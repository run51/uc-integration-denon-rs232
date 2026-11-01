"""Parser tests built from a real AVP-A1HD RS-232 capture."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "intg-denon"))

from denon_control import DenonDevice, EventKind, decode_level, encode_level, parse_line  # noqa: E402
from denon_control.const import VOLUME_ZERO_DB_CODE  # noqa: E402


# --- Master volume -----------------------------------------------------------


@pytest.mark.parametrize(
    "line, db",
    [
        ("MV30", -50.0),
        ("MV305", -49.5),
        ("MV295", -50.5),
        ("MV80", 0.0),
        ("MV805", 0.5),
        ("MV795", -0.5),
        ("MV00", -80.0),
        ("MV98", 18.0),
    ],
)
def test_volume(line: str, db: float) -> None:
    event = parse_line(line)
    assert event.kind is EventKind.VOLUME
    assert event.value == db


def test_mvmax_is_not_a_volume() -> None:
    """Trap #2: MVMAX follows every MV and must not be read as volume."""
    event = parse_line("MVMAX 98")
    assert event.kind is EventKind.VOLUME_MAX
    assert event.value == 18.0


def test_encode_roundtrip() -> None:
    for db in (-80.0, -49.5, -50.0, 0.0, 0.5, 18.0):
        code = encode_level(db, VOLUME_ZERO_DB_CODE, max_code=98)
        assert decode_level(code, VOLUME_ZERO_DB_CODE) == db


# --- Power -------------------------------------------------------------------


def test_power() -> None:
    assert parse_line("PWON") == parse_line("PWON")
    assert parse_line("PWON").value is True
    assert parse_line("PWSTANDBY").value is False
    assert parse_line("PWSTANDBY").kind is EventKind.POWER
    assert parse_line("ZMON").kind is EventKind.MAIN_ZONE


# --- Surround / quick select --------------------------------------------------


def test_msquick_is_not_a_surround_mode() -> None:
    """Trap #3: MSQUICK1 carries the MS prefix."""
    event = parse_line("MSQUICK1")
    assert event.kind is EventKind.QUICK_SELECT
    assert event.value == "QUICK1"


@pytest.mark.parametrize("line, mode", [("MSDOLBY PL2 C", "DOLBY PL2 C"), ("MSSTEREO", "STEREO"), ("MSDOLBY HD", "DOLBY HD")])
def test_surround(line: str, mode: str) -> None:
    event = parse_line(line)
    assert event.kind is EventKind.SURROUND
    assert event.value == mode


# --- Sources -----------------------------------------------------------------


def test_source_vs_video_select() -> None:
    """Trap #3bis: SV is the video-select assignment, not the source."""
    assert parse_line("SIHDP").kind is EventKind.SOURCE
    assert parse_line("SIHDP").value == "HDP"
    assert parse_line("SIDVD").value == "DVD"
    assert parse_line("SVSOURCE").kind is EventKind.VIDEO_SELECT
    assert parse_line("SVDVD").kind is EventKind.VIDEO_SELECT
    assert parse_line("SDHDMI").kind is EventKind.INPUT_MODE
    assert parse_line("SDAUTO").value == "AUTO"
    assert parse_line("DCAUTO").kind is EventKind.DIGITAL_MODE


# --- Channel volume ----------------------------------------------------------


@pytest.mark.parametrize(
    "line, channel, db",
    [
        ("CVFL 405", "FL", -9.5),
        ("CVFR 41", "FR", -9.0),
        ("CVC 38", "C", -12.0),
        ("CVSW1 38", "SW1", -12.0),
        ("CVSW2 50", "SW2", 0.0),
        ("CVFWR 50", "FWR", 0.0),
    ],
)
def test_channel_levels(line: str, channel: str, db: float) -> None:
    event = parse_line(line)
    assert event.kind is EventKind.CHANNEL_LEVEL
    assert event.key == channel
    assert event.value == db


# --- PS parameters -----------------------------------------------------------


