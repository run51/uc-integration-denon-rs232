"""TCP transport for a serial-over-IP bridge in front of the Denon RS-232 port.

Works with any transparent serial bridge that exposes a raw TCP socket:
Unfolded Circle Dock 3 (external port 2 = TCP 5000), Global Caché IP2SL / iTach,
USR-TCP232, ser2net, ESPHome stream server, ...

The bridge may deliver bytes in arbitrary chunks (a response can be split
across two reads, several responses can arrive in one read), so framing is done
here: bytes are accumulated and cut on <CR> (0x0D).  A trailing <LF> is
tolerated in case the bridge adds one.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from .const import COMMAND_GAP_S, CR

_LOG = logging.getLogger(__name__)

LineCallback = Callable[[str], Awaitable[None] | None]

CONNECT_TIMEOUT_S = 5.0
FRAME_TERMINATORS = (b"\r", b"\n")
MAX_BUFFER = 4096


class TcpTransport:
    """Persistent TCP connection with CR framing and paced writes."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        on_line: LineCallback | None = None,
        command_gap: float = COMMAND_GAP_S,
    ) -> None:
        self._host = host
        self._port = port
        self._on_line = on_line
        self._command_gap = command_gap

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._read_task: asyncio.Task[None] | None = None
        self._closed = asyncio.Event()
        self._closed.set()

        self._write_lock = asyncio.Lock()
        self._last_write = 0.0
        self._hold_until = 0.0

    # ------------------------------------------------------------------ props

    @property
    def host(self) -> str:
        """Bridge host."""
        return self._host

    @property
    def port(self) -> int:
        """Bridge TCP port."""
        return self._port

    @property
    def is_connected(self) -> bool:
        """True while the socket is open."""
        return self._writer is not None and not self._closed.is_set()

    def set_line_callback(self, callback: LineCallback | None) -> None:
        """Register the per-line callback."""
        self._on_line = callback

    # ------------------------------------------------------------ lifecycle

    async def connect(self) -> None:
        """Open the socket and start the reader task."""
        if self.is_connected:
            return

        _LOG.debug("Connecting to %s:%s", self._host, self._port)
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port),
            timeout=CONNECT_TIMEOUT_S,
        )
        self._reader = reader
        self._writer = writer
        self._closed.clear()
        self._read_task = asyncio.create_task(
            self._read_loop(), name=f"denon-rx-{self._host}:{self._port}"
        )
        _LOG.info("Connected to %s:%s", self._host, self._port)

    async def disconnect(self) -> None:
        """Close the socket and stop the reader task."""
        task = self._read_task
        self._read_task = None

        if task is not None and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # pylint: disable=broad-except
                pass

        await self._close_writer()

    async def wait_closed(self) -> None:
        """Block until the connection is lost or closed."""
        await self._closed.wait()

    async def _close_writer(self) -> None:
        writer = self._writer
        self._writer = None
        self._reader = None

        if writer is not None:
            try:
                writer.close()
                await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
            except Exception:  # pylint: disable=broad-except
                pass

        self._closed.set()

    # ----------------------------------------------------------------- write

    def hold_for(self, seconds: float) -> None:
        """Delay any further command by ``seconds`` (used after power on)."""
        self._hold_until = max(self._hold_until, time.monotonic() + seconds)

    async def send(self, command: str) -> None:
        """Send one command, appending <CR>, respecting the inter-command gap."""
        if not self.is_connected or self._writer is None:
            raise ConnectionError("Not connected")

        payload = command.rstrip("\r\n") + CR

        async with self._write_lock:
            now = time.monotonic()
            wait = max(self._hold_until - now, self._last_write + self._command_gap - now)
            if wait > 0:
                await asyncio.sleep(wait)

            try:
                self._writer.write(payload.encode("latin-1"))
                await self._writer.drain()
            except (ConnectionError, OSError) as err:
                await self._close_writer()
                raise ConnectionError(f"Write failed: {err}") from err

            self._last_write = time.monotonic()
            _LOG.debug(">>> %r", command)

    # ------------------------------------------------------------------ read

    async def _read_loop(self) -> None:
        assert self._reader is not None
        reader = self._reader
        buffer = bytearray()

        try:
            while True:
                chunk = await reader.read(512)
                if not chunk:
                    _LOG.warning("Connection closed by %s:%s", self._host, self._port)
                    break

                buffer.extend(chunk)

                while True:
                    cut = -1
                    for term in FRAME_TERMINATORS:
                        idx = buffer.find(term)
                        if idx != -1 and (cut == -1 or idx < cut):
                            cut = idx
                    if cut == -1:
                        break

                    raw = bytes(buffer[:cut])
                    del buffer[: cut + 1]

                    line = raw.decode("latin-1").strip()
                    if line:
                        _LOG.debug("<<< %r", line)
                        await self._dispatch(line)

                if len(buffer) > MAX_BUFFER:
                    _LOG.warning("RX buffer overflow, discarding %d bytes", len(buffer))
                    buffer.clear()

        except asyncio.CancelledError:
            raise
        except (ConnectionError, OSError) as err:
            _LOG.warning("Read error on %s:%s: %s", self._host, self._port, err)
        finally:
            await self._close_writer()

    async def _dispatch(self, line: str) -> None:
        if self._on_line is None:
            return
        try:
            result = self._on_line(line)
            if asyncio.iscoroutine(result):
                await result
        except Exception:  # pylint: disable=broad-except
            _LOG.exception("Unhandled error while processing line %r", line)
