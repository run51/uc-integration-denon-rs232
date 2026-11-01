"""End-to-end test: framework device wrapper <-> simulated Denon over TCP."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "intg-denon"))
sys.path.insert(0, str(ROOT / "tests"))

from denon_simulator import DenonSim  # noqa: E402
from const import SELECT_BY_ID, SWITCH_BY_ID, DeviceConfig  # noqa: E402
from device import DenonClientDevice  # noqa: E402
from ucapi import media_player, select, switch  # noqa: E402
from ucapi_framework import DeviceEvents  # noqa: E402


async def _wait_for(predicate, timeout: float = 5.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while not predicate():
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_full_cycle() -> None:
    sim = DenonSim()
    server = await asyncio.start_server(sim.client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    cfg = DeviceConfig(identifier="denon_test", name="Denon Test", address="127.0.0.1", port=port)
    dev = DenonClientDevice(cfg, asyncio.get_event_loop())

    updates: list[str] = []
    dev.events.on(DeviceEvents.UPDATE, lambda *a, **k: updates.append("update"))
    connected = asyncio.Event()
    dev.events.on(DeviceEvents.CONNECTED, lambda *_: connected.set())

    try:
        await dev.connect()
        await asyncio.wait_for(connected.wait(), 5)

        # Initial query: unit is in standby
        await _wait_for(lambda: dev.denon.power is False)
        assert dev.state is media_player.States.STANDBY
        mp = dev.get_media_player_attributes()
        assert mp[media_player.Attributes.STATE] is media_player.States.STANDBY
        assert "TV/CBL" in mp[media_player.Attributes.SOURCE_LIST]
        assert mp[media_player.Attributes.MEDIA_TITLE] == ""

        # Power on -> burst of state (fragmented CV lines included)
        await dev.power_on()
        await _wait_for(lambda: dev.denon.power is True and dev.denon.volume_db is not None)
        await _wait_for(lambda: dev.denon.channel_levels.get("FL") == -9.5, timeout=6)
        assert dev.state is media_player.States.ON
        assert dev.denon.volume_db == -50.0
        assert dev.denon.volume_max_db == 18.0
        assert dev.denon.surround == "STEREO"

        # The refresh scheduled after power-on (4.5 s) fetches the PS family
        await _wait_for(lambda: dev.denon.parameters.get("ROOM EQ") == "AUDYSSEY", timeout=8)
        assert dev.denon.quick_select == "QUICK1"
        assert dev.denon.source == "DVD"

        # Volume: old value then new value are both reported; final state wins
        await dev.volume_up()
        await _wait_for(lambda: dev.denon.volume_db == -49.5)
        assert dev.get_media_player_attributes()[media_player.Attributes.VOLUME] == 31

        await dev.set_volume_percent(50)  # -80 + 0.5*98 = -31 dB -> MV49
        await _wait_for(lambda: dev.denon.volume_db == -31.0)

        # Select source by label
        await dev.select_source("TV/CBL")
        await _wait_for(lambda: dev.denon.source == "TV/CBL")
        sel = dev.get_select_attributes("source")
        assert sel[select.Attributes.CURRENT_OPTION] == "TV/CBL"
        assert sel[select.Attributes.STATE] is select.States.ON

        # Sound mode by label
        await dev.select_sound_mode("7ch Stereo")
        await _wait_for(lambda: dev.denon.surround == "7CH STEREO")
        assert dev.get_media_player_attributes()[media_player.Attributes.SOUND_MODE] == "7ch Stereo"

        # PS select + switch
        await dev.select_option(SELECT_BY_ID["room_eq"], "Flat")
        await _wait_for(lambda: dev.denon.parameters.get("ROOM EQ") == "FLAT")
        await dev.select_option(SELECT_BY_ID["dynamic_eq"], "Dynamic EQ")
        await _wait_for(lambda: dev.denon.parameters.get("DYN") == "ON")
        dyn = dev.get_select_attributes("dynamic_eq")
        assert dyn[select.Attributes.CURRENT_OPTION] == "Dynamic EQ"
        assert dev.get_sensor_attributes("dynamic_eq")["value"] == "Dynamic EQ"
        await dev.select_option(SELECT_BY_ID["dsx"], "Height")
        await _wait_for(lambda: dev.denon.parameters.get("DSX") == "ONH")
        # Dynamic Volume level while Dynamic EQ alone is on: the unit would
        # ignore PSDYNSET, so the driver enables PSDYN VOL first.
        await dev.select_option(SELECT_BY_ID["dynamic_volume"], "Day")
        await _wait_for(lambda: dev.denon.parameters.get("DYNSET") == "DAY")
        assert dev.denon.parameters.get("DYN") == "VOL"
        await dev.select_option(SELECT_BY_ID["dynamic_eq"], "Dynamic EQ")
        await _wait_for(lambda: dev.denon.parameters.get("DYN") == "ON")
        await dev.set_switch(SWITCH_BY_ID["cinema_eq"], True)
        await _wait_for(lambda: dev.denon.parameters.get("CINEMA EQ") == "ON")
        assert dev.get_switch_attributes("cinema_eq")[switch.Attributes.STATE] is switch.States.ON

        # Mute
        await dev.mute(True)
        await _wait_for(lambda: dev.denon.muted is True)
        mp = dev.get_media_player_attributes()
        assert mp[media_player.Attributes.MUTED] is True

        # Media widget lines: source / surround mode / volume in dB
        assert mp[media_player.Attributes.MEDIA_TITLE] == "TV/CBL"
        assert mp[media_player.Attributes.MEDIA_ARTIST] == "7ch Stereo"
        assert mp[media_player.Attributes.MEDIA_ALBUM] == "-31.0 dB · Muted"

        # Zone 2
        await dev.set_switch(SWITCH_BY_ID["zone2_power"], True)
        await _wait_for(lambda: dev.denon.zones[2].power is True)
        await dev.select_option(SELECT_BY_ID["zone2_source"], "CD")
        await _wait_for(lambda: dev.denon.zones[2].source == "CD")

        # Raw pass-through + simple command
        assert await dev.send_simple_command("QUICK2")
        await _wait_for(lambda: dev.denon.quick_select == "QUICK2")
        assert await dev.send_simple_command("DYN_EQ_VOL")
        await _wait_for(lambda: dev.denon.parameters.get("DYN") == "VOL")
        assert await dev.send_simple_command("PSDYNSET NGT")  # raw
        await _wait_for(lambda: dev.denon.parameters.get("DYNSET") == "NGT")
        assert not await dev.send_simple_command("not a command")

        # Sensors
        vol_sensor = dev.get_sensor_attributes("volume_db")
        assert vol_sensor["value"] == f"{dev.denon.volume_db:.1f}"
        assert dev.get_sensor_attributes("room_eq")["value"] == "Flat"

        # Updates were debounced: far fewer pushes than lines received
        assert 5 < len(updates) < 60, len(updates)

        # Drop the link from the server side -> device reconnects by itself
        for writer in list(sim.clients):
            writer.close()
        await _wait_for(lambda: not dev.is_connected, timeout=3)
        await _wait_for(lambda: dev.is_connected and dev.denon.power is True, timeout=10)

        # Standby while connected
        await dev.power_off()
        await _wait_for(lambda: dev.denon.power is False)
        assert dev.state is media_player.States.STANDBY

    finally:
        await dev.disconnect()
        server.close()
        await server.wait_closed()
