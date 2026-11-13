"""Direct / Pure Direct indicator sensors: which lamp is lit for each decoding the unit reports."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "intg-denon"))

from const import INDICATOR_OFF_COLOR, INDICATOR_ON_COLOR, DeviceConfig  # noqa: E402
from device import DenonClientDevice  # noqa: E402
from ucapi import sensor  # noqa: E402


@pytest.mark.parametrize(
    ("surround", "direct", "pure"),
    [
        ("DIRECT", True, False),
        ("MULTI CH DIRECT", True, False),
        ("DSD DIRECT", True, False),
        ("M CH DRCT", True, False),
        ("DSD MULTI DRCT", True, False),
        ("PURE DIRECT", False, True),
        ("MULTI CH PURE D", False, True),
        ("DSD PURE DIRECT", False, True),
        ("STEREO", False, False),
        ("DOLBY PL2 C", False, False),
        (None, False, False),
    ],
)
def test_indicator_on(surround: str | None, direct: bool, pure: bool) -> None:
    cfg = DeviceConfig(identifier="d", name="Denon", address="127.0.0.1")
    dev = DenonClientDevice(cfg, asyncio.new_event_loop())
    dev.denon.surround = surround
    assert dev.indicator_on("direct") is direct
    assert dev.indicator_on("pure_direct") is pure


def test_indicator_value_is_a_lamp_grey_when_off(monkeypatch: pytest.MonkeyPatch) -> None:
    # the style settings of the other sensors do not apply to the lamp
    cfg = DeviceConfig(
        identifier="d", name="Denon", address="127.0.0.1", sensor_font_size=2, sensor_color="#f00"
    )
    dev = DenonClientDevice(cfg, asyncio.new_event_loop())
    monkeypatch.setattr(DenonClientDevice, "is_connected", property(lambda self: True))
    dev.denon.surround = "PURE DIRECT"
    lit = dev.get_sensor_attributes("pure_direct")
    off = dev.get_sensor_attributes("direct")
    assert lit[sensor.Attributes.VALUE] == f"<font color='{INDICATOR_ON_COLOR}'>●</font>"
    assert off[sensor.Attributes.VALUE] == f"<font color='{INDICATOR_OFF_COLOR}'>●</font>"
    assert lit[sensor.Attributes.STATE] is sensor.States.ON