@pytest.mark.parametrize(
    "line, key, value",
    [
        ("PSROOM EQ:AUDYSSEY", "ROOM EQ", "AUDYSSEY"),
        ("PSROOM EQ:BYP.LR", "ROOM EQ", "BYP.LR"),
        ("PSRSTR OFF", "RSTR", "OFF"),
        ("PSDYNSET EVE", "DYNSET", "EVE"),
        ("PSDYNSET NGT", "DYNSET", "NGT"),
        ("PSCINEMA EQ.ON", "CINEMA EQ", "ON"),
        ("PSCINEMA EQ.OFF", "CINEMA EQ", "OFF"),
        ("PSTONE DEFEAT ON", "TONE DEFEAT", "ON"),
        ("PSSB:MTRX ON", "SB", "MTRX ON"),
        ("PSMODE:CINEMA", "MODE", "CINEMA"),
        ("PSDRC AUTO", "DRC", "AUTO"),
        ("PSDCO OFF", "DCO", "OFF"),
        # 3D upgrade (protocol 6.0.2): a single PSDYN parameter, values from the live unit
        ("PSDYN OFF", "DYN", "OFF"),
        ("PSDYN ON", "DYN", "ON"),
        ("PSDYN VOL", "DYN", "VOL"),
        ("PSREFLEV 10", "REFLEV", "10"),
        ("PSDSX OFF", "DSX", "OFF"),
        ("PSDSX ONH", "DSX", "ONH"),
        ("PSSTW 50", "STW", "50"),
        ("PSSTH 45", "STH", "45"),
        ("PSFH:ON", "FH", "ON"),
        ("PSPHG MID", "PHG", "MID"),
        # truncated line seen in an early capture
        ("PSDYE ON", "DYN", "ON"),
    ],
)
def test_ps_parameters(line: str, key: str, value: str) -> None:
    """Trap #4: irregular separators in the PS family."""
    event = parse_line(line)
    assert event.kind is EventKind.PARAMETER, event
    assert event.key == key
    assert event.value == value


# --- Zones -------------------------------------------------------------------


@pytest.mark.parametrize(
    "line, kind, key, value",
    [
        ("Z2ON", EventKind.ZONE_POWER, "2", True),
        ("Z3OFF", EventKind.ZONE_POWER, "3", False),
        ("Z2DVD", EventKind.ZONE_SOURCE, "2", "DVD"),
        ("Z2SOURCE", EventKind.ZONE_SOURCE, "2", "SOURCE"),
        ("Z245", EventKind.ZONE_VOLUME, "2", -35.0),
        ("Z2MUON", EventKind.ZONE_MUTE, "2", True),
        ("Z2CVFL 50", EventKind.IGNORED, None, None),
    ],
)
def test_zones(line: str, kind: EventKind, key: str | None, value) -> None:
    event = parse_line(line)
    assert event.kind is kind
    if key is not None:
        assert event.key == key
        assert event.value == value


# --- Fragmentation (trap #1) -------------------------------------------------


class _FakeReader:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    async def read(self, _n: int) -> bytes:
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


class _FakeWriter:
    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass


def test_fragmented_frames_are_reassembled() -> None:
    """Exactly what the UART log showed: 'CVFL' then ' 405\\r' in two reads."""
    from denon_control.transport import TcpTransport

    lines: list[str] = []
    transport = TcpTransport("127.0.0.1", 1, on_line=lines.append)
    transport._reader = _FakeReader([b"CVFL", b" 405\rCVFR 41\rMV30\rMVMAX", b" 98\r"])  # pylint: disable=protected-access
    transport._writer = _FakeWriter()  # type: ignore[assignment]  # pylint: disable=protected-access
    transport._closed.clear()  # pylint: disable=protected-access

    asyncio.run(transport._read_loop())  # pylint: disable=protected-access

    assert lines == ["CVFL 405", "CVFR 41", "MV30", "MVMAX 98"]


