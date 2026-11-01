"""Stateless parser: one Denon response/event line -> one typed ``DenonEvent``.

Traps handled here (all observed on a real AVP-A1HD capture):

* ``MVMAX 98`` follows every ``MV`` response and must not be read as a volume.
* ``MSQUICK1`` uses the ``MS`` prefix but is a Quick Select, not a surround mode.
* ``SVDVD`` / ``SVSOURCE`` are the video-select assignment, not the input source.
* ``PS`` parameters use inconsistent separators (``ROOM EQ:AUDYSSEY``,
  ``CINEMA EQ.ON``, ``DSX ONH``); ``PSDYN VOL`` is the Dynamic EQ parameter
  (value ``VOL``), not ``PSDYNSET``.
* ``Z2 45`` is a zone volume, ``Z2DVD`` a zone source, ``Z2ON`` a zone power.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .const import (
    CHANNEL_ZERO_DB_CODE,
    MS_NON_MODE_PREFIXES,
    PS_PARAMS,
    PS_RESPONSE_ALIASES,
    VOLUME_ZERO_DB_CODE,
)


class EventKind(StrEnum):
    """Categories of parsed lines."""

    POWER = "power"  # value: bool
    MAIN_ZONE = "main_zone"  # value: bool
    VOLUME = "volume"  # value: float dB  (extra: code)
    VOLUME_MAX = "volume_max"  # value: float dB
    MUTE = "mute"  # value: bool
    SOURCE = "source"  # value: str code
    VIDEO_SELECT = "video_select"  # value: str
    RECORD_SELECT = "record_select"  # value: str
    INPUT_MODE = "input_mode"  # value: str
    DIGITAL_MODE = "digital_mode"  # value: str
    SURROUND = "surround"  # value: str
    QUICK_SELECT = "quick_select"  # value: str ("QUICK1")
    CHANNEL_LEVEL = "channel_level"  # key: channel, value: float dB
    PARAMETER = "parameter"  # key: PS key, value: str
    VIDEO_SETTING = "video_setting"  # key/value raw (VS)
    ZONE_POWER = "zone_power"  # key: zone, value: bool
    ZONE_SOURCE = "zone_source"  # key: zone, value: str
    ZONE_VOLUME = "zone_volume"  # key: zone, value: float dB
    ZONE_MUTE = "zone_mute"  # key: zone, value: bool
    IGNORED = "ignored"  # known but unused
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DenonEvent:
    """Parsed line."""

    kind: EventKind
    value: Any = None
    key: str | None = None
    raw: str = ""


_VOLUME_RE = re.compile(r"^(\d{2})(\d)?$")
_ZONE_RE = re.compile(r"^Z([234])(.*)$")
_PS_PREFIXES = sorted(
    ((prefix, key) for key, (prefix, _query) in PS_PARAMS.items()),
    key=lambda item: len(item[0]),
    reverse=True,
)


def decode_level(code: str, zero_code: int) -> float | None:
    """Decode a Denon two/three-digit level into dB.

    ``80`` -> 0.0, ``805`` -> +0.5, ``795`` -> -0.5 (for zero_code=80).
    Returns None when the code is not numeric.
    """
    match = _VOLUME_RE.match(code.strip())
    if not match:
        return None
    whole = int(match.group(1))
    half = 0.5 if match.group(2) == "5" else 0.0
    return float(whole - zero_code) + half


def encode_level(db: float, zero_code: int, min_code: int = 0, max_code: int = 99) -> str:
    """Encode a dB value into the Denon two/three-digit format."""
    steps = round(db * 2) / 2  # snap to 0.5 dB
    code = zero_code + steps
    code = max(min_code, min(max_code, code))
    whole = int(code)
    if code - whole >= 0.5:
        return f"{whole:02d}5"
    return f"{whole:02d}"


def _on_off(value: str) -> bool | None:
    value = value.strip().upper()
    if value == "ON":
        return True
    if value in {"OFF", "STANDBY"}:
        return False
    return None


def parse_line(line: str) -> DenonEvent:  # pylint: disable=too-many-return-statements,too-many-branches
    """Parse one CR-terminated line (without the CR)."""
    raw = line.strip()
    if not raw:
        return DenonEvent(EventKind.IGNORED, raw=raw)

    head = raw[:2]
    body = raw[2:]

    # --- Power / main zone --------------------------------------------------
    if head == "PW":
        state = _on_off(body)
        if state is None:
            return DenonEvent(EventKind.UNKNOWN, raw=raw)
        return DenonEvent(EventKind.POWER, state, raw=raw)

    if head == "ZM":
        state = _on_off(body)
        if state is None:
            return DenonEvent(EventKind.UNKNOWN, raw=raw)
        return DenonEvent(EventKind.MAIN_ZONE, state, raw=raw)

    # --- Master volume ------------------------------------------------------
    if head == "MV":
        if body.startswith("MAX"):
            level = decode_level(body[3:], VOLUME_ZERO_DB_CODE)
            if level is None:
                return DenonEvent(EventKind.UNKNOWN, raw=raw)
            return DenonEvent(EventKind.VOLUME_MAX, level, raw=raw)
        level = decode_level(body, VOLUME_ZERO_DB_CODE)
        if level is None:
            return DenonEvent(EventKind.UNKNOWN, raw=raw)
        return DenonEvent(EventKind.VOLUME, level, key=body.strip(), raw=raw)

    if head == "MU":
        state = _on_off(body)
        if state is None:
            return DenonEvent(EventKind.UNKNOWN, raw=raw)
        return DenonEvent(EventKind.MUTE, state, raw=raw)

    # --- Channel volume -----------------------------------------------------
    if head == "CV":
        parts = body.strip().split(None, 1)
        if len(parts) != 2:
            return DenonEvent(EventKind.UNKNOWN, raw=raw)
        level = decode_level(parts[1], CHANNEL_ZERO_DB_CODE)
        if level is None:
            return DenonEvent(EventKind.UNKNOWN, raw=raw)
        return DenonEvent(EventKind.CHANNEL_LEVEL, level, key=parts[0].upper(), raw=raw)

    # --- Sources / modes ----------------------------------------------------
    if head == "SI":
        return DenonEvent(EventKind.SOURCE, body.strip().upper(), raw=raw)

    if head == "SV":
        return DenonEvent(EventKind.VIDEO_SELECT, body.strip().upper(), raw=raw)

    if head == "SR":
        return DenonEvent(EventKind.RECORD_SELECT, body.strip().upper(), raw=raw)

    if head == "SD":
        return DenonEvent(EventKind.INPUT_MODE, body.strip().upper(), raw=raw)

    if head == "DC":
        return DenonEvent(EventKind.DIGITAL_MODE, body.strip().upper(), raw=raw)

    if head == "MS":
        value = body.strip().upper()
        if value.startswith(MS_NON_MODE_PREFIXES):
            # "MSQUICK1" (and "MSQUICK1 MEMORY" acknowledgements)
            return DenonEvent(EventKind.QUICK_SELECT, value.split()[0], raw=raw)
        return DenonEvent(EventKind.SURROUND, value, raw=raw)

    # --- PS parameters ------------------------------------------------------
    if head == "PS":
        return _parse_ps(raw)

    if head == "PV":
        return DenonEvent(EventKind.IGNORED, raw=raw)

    if head == "VS":
        return DenonEvent(EventKind.VIDEO_SETTING, body.strip(), raw=raw)

    # --- Zones --------------------------------------------------------------
    zone = _ZONE_RE.match(raw)
    if zone:
        return _parse_zone(int(zone.group(1)), zone.group(2).strip(), raw)

    # --- Known noise --------------------------------------------------------
    if head in {"NS", "IP", "TF", "TP", "TM", "SY", "RM"}:
        return DenonEvent(EventKind.IGNORED, raw=raw)

    return DenonEvent(EventKind.UNKNOWN, raw=raw)


def _parse_ps(raw: str) -> DenonEvent:
    """Parse the irregular PS family."""
    upper = raw.upper()

    for prefix, key in _PS_PREFIXES:
        if upper.startswith(prefix.upper()):
            value = raw[len(prefix) :].strip()
            return DenonEvent(EventKind.PARAMETER, value, key=key, raw=raw)

    # Firmware quirks: "PSDYE ON"
    body = raw[2:]
    for alias, key in PS_RESPONSE_ALIASES.items():
        if body.upper().startswith(alias):
            value = body[len(alias) :].strip().lstrip(":. ")
            return DenonEvent(EventKind.PARAMETER, value, key=key, raw=raw)

    # Generic fallback: split at first separator
    match = re.match(r"^([A-Z]+)[\s:.]+(.*)$", body.strip(), re.IGNORECASE)
    if match:
        return DenonEvent(
            EventKind.PARAMETER, match.group(2).strip(), key=match.group(1).upper(), raw=raw
        )
    return DenonEvent(EventKind.UNKNOWN, raw=raw)


def _parse_zone(zone: int, body: str, raw: str) -> DenonEvent:
    """Parse Z2/Z3/Z4 lines."""
    key = str(zone)
    upper = body.upper()

    if upper.startswith("MU"):
        state = _on_off(upper[2:])
        if state is None:
            return DenonEvent(EventKind.UNKNOWN, raw=raw)
        return DenonEvent(EventKind.ZONE_MUTE, state, key=key, raw=raw)

    if upper.startswith(("CV", "PS", "CS")):
        return DenonEvent(EventKind.IGNORED, raw=raw)

    state = _on_off(upper)
    if state is not None:
        return DenonEvent(EventKind.ZONE_POWER, state, key=key, raw=raw)

    level = decode_level(upper, VOLUME_ZERO_DB_CODE)
    if level is not None:
        return DenonEvent(EventKind.ZONE_VOLUME, level, key=key, raw=raw)

    if upper:
        return DenonEvent(EventKind.ZONE_SOURCE, upper, key=key, raw=raw)

    return DenonEvent(EventKind.UNKNOWN, raw=raw)
