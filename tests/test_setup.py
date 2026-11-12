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
