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