# --- Full capture replay ------------------------------------------------------

CAPTURE = """
PWSTANDBY
ZMON
PWON
MV30
MVMAX 98
MSDOLBY PL2 C
CVFL 405
CVFR 41
CVC 38
CVSW1 38
CVSW2 50
CVTR 50
CVSL 40
CVSR 41
CVSBL 50
CVSBR 50
CVSB 50
CVFHL 50
CVFHR 50
CVFWL 50
CVFWR 50
MVMAX 98
SIHDP
SVSOURCE
SDHDMI
MSSTEREO
MSQUICK1
SDAUTO
SIDVD
PSRSTR OFF
SVDVD
DCAUTO
PSROOM EQ:AUDYSSEY
PSDYN VOL
PSDYNSET EVE
MV305
MV295
"""


def test_replay_capture_state() -> None:
    device = DenonDevice("127.0.0.1", 1)
    events = []
    device.add_listener(lambda _state, event: events.append(event))

    async def run() -> None:
        for line in CAPTURE.strip().splitlines():
            await device._on_line(line)  # pylint: disable=protected-access

    asyncio.run(run())

    state = device.state
    assert state.power is True
    assert state.main_zone is True
    assert state.volume_db == -50.5
    assert state.volume_max_db == 18.0
    assert state.source == "DVD"
    assert state.video_select == "DVD"
    assert state.input_mode == "AUTO"
    assert state.digital_mode == "AUTO"
    assert state.surround == "STEREO"
    assert state.quick_select == "QUICK1"
    assert state.channel_levels["FL"] == -9.5
    assert state.channel_levels["C"] == -12.0
    assert state.parameters["ROOM EQ"] == "AUDYSSEY"
    assert state.parameters["DYNSET"] == "EVE"
    assert state.parameters["DYN"] == "VOL"  # not "SET EVE" nor a separate DYNVOL key
    assert state.parameters["RSTR"] == "OFF"
    assert device.volume_percent() == 30  # (-50.5 + 80) / 98 * 100 = 30.1

    # No UNKNOWN event on the whole capture
    assert not [e for e in events if e.kind is EventKind.UNKNOWN]


def test_queries_follow_3d_upgrade_protocol() -> None:
    """The 3D upgrade (protocol 6.0.2) removed PSNIGHT and never had PSDYNEQ / PSDYNVOL.

    The live unit stays silent on those queries; PSDYN, PSDSX and PSREFLEV answer.
    """
    from denon_control.const import PS_PARAMS, STATUS_QUERIES_ON  # noqa: PLC0415

    assert "PSDYN ?" in STATUS_QUERIES_ON
    assert "PSDSX ?" in STATUS_QUERIES_ON
    for gone in ("PSNIGHT ?", "PSDYNEQ ?", "PSDYNVOL ?"):
        assert gone not in STATUS_QUERIES_ON
    for key in ("NIGHT", "DYNEQ", "DYNVOL"):
        assert key not in PS_PARAMS


def test_dynamic_volume_level_enables_dynamic_volume_first() -> None:
    """The unit ignores PSDYNSET unless PSDYN is VOL (checked live, 01/11/2026).

    Choosing Day / Evening / Midnight must first send PSDYN VOL.
    """
    sent: list[str] = []

    class _Recorder:
        async def send(self, command: str) -> None:
            sent.append(command)

    async def run() -> None:
        dev = DenonDevice("127.0.0.1")
        dev._transport = _Recorder()  # pylint: disable=protected-access
        dev.state.parameters["DYN"] = "ON"
        await dev.set_parameter("DYNSET", "DAY")
        await dev.set_parameter("DYNSET", "NGT")  # already VOL: no extra command
        await dev.send_raw("PSDYNSET ?")  # queries untouched

    asyncio.run(run())
    assert sent == ["PSDYN VOL", "PSDYNSET DAY", "PSDYNSET NGT", "PSDYNSET ?"]
