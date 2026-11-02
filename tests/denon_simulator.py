"""Minimal AVP-A1HD simulator behind a raw TCP socket.

Reproduces what the real unit did in the RS-232 capture:
* answers queries, pushes unsolicited EVENTs on change,
* ``MVMAX 98`` after every ``MV`` response,
* a burst of state after ``PWON`` (channel levels, MS, SI, SD...),
* ``MSQUICK1`` when a quick select is recalled,
* on MVUP/MVDOWN reports the previous then the new value,
* occasionally splits a frame across two writes (fragmentation).

Usage:  python tests/denon_simulator.py [port]     (default 4999)
"""

from __future__ import annotations

import asyncio
import logging
import sys

_LOG = logging.getLogger("denon-sim")

CR = b"\r"


class DenonSim:  # pylint: disable=too-many-instance-attributes
    """Simulated unit state."""

    def __init__(self) -> None:
        self.power = False
        self.main_zone = True
        self.volume = 30.0  # code units, 80 = 0 dB
        self.muted = False
        self.source = "DVD"
        self.surround = "STEREO"
        self.input_mode = "AUTO"
        self.quick = "QUICK1"
        self.ps = {
            "ROOM EQ:": "AUDYSSEY",
            "DYN ": "ON",
            "DYNSET ": "EVE",
            "DSX ": "OFF",
            "REFLEV ": "0",
            "RSTR ": "OFF",
            "CINEMA EQ.": "OFF",
        }
        self.channels = {
            "FL": "405", "FR": "41", "C": "38", "SW1": "38", "SW2": "50", "SW3": "50",
            "TR": "50", "SL": "40", "SR": "41", "SBL": "50", "SBR": "50", "SB": "50",
            "FHL": "50", "FHR": "50", "FWL": "50", "FWR": "50",
        }
        self.zones = {2: (False, "SOURCE", 45.0), 3: (False, "SOURCE", 45.0)}
        self.clients: set[asyncio.StreamWriter] = set()

    # ------------------------------------------------------------ helpers

    @staticmethod
    def fmt(code: float) -> str:
        whole = int(code)
        return f"{whole:02d}5" if code - whole >= 0.5 else f"{whole:02d}"

    async def broadcast(self, *lines: str, fragment: bool = False) -> None:
        for line in lines:
            data = line.encode("latin-1") + CR
            for writer in list(self.clients):
                try:
                    if fragment and len(data) > 4:
                        writer.write(data[:4])
                        await writer.drain()
                        await asyncio.sleep(0.03)
                        writer.write(data[4:])
                    else:
                        writer.write(data)
                    await writer.drain()
                except (ConnectionError, OSError):
                    self.clients.discard(writer)
            _LOG.debug("<<< %s", line)
            await asyncio.sleep(0.015)

    def mv(self) -> list[str]:
        return [f"MV{self.fmt(self.volume)}", "MVMAX 98"]

    def channel_levels(self) -> list[str]:
        return [f"CV{ch} {code}" for ch, code in self.channels.items()]

    # ------------------------------------------------------------ commands

    async def handle(self, cmd: str) -> None:  # pylint: disable=too-many-branches,too-many-statements
        _LOG.debug(">>> %s", cmd)

        if cmd == "PW?":
            await self.broadcast("PWON" if self.power else "PWSTANDBY")
        elif cmd == "PWON":
            if not self.power:
                self.power = True
                await self.broadcast("ZMON", "PWON")
                await asyncio.sleep(0.6)
                await self.broadcast(*self.mv(), f"MS{self.surround}")
                await self.broadcast(*self.channel_levels(), fragment=True)
                await self.broadcast("MVMAX 98")
        elif cmd == "PWSTANDBY":
            self.power = False
            await self.broadcast("PWSTANDBY")
        elif not self.power:
            return  # standby: silent, like the real unit

        elif cmd == "ZM?":
            await self.broadcast("ZMON" if self.main_zone else "ZMOFF")
        elif cmd == "MV?":
            await self.broadcast(*self.mv())
        elif cmd == "MVUP":
            old = self.mv()
            self.volume = min(98, self.volume + 0.5)
            await self.broadcast(*old, *self.mv())
        elif cmd == "MVDOWN":
            old = self.mv()
            self.volume = max(0, self.volume - 0.5)
            await self.broadcast(*old, *self.mv())
        elif cmd.startswith("MV"):
            body = cmd[2:]
            self.volume = int(body[:2]) + (0.5 if len(body) == 3 else 0)
            await self.broadcast(*self.mv())
        elif cmd == "MU?":
            await self.broadcast("MUON" if self.muted else "MUOFF")
        elif cmd in ("MUON", "MUOFF"):
            self.muted = cmd == "MUON"
            await self.broadcast(cmd)
        elif cmd == "SI?":
            await self.broadcast(f"SI{self.source}", "SVSOURCE")
        elif cmd.startswith("SI"):
            self.source = cmd[2:]
            await self.broadcast(f"SI{self.source}", f"SV{self.source}", f"MS{self.surround}")
            await self.broadcast(*self.channel_levels())
        elif cmd == "CV?":
            await self.broadcast(*self.channel_levels())
        elif cmd.startswith("CV") and " " in cmd:
            ch, code = cmd[2:].split(" ", 1)
            if ch in self.channels and code.isdigit():
                self.channels[ch] = code
                await self.broadcast(f"CV{ch} {code}")
        elif cmd == "SD?":
            await self.broadcast(f"SD{self.input_mode}")
        elif cmd.startswith("SD"):
            self.input_mode = cmd[2:]
            await self.broadcast(f"SD{self.input_mode}")
        elif cmd == "DC?":
            await self.broadcast("DCAUTO")
        elif cmd == "MS?":
            await self.broadcast(f"MS{self.surround}")
        elif cmd == "MSQUICK ?":
            await self.broadcast(f"MS{self.quick}")
        elif cmd.startswith("MSQUICK"):
            self.quick = cmd[2:].split()[0]
            self.surround = "STEREO"
            await self.broadcast(f"MS{self.quick}", f"MS{self.surround}", f"SI{self.source}")
        elif cmd.startswith("MS"):
            self.surround = cmd[2:]
            await self.broadcast(f"MS{self.surround}")
            await self.broadcast(*self.channel_levels())
        elif cmd.startswith("PS"):
            body = cmd[2:]
            for key, value in self.ps.items():
                if body.startswith(key):
                    rest = body[len(key):].strip()
                    if rest == "?":
                        await self.broadcast(f"PS{key}{value}")
                    elif key == "DYNSET " and self.ps["DYN "] != "VOL":
                        pass  # real unit ignores the level unless Dynamic Volume is on
                    else:
                        self.ps[key] = rest
                        await self.broadcast(f"PS{key}{rest}")
                    return
            # unknown PS query: silent (PSNIGHT ? is unanswered since the 3D upgrade)
        elif cmd[:2] in ("Z2", "Z3"):
            zone = int(cmd[1])
            power, src, vol = self.zones[zone]
            body = cmd[2:]
            if body == "?":
                await self.broadcast(f"Z{zone}{'ON' if power else 'OFF'}", f"Z{zone}{src}", f"Z{zone}{self.fmt(vol)}")
            elif body == "MU?":
                await self.broadcast(f"Z{zone}MUOFF")
            elif body in ("ON", "OFF"):
                self.zones[zone] = (body == "ON", src, vol)
                await self.broadcast(cmd)
            elif body == "UP":
                self.zones[zone] = (power, src, vol + 1)
                await self.broadcast(f"Z{zone}{self.fmt(vol + 1)}")
            elif body == "DOWN":
                self.zones[zone] = (power, src, vol - 1)
                await self.broadcast(f"Z{zone}{self.fmt(vol - 1)}")
            else:
                self.zones[zone] = (power, body, vol)
                await self.broadcast(cmd)
        elif cmd == "Z4?":
            await self.broadcast("Z4OFF")
        elif cmd.startswith("MN"):
            pass  # cursor: no echo

    # ------------------------------------------------------------- server

    async def client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        _LOG.info("client connected: %s", peer)
        self.clients.add(writer)
        buffer = b""
        try:
            while True:
                chunk = await reader.read(256)
                if not chunk:
                    break
                buffer += chunk
                while CR in buffer or b"\n" in buffer:
                    idx = min(i for i in (buffer.find(CR), buffer.find(b"\n")) if i != -1)
                    line, buffer = buffer[:idx], buffer[idx + 1:]
                    text = line.decode("latin-1").strip()
                    if text:
                        await self.handle(text)
        except (ConnectionError, OSError):
            pass
        finally:
            self.clients.discard(writer)
            writer.close()
            _LOG.info("client disconnected: %s", peer)


async def main(port: int) -> None:
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s %(message)s")
    sim = DenonSim()
    server = await asyncio.start_server(sim.client, "0.0.0.0", port)
    _LOG.info("Denon simulator listening on %s", port)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 4999))
