"""Constants and declarative entity definitions for the Denon RS-232 integration.

Everything the Remote can do is expressed as a *simple command* name (upper
snake case, e.g. ``SOURCE_DVD``) mapped to the raw Denon protocol string.
Selects, switches and sensors are declared as data so that adding or removing
one is a one-line change.

To trim the source list: edit ``denon_control/const.py::SOURCES``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from denon_control.const import (
    DCOMP_MODES,
    DEFAULT_TCP_PORT,
    DIGITAL_INPUT_MODES,
    DRC_MODES,
    DSX_MODES,
    DYNAMIC_EQ_MODES,
    DYNAMIC_VOLUME_SETTINGS,
    INPUT_MODES,
    MENU_COMMANDS,
    PL_MODES,
    PLIIZ_HEIGHT_GAINS,
    PS_PARAMS,
    QUICK_SELECTS,
    REFERENCE_LEVELS,
    RESTORER_MODES,
    ROOM_EQ_MODES,
    SOURCES,
    SURROUND_MODES,
    ZONE4_SOURCES,
)
from ucapi import media_player, remote

DRIVER_ID = "denon_rs232"
DEFAULT_PORT = DEFAULT_TCP_PORT


@dataclass(slots=True)
class DeviceConfig:
    """Stored configuration for one Denon unit."""

    identifier: str
    name: str
    address: str
    port: int = DEFAULT_PORT
    # Sensor values on the remote: 0 = remote default font (36 px), 1..7 = Qt <font size>
    # scale (1 = 70 %, 2 = 80 %, 3 = 100 %...); colour "#rrggbb" or a name, "" = default.
    sensor_font_size: int = 0
    sensor_color: str = ""


# --------------------------------------------------------------------------- #
# Simple commands                                                             #
# --------------------------------------------------------------------------- #


def slug(code: str) -> str:
    """``TV/CBL`` -> ``TV_CBL``, ``V.AUX`` -> ``V_AUX``, ``7CH STEREO`` -> ``7CH_STEREO``."""
    return re.sub(r"[^A-Z0-9]+", "_", code.upper()).strip("_")


def _build_simple_commands() -> dict[str, str]:
    cmds: dict[str, str] = {
        "POWER_ON": "PWON",
        "POWER_OFF": "PWSTANDBY",
        "MAIN_ZONE_ON": "ZMON",
        "MAIN_ZONE_OFF": "ZMOFF",
        "VOLUME_UP": "MVUP",
        "VOLUME_DOWN": "MVDOWN",
        "MUTE_ON": "MUON",
        "MUTE_OFF": "MUOFF",
        "CURSOR_UP": MENU_COMMANDS["cursor_up"],
        "CURSOR_DOWN": MENU_COMMANDS["cursor_down"],
        "CURSOR_LEFT": MENU_COMMANDS["cursor_left"],
        "CURSOR_RIGHT": MENU_COMMANDS["cursor_right"],
        "CURSOR_ENTER": MENU_COMMANDS["cursor_enter"],
        "RETURN": MENU_COMMANDS["back"],
        "MENU_ON": MENU_COMMANDS["menu_on"],
        "MENU_OFF": MENU_COMMANDS["menu_off"],
        "VIDEO_SELECT_SOURCE": "SVSOURCE",
    }

    for code in SOURCES:
        cmds[f"SOURCE_{slug(code)}"] = f"SI{code}"
    for code in SURROUND_MODES:
        cmds[f"SURROUND_{slug(code)}"] = f"MS{code}"
    for code in QUICK_SELECTS:
        cmds[slug(code)] = f"MS{code}"
        cmds[f"{slug(code)}_MEMORY"] = f"MS{code} MEMORY"
    for code in INPUT_MODES:
        cmds[f"INPUT_MODE_{slug(code)}"] = f"SD{code}"
    for code in DIGITAL_INPUT_MODES:
        cmds[f"DIGITAL_{slug(code)}"] = f"DC{code}"

    ps = {key: prefix for key, (prefix, _q) in PS_PARAMS.items()}
    for code in ROOM_EQ_MODES:
        cmds[f"ROOM_EQ_{slug(code)}"] = f"{ps['ROOM EQ']}{code}"
    cmds["DYN_EQ_OFF"] = f"{ps['DYN']}OFF"
    cmds["DYN_EQ_ON"] = f"{ps['DYN']}ON"
    cmds["DYN_EQ_VOL"] = f"{ps['DYN']}VOL"
    for code in DYNAMIC_VOLUME_SETTINGS:
        cmds[f"DYN_VOL_{slug(code)}"] = f"{ps['DYNSET']}{code}"
    for code in REFERENCE_LEVELS:
        cmds[f"REF_LEVEL_{code}"] = f"{ps['REFLEV']}{code}"
    cmds["DSX_OFF"] = f"{ps['DSX']}OFF"
    cmds["DSX_HEIGHT"] = f"{ps['DSX']}ONH"
    cmds["DSX_WIDE"] = f"{ps['DSX']}ONW"
    for name, key in (("STAGE_WIDTH", "STW"), ("STAGE_HEIGHT", "STH")):
        cmds[f"{name}_UP"] = f"{ps[key]}UP"
        cmds[f"{name}_DOWN"] = f"{ps[key]}DOWN"
    cmds["PLIIZ_HEIGHT_ON"] = f"{ps['FH']}ON"
    cmds["PLIIZ_HEIGHT_OFF"] = f"{ps['FH']}OFF"
    for code in PLIIZ_HEIGHT_GAINS:
        cmds[f"PLIIZ_GAIN_{slug(code)}"] = f"{ps['PHG']}{code}"
    for code in RESTORER_MODES:
        cmds[f"RESTORER_{slug(code)}"] = f"{ps['RSTR']}{code}"
    for code in PL_MODES:
        cmds[f"PL_MODE_{slug(code)}"] = f"{ps['MODE']}{code}"
    for code in DRC_MODES:
        cmds[f"DRC_{slug(code)}"] = f"{ps['DRC']}{code}"
    for code in DCOMP_MODES:
        cmds[f"DCOMP_{slug(code)}"] = f"{ps['DCO']}{code}"
    for on_off in ("ON", "OFF"):
        cmds[f"CINEMA_EQ_{on_off}"] = f"{ps['CINEMA EQ']}{on_off}"
        cmds[f"TONE_DEFEAT_{on_off}"] = f"{ps['TONE DEFEAT']}{on_off}"

    for zone in (2, 3):
        cmds[f"ZONE{zone}_ON"] = f"Z{zone}ON"
        cmds[f"ZONE{zone}_OFF"] = f"Z{zone}OFF"
        cmds[f"ZONE{zone}_VOLUME_UP"] = f"Z{zone}UP"
        cmds[f"ZONE{zone}_VOLUME_DOWN"] = f"Z{zone}DOWN"
        cmds[f"ZONE{zone}_MUTE_ON"] = f"Z{zone}MUON"
        cmds[f"ZONE{zone}_MUTE_OFF"] = f"Z{zone}MUOFF"
        cmds[f"ZONE{zone}_SOURCE_MAIN"] = f"Z{zone}SOURCE"
        for code in SOURCES:
            cmds[f"ZONE{zone}_SOURCE_{slug(code)}"] = f"Z{zone}{code}"
    cmds["ZONE4_ON"] = "Z4ON"
    cmds["ZONE4_OFF"] = "Z4OFF"
    cmds["ZONE4_SOURCE_MAIN"] = "Z4SOURCE"
    for code in ZONE4_SOURCES:
        cmds[f"ZONE4_SOURCE_{slug(code)}"] = f"Z4{code}"

    return cmds


#: simple command name -> raw Denon command (without <CR>)
SIMPLE_COMMANDS: dict[str, str] = _build_simple_commands()

# Raw pass-through: must start with a known Denon command family and stay ASCII.
# Examples accepted: "PSSB:MTRX ON", "CVFL 50", "Z2UP", "MNMEN ON", "SI?".
RAW_COMMAND_PREFIXES = (
    "PW", "ZM", "MV", "MU", "CV", "SI", "SV", "SR", "SD", "DC", "MS", "PS",
    "PV", "VS", "Z2", "Z3", "Z4", "MN", "NS", "IP", "TF", "TP", "TM", "SY",
)
RAW_COMMAND_RE = re.compile(
    r"^(?:" + "|".join(RAW_COMMAND_PREFIXES) + r")[A-Z0-9 :./?+-]{1,40}$"
)


# --------------------------------------------------------------------------- #
# Media player / remote definitions                                           #
# --------------------------------------------------------------------------- #


class MediaPlayerDef:  # pylint: disable=too-few-public-methods
    """Media player features, attributes and simple commands."""

    features = [
        media_player.Features.ON_OFF,
        media_player.Features.TOGGLE,
        media_player.Features.VOLUME,
        media_player.Features.VOLUME_UP_DOWN,
        media_player.Features.MUTE_TOGGLE,
        media_player.Features.MUTE,
        media_player.Features.UNMUTE,
        media_player.Features.DPAD,
        media_player.Features.MENU,
        media_player.Features.SELECT_SOURCE,
        media_player.Features.SELECT_SOUND_MODE,
    ]

    attributes = {
        media_player.Attributes.STATE: media_player.States.UNKNOWN,
        media_player.Attributes.VOLUME: 0,
        media_player.Attributes.MUTED: False,
        media_player.Attributes.SOURCE: "",
        media_player.Attributes.SOURCE_LIST: list(SOURCES.values()),
        media_player.Attributes.SOUND_MODE: "",
        media_player.Attributes.SOUND_MODE_LIST: list(SURROUND_MODES.values()),
    }

    simple_commands = list(SIMPLE_COMMANDS)


class RemoteDef:  # pylint: disable=too-few-public-methods
    """Remote features, attributes and simple commands."""

    features = [
        remote.Features.SEND_CMD,
        remote.Features.ON_OFF,
        remote.Features.TOGGLE,
    ]

    attributes = {
        remote.Attributes.STATE: remote.States.UNKNOWN,
    }

    simple_commands = list(SIMPLE_COMMANDS)


# --------------------------------------------------------------------------- #
# Selects                                                                     #
# --------------------------------------------------------------------------- #

SelectKind = Literal[
    "source", "surround", "input_mode", "digital_mode", "quick", "ps", "zone_source"
]


@dataclass(frozen=True, slots=True)
class SelectConfig:
    """One select entity: how to read it and how to set it."""

    identifier: str
    name: str
    kind: SelectKind
    options: dict[str, str]  # protocol code -> label
    key: str | None = None  # PS key or zone number


ZONE_SOURCE_OPTIONS = {"SOURCE": "Main zone", **SOURCES}
ZONE4_SOURCE_OPTIONS = {"SOURCE": "Main zone", **ZONE4_SOURCES}

SELECTS: tuple[SelectConfig, ...] = (
    SelectConfig("source", "Source", "source", SOURCES),
    SelectConfig("surround_mode", "Surround Mode", "surround", SURROUND_MODES),
    SelectConfig("input_mode", "Input Mode", "input_mode", INPUT_MODES),
    SelectConfig("digital_mode", "Digital Input Mode", "digital_mode", DIGITAL_INPUT_MODES),
    SelectConfig("quick_select", "Quick Select", "quick", QUICK_SELECTS),
    SelectConfig("room_eq", "Room EQ", "ps", ROOM_EQ_MODES, key="ROOM EQ"),
    SelectConfig("dynamic_eq", "Dynamic EQ", "ps", DYNAMIC_EQ_MODES, key="DYN"),
    SelectConfig("dynamic_volume", "Dynamic Volume", "ps", DYNAMIC_VOLUME_SETTINGS, key="DYNSET"),
    SelectConfig("reference_level", "Reference Level", "ps", REFERENCE_LEVELS, key="REFLEV"),
    SelectConfig("dsx", "Audyssey DSX", "ps", DSX_MODES, key="DSX"),
    SelectConfig("pliiz_gain", "PLIIz Height Gain", "ps", PLIIZ_HEIGHT_GAINS, key="PHG"),
    SelectConfig("audio_restorer", "Audio Restorer", "ps", RESTORER_MODES, key="RSTR"),
    SelectConfig("pl_mode", "PL Mode", "ps", PL_MODES, key="MODE"),
    SelectConfig("drc", "DRC", "ps", DRC_MODES, key="DRC"),
    SelectConfig("dcomp", "D.COMP", "ps", DCOMP_MODES, key="DCO"),
    SelectConfig("zone2_source", "Zone 2 Source", "zone_source", ZONE_SOURCE_OPTIONS, key="2"),
    SelectConfig("zone3_source", "Zone 3 Source", "zone_source", ZONE_SOURCE_OPTIONS, key="3"),
    SelectConfig("zone4_source", "Zone 4 Source", "zone_source", ZONE4_SOURCE_OPTIONS, key="4"),
)

SELECT_IDS = tuple(s.identifier for s in SELECTS)
SELECT_BY_ID = {s.identifier: s for s in SELECTS}


# --------------------------------------------------------------------------- #
# Switches                                                                    #
# --------------------------------------------------------------------------- #

SwitchKind = Literal["mute", "main_zone", "ps", "zone_power", "zone_mute"]


@dataclass(frozen=True, slots=True)
class SwitchConfig:
    """One switch entity."""

    identifier: str
    name: str
    kind: SwitchKind
    key: str | None = None  # PS key or zone number


SWITCHES: tuple[SwitchConfig, ...] = (
    SwitchConfig("mute", "Mute", "mute"),
    SwitchConfig("main_zone", "Main Zone", "main_zone"),
    SwitchConfig("pliiz_height", "PLIIz Height", "ps", key="FH"),
    SwitchConfig("cinema_eq", "Cinema EQ", "ps", key="CINEMA EQ"),
    SwitchConfig("tone_defeat", "Tone Defeat", "ps", key="TONE DEFEAT"),
    SwitchConfig("zone2_power", "Zone 2", "zone_power", key="2"),
    SwitchConfig("zone3_power", "Zone 3", "zone_power", key="3"),
    SwitchConfig("zone4_power", "Zone 4", "zone_power", key="4"),
    SwitchConfig("zone2_mute", "Zone 2 Mute", "zone_mute", key="2"),
    SwitchConfig("zone3_mute", "Zone 3 Mute", "zone_mute", key="3"),
)

SWITCH_IDS = tuple(s.identifier for s in SWITCHES)
SWITCH_BY_ID = {s.identifier: s for s in SWITCHES}


# --------------------------------------------------------------------------- #
# Sensors                                                                     #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class SensorConfig:
    """One sensor entity."""

    identifier: str
    name: str
    unit: str | None = None
    default: str = ""
    labels: dict[str, str] = field(default_factory=dict)  # code -> label, optional
    # Indicator sensors: "direct" / "pure_direct" light up while the unit decodes in that mode
    indicator: str = ""


SENSORS: tuple[SensorConfig, ...] = (
    SensorConfig("volume_db", "Master Volume", unit="dB", default="-80.0"),
    SensorConfig("source", "Current Source", labels=SOURCES),
    SensorConfig("surround_mode", "Surround Mode"),
    SensorConfig("input_mode", "Input Mode", labels=INPUT_MODES),
    SensorConfig("digital_mode", "Digital Input Mode", labels=DIGITAL_INPUT_MODES),
    SensorConfig("quick_select", "Quick Select", labels=QUICK_SELECTS),
    SensorConfig("room_eq", "Room EQ", labels=ROOM_EQ_MODES),
    SensorConfig("dynamic_eq", "Dynamic EQ", labels=DYNAMIC_EQ_MODES),
    SensorConfig("dynamic_volume", "Dynamic Volume", labels=DYNAMIC_VOLUME_SETTINGS),
    SensorConfig("dsx", "Audyssey DSX", labels=DSX_MODES),
    SensorConfig("audio_restorer", "Audio Restorer", labels=RESTORER_MODES),
    SensorConfig("zone2_source", "Zone 2 Source", labels=ZONE_SOURCE_OPTIONS),
    SensorConfig("zone2_volume_db", "Zone 2 Volume", unit="dB"),
    SensorConfig("direct", "Direct", indicator="direct"),
    SensorConfig("pure_direct", "Pure Direct", indicator="pure_direct"),
)

# Indicator sensors: a lamp ("●", in the remote's large sensor font) in this colour while the mode
# is on, grey otherwise. The button above it carries the name.
INDICATOR_ON_COLOR = "#4da6ff"
INDICATOR_OFF_COLOR = "#5a5a5a"

SENSOR_IDS = tuple(s.identifier for s in SENSORS)
SENSOR_BY_ID = {s.identifier: s for s in SENSORS}
