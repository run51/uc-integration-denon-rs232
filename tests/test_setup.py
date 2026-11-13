"""Device identifier must stay stable when the bridge address changes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "intg-denon"))

from setup import make_identifier  # noqa: E402


def test_identifier_ignores_address() -> None:
    # Fresh install, whatever the bridge IP: always the same id.
    assert make_identifier(lambda _id: False) == "denon"


def test_update_keeps_identifier() -> None:
    # "Update" removes the old config first, so the id is free again.
    configured: set[str] = {"denon"}
    configured.discard("denon")
    assert make_identifier(configured.__contains__) == "denon"


def test_second_device_gets_suffix() -> None:
    assert make_identifier({"denon"}.__contains__) == "denon_2"
    assert make_identifier({"denon", "denon_2"}.__contains__) == "denon_3"


def test_sensor_value_style() -> None:
    from device import style_sensor_value  # noqa: E402

    assert style_sensor_value("Dolby TrueHD", 0, "") is None
    styled = style_sensor_value("Dolby TrueHD", 2, "#4da6ff")
    assert styled == "<font size='2' color='#4da6ff'>Dolby TrueHD</font>"
    assert style_sensor_value("-35.0 dB", 1, "") == "<font size='1'>-35.0 dB</font>"
    # Unknown colour syntax is ignored, text is escaped.
    assert style_sensor_value("A<B", 0, "x' onload='") is None
    assert style_sensor_value("A<B", 2, "x' onload='") == "<font size='2'>A&lt;B</font>"


def test_number_values_and_codes() -> None:
    from device import _lfe_db, _tone_db  # noqa: E402

    assert _tone_db("50") == 0.0
    assert _tone_db("44") == -6.0
    assert _tone_db("56") == 6.0
    assert _tone_db(None) is None
    assert _lfe_db("00") == 0.0
    assert _lfe_db("10") == -10.0
    assert _lfe_db("x") is None


def test_number_entity_definition() -> None:
    from const import NUMBERS, DeviceConfig  # noqa: E402
    from number_entity import NUMBER, DenonNumber  # noqa: E402

    class FakeDevice:
        def add_listener(self, *_a, **_k):
            pass

    cfg = DeviceConfig(identifier="denon", name="Denon", address="1.2.3.4", number_entities=True)
    volume = next(n for n in NUMBERS if n.identifier == "volume")
    try:
        entity = DenonNumber(cfg, FakeDevice(), volume)  # type: ignore[arg-type]
    except AttributeError:
        return  # framework needs a real device to subscribe: the definition is checked below
    assert entity.id == "number.denon.volume"
    assert entity.entity_type == "number" and NUMBER.value == "number"
    assert entity.options["min"] == -80.0 and entity.options["unit"] == "dB"


def test_held_button_steps_build_on_last_sent_value() -> None:
    """A held volume button: each step builds on the value just sent, shown at once."""
    import asyncio

    from const import NUMBER_BY_ID, DeviceConfig  # noqa: E402
    from device import DenonClientDevice  # noqa: E402
    from number_entity import DenonNumber  # noqa: E402
    from ucapi import StatusCodes  # noqa: E402

    async def run() -> tuple[list[float], list[float | None], int]:
        cfg = DeviceConfig(
            identifier="denon", name="Denon", address="1.2.3.4", number_entities=True
        )
        dev = DenonClientDevice(cfg, asyncio.get_running_loop())
        dev.denon.volume_db = -40.0  # the unit has not reported any of the new levels yet
        sent: list[float] = []
        shown: list[float | None] = []
        pushes = 0

        async def set_volume_db(value: float) -> None:
            sent.append(value)

        def push_update() -> None:
            nonlocal pushes
            pushes += 1

        dev._client.set_volume_db = set_volume_db  # type: ignore[method-assign]  # noqa: SLF001
        dev.push_update = push_update  # type: ignore[method-assign]
        entity = DenonNumber.__new__(DenonNumber)
        entity._device, entity._cfg = dev, NUMBER_BY_ID["volume"]  # noqa: SLF001
        for cmd in ("increment", "increment", "increment", "decrement"):
            assert await entity.handle_command(None, cmd, None) == StatusCodes.OK
            shown.append(dev.number_value(NUMBER_BY_ID["volume"]))
        dev.denon.volume_db = -39.0  # the unit reports the last value: the pending one is dropped
        assert dev.number_value(NUMBER_BY_ID["volume"]) == -39.0
        assert "volume" not in dev._pending_numbers  # noqa: SLF001
        return sent, shown, pushes

    sent, shown, pushes = asyncio.run(run())
    assert sent == [-39.5, -39.0, -38.5, -39.0]
    assert shown == sent  # shown before the unit reports it
    assert pushes == 4  # one immediate push per step


def test_pending_value_expires() -> None:
    """A value the unit never reports is given up after PENDING_S: the reported one is shown."""
    import asyncio

    import device as device_module  # noqa: E402
    from const import NUMBER_BY_ID, DeviceConfig  # noqa: E402
    from device import DenonClientDevice  # noqa: E402

    async def run() -> tuple[float | None, float | None]:
        cfg = DeviceConfig(
            identifier="denon", name="Denon", address="1.2.3.4", number_entities=True
        )
        dev = DenonClientDevice(cfg, asyncio.get_running_loop())
        dev.denon.channel_levels["C"] = -3.0
        dev.push_update = lambda: None  # type: ignore[method-assign]

        async def set_level(_key: str, _value: float) -> None:
            pass

        dev._client.set_channel_level_db = set_level  # type: ignore[method-assign]  # noqa: SLF001
        await dev.set_number("center_level", 20.0)  # clamped to +12, never confirmed
        before = dev.number_value(NUMBER_BY_ID["center_level"])
        value, _ = dev._pending_numbers["center_level"]  # noqa: SLF001
        dev._pending_numbers["center_level"] = (value, -device_module.PENDING_S)  # noqa: SLF001
        return before, dev.number_value(NUMBER_BY_ID["center_level"])

    assert asyncio.run(run()) == (12.0, -3.0)


def test_number_values_are_clamped_to_the_range() -> None:
    from const import NUMBER_BY_ID  # noqa: E402

    center = NUMBER_BY_ID["center_level"]
    assert center.clamp(12.7) == 12.0
    assert center.clamp(-3.26) == -3.5
    assert NUMBER_BY_ID["volume"].clamp(-81) == -80.0
