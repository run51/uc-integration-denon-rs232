"""Level pictures: SVG bars served to the Remote for the level sensors."""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "intg-denon"))

import level_images  # noqa: E402
from level_images import LevelImageServer, draw  # noqa: E402


def _fill_width(svg: str) -> float:
    """Width of the blue fill rectangle."""
    match = re.search(
        r'<rect x="[\d.]+" y="[\d.]+" width="([\d.]+)" height="[\d.]+"[^>]*fill="#4da6ff"', svg
    )
    return float(match.group(1)) if match else 0.0


def test_center_bar_fills_from_zero() -> None:
    zero, minus = draw("center_level", 0.0), draw("center_level", -6.0)
    plus = draw("center_level", 6.0)
    assert _fill_width(zero) == 0.0 and ">0.0 <" in zero
    assert _fill_width(minus) == _fill_width(plus) > 0
    assert ">-6.0 <" in minus and ">+6.0 <" in plus


def test_volume_card_fills_from_minimum() -> None:
    low, high = draw("volume", -80.0), draw("volume", 18.0)
    assert _fill_width(high) > _fill_width(low) > 0  # a round end stays visible at the minimum
    assert ">-48.5<tspan" in draw("volume", -48.5)


def test_values_out_of_range_are_drawn_at_the_ends() -> None:
    assert _fill_width(draw("center_level", 40.0)) == _fill_width(draw("center_level", 12.0))


def test_requests() -> None:
    ok = LevelImageServer.respond("GET /level/center_level.svg?v=-5.0 HTTP/1.1")
    assert ok[0] == "200 OK" and ok[2] == "image/svg+xml" and ok[1].startswith(b"<svg")
    assert LevelImageServer.respond("GET /level/nope.svg?v=1 HTTP/1.1")[0].startswith("404")
    assert LevelImageServer.respond("GET /level/volume.svg HTTP/1.1")[0].startswith("400")
    assert LevelImageServer.respond("GET /level/volume.svg?v=abc HTTP/1.1")[0].startswith("400")
    assert LevelImageServer.respond("POST /level/volume.svg?v=1 HTTP/1.1")[0].startswith("405")


def test_taken_port_is_skipped() -> None:
    async def run() -> tuple[int, bool]:
        blocker = await asyncio.start_server(lambda r, w: None, "0.0.0.0", 0)
        taken = blocker.sockets[0].getsockname()[1]
        server = LevelImageServer(port=taken)
        await server.start()
        result = (server.port, server.running)
        server._server.close()  # type: ignore[union-attr]  # noqa: SLF001
        blocker.close()
        return result, taken

    (port, running), taken = asyncio.run(run())
    assert running and port != taken


def test_sensor_value_is_an_image_tag() -> None:
    server = LevelImageServer(host="192.168.1.2", port=9999)
    assert server.img("center_level", -5) == (
        "<img src='http://192.168.1.2:9999/level/center_level.svg?v=-5.0' width='216' height='50'>"
    )
    assert "width='136' height='96'" in server.img("volume", -40)


def test_served_over_http() -> None:
    async def run() -> bytes:
        server = LevelImageServer(port=0)
        server._server = await asyncio.start_server(server._handle, "127.0.0.1", 0)  # noqa: SLF001
        port = server._server.sockets[0].getsockname()[1]  # noqa: SLF001
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET /level/bass.svg?v=2 HTTP/1.1\r\nHost: x\r\n\r\n")
        await writer.drain()
        data = await reader.read()
        writer.close()
        server._server.close()  # noqa: SLF001
        return data

    data = asyncio.run(run())
    assert data.startswith(b"HTTP/1.1 200 OK") and b"image/svg+xml" in data and b">+2.0 <" in data


def test_level_sensor_attributes() -> None:
    from const import SENSOR_BY_ID  # noqa: E402
    from device import DenonClientDevice  # noqa: E402

    class Fake:
        is_connected = True
        number_value = DenonClientDevice.number_value
        reported_number_value = DenonClientDevice.reported_number_value
        _pending_numbers: dict[str, tuple[float, float]] = {}
        get_sensor_attributes = DenonClientDevice.get_sensor_attributes

        class denon:  # noqa: N801 - stands for DenonState
            volume_db = -48.5
            channel_levels = {"C": -5.0}
            parameters: dict[str, str] = {}

    level_images.SERVER._server = object()  # type: ignore[assignment]  # noqa: SLF001 - "running"
    try:
        attrs = Fake().get_sensor_attributes("center_level_bar")  # type: ignore[arg-type]
        assert attrs["value"].startswith("<img src='http://127.0.0.1:9330/level/center_level.svg?v=-5.0'")
        Fake.is_connected = False
        attrs = Fake().get_sensor_attributes("volume_level")  # type: ignore[arg-type]
        assert attrs["value"] == "" and attrs["state"] == "UNAVAILABLE"
    finally:
        level_images.SERVER._server = None  # noqa: SLF001
    assert "volume_level" in SENSOR_BY_ID
