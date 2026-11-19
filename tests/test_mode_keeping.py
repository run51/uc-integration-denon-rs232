"""The listening mode asked for is kept when the unit switches back by itself."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "intg-denon"))

import device as device_module  # noqa: E402
from const import DeviceConfig  # noqa: E402
from denon_control.protocol import DenonEvent, EventKind  # noqa: E402
from device import DenonClientDevice, is_surround_command, mode_family  # noqa: E402


def test_families() -> None:
    assert {mode_family(m) for m in ("STANDARD", "DOLBY DIGITAL", "PLII CINEMA")} == {"other"}
    assert {mode_family(m) for m in ("DIRECT", "MULTI CH DIRECT", "M CH DRCT")} == {"direct"}
    assert mode_family("PURE DIRECT") == mode_family("MULTI CH PURE D") == "pure"
    assert is_surround_command("MSSTANDARD") and not is_surround_command("MSQUICK1")


def _run(reports: list[str], asked: str = "SURROUND_STANDARD", age: float = 0.0) -> list[str]:
    async def run() -> list[str]:
        cfg = DeviceConfig(identifier="denon", name="Denon", address="1.2.3.4")
        dev = DenonClientDevice(cfg, asyncio.get_running_loop())
        sent: list[str] = []

        async def send_raw(command: str) -> None:
            sent.append(command)

        async def select_surround(code: str) -> None:
            sent.append(f"MS{code}")

        dev._client.send_raw = send_raw  # type: ignore[method-assign]  # noqa: SLF001
        dev._client.select_surround = select_surround  # type: ignore[method-assign]  # noqa: SLF001
        dev.push_update = lambda: None  # type: ignore[method-assign]
        await dev.send_simple_command(asked)
        if age:
            code, at, left = dev._mode_request  # noqa: SLF001
            dev._mode_request = (code, at - age, left)  # noqa: SLF001
        for value in reports:
            dev._on_denon_event(dev.denon, DenonEvent(EventKind.SURROUND, value, raw=f"MS{value}"))  # noqa: SLF001
            await asyncio.sleep(device_module.MODE_RESEND_DELAY_S + 0.05)
        return sent

    device_module.MODE_RESEND_DELAY_S = 0.01
    return asyncio.run(run())


def test_unit_switching_to_direct_gets_standard_again() -> None:
    assert _run(["PLII CINEMA", "DIRECT"]) == ["MSSTANDARD", "MSSTANDARD"]


def test_standard_decoding_choices_are_left_alone() -> None:
    assert _run(["DOLBY DIGITAL", "DTS NEO:X C", "PLII CINEMA"]) == ["MSSTANDARD"]


def test_direct_asked_for_music_is_kept_too() -> None:
    assert _run(["STEREO"], asked="SURROUND_DIRECT") == ["MSDIRECT", "MSDIRECT"]


def test_not_kept_after_the_window_nor_more_than_three_times() -> None:
    assert _run(["DIRECT"], age=device_module.MODE_KEEP_S + 1) == ["MSSTANDARD"]
    assert _run(["DIRECT"] * 5) == ["MSSTANDARD"] * 4  # the request + 3 resends at most
