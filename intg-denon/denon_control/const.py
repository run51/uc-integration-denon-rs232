"""Denon AVP-A1HD RS-232 protocol tables.

Source: "DENON AVP control protocol" Rev 6.0.2 for the AVP-A1HD *3D upgrade*
(SPK-592, November 2011) plus observed behaviour of the unit on live RS-232
captures.  The upgrade added Audyssey DSX, Dynamic EQ reference level, Dolby
PLIIz height and DTS Neo:X, merged Dynamic EQ / Dynamic Volume into a single
``PSDYN`` parameter and removed Night mode (``PSNIGHT``).

Every command is ASCII, terminated by <CR> (0x0D).  The unit answers each
query with a RESPONSE and pushes unsolicited EVENTs whenever its state changes.
"""

from __future__ import annotations

CR = "\r"

# --- Serial / link parameters -------------------------------------------------
BAUD_RATE = 9600
DEFAULT_TCP_PORT = 5000  # Unfolded Circle Dock 3 external port 2 (port 1 = 4999)

# Protocol note K): wait 4 s after a power-on command before sending anything else.
POWER_ON_SETTLE_S = 4.0
# Minimum gap between two commands on the 9600 bps link.
COMMAND_GAP_S = 0.06

# --- Master volume -----------------------------------------------------------
# "MV**": 00..99, 80 = 0 dB, 99 = "---" (minimum).  Three digits = half step:
#   MV805 = +0.5 dB, MV795 = -0.5 dB.  Two digits at whole dB steps.
VOLUME_ZERO_DB_CODE = 80
VOLUME_MIN_DB = -80.0
VOLUME_DEFAULT_MAX_CODE = 98  # reported by "MVMAX 98" on this unit → +18 dB

# --- Channel volume ----------------------------------------------------------
# "CVxx **": 38..62, 50 = 0 dB, three digits = half step (CVFL 405 = -9.5 dB).
CHANNEL_ZERO_DB_CODE = 50

CHANNEL_NAMES: dict[str, str] = {
    "FL": "Front L",
    "FR": "Front R",
    "C": "Center",
    "SW1": "Subwoofer 1",
    "SW2": "Subwoofer 2",
    "SW3": "Subwoofer 3",
    "SL": "Surround L",
    "SR": "Surround R",
    "SBL": "Surround Back L",
    "SBR": "Surround Back R",
    "SB": "Surround Back",
    "FHL": "Front Height L",
    "FHR": "Front Height R",
    "FWL": "Front Wide L",
    "FWR": "Front Wide R",
    "TR": "Transducer",
}

# --- Input sources (SI) ------------------------------------------------------
# Protocol code -> human label.  Order = display order.
# XM and HDRADIO exist on North-America units only and are left out on purpose.
SOURCES: dict[str, str] = {
    "PHONO": "Phono",
    "CD": "CD",
    "TUNER": "Tuner",
    "DVD": "DVD",
    "HDP": "HDP",
    "TV/CBL": "TV/CBL",
    "SAT": "SAT",
    "VCR": "VCR",
    "DVR-1": "DVR-1",
    "DVR-2": "DVR-2",
    "V.AUX": "V.AUX",
    "NET/USB": "NET/USB",
    "IPOD": "iPod",
}

# Zone 4 only accepts sources that carry a digital input (protocol p.22).
ZONE4_SOURCES: dict[str, str] = {
    "CD": "CD",
    "TUNER": "Tuner",
    "DVD": "DVD",
    "HDP": "HDP",
    "TV/CBL": "TV/CBL",
    "SAT": "SAT",
    "VCR": "VCR",
    "DVR-1": "DVR-1",
    "DVR-2": "DVR-2",
    "V.AUX": "V.AUX",
}

# --- Surround modes (MS) -----------------------------------------------------
# Settable modes.  The unit *reports* more specific names (e.g. "DOLBY PL2 C",
# "DOLBY HD", "DTS HD MSTR") that cannot be set directly; they are kept as the
# current sound_mode even when absent from this list.
SURROUND_MODES: dict[str, str] = {
    "DIRECT": "Direct",
    "PURE DIRECT": "Pure Direct",
    "STEREO": "Stereo",
    "STANDARD": "Standard",
    "DOLBY DIGITAL": "Dolby Digital",
    "DTS SURROUND": "DTS Surround",
    "DOLBY H/P": "Dolby Headphone",
    "HOME THX CINEMA": "THX Cinema",
    "WIDE SCREEN": "Wide Screen",
    "7CH STEREO": "7ch Stereo",
    "SUPER STADIUM": "Super Stadium",
    "ROCK ARENA": "Rock Arena",
    "JAZZ CLUB": "Jazz Club",
    "CLASSIC CONCERT": "Classic Concert",
    "MONO MOVIE": "Mono Movie",
    "MATRIX": "Matrix",
    "VIDEO GAME": "Video Game",
}

# Response values starting with these prefixes under "MS" are NOT surround modes.
MS_NON_MODE_PREFIXES = ("QUICK",)

QUICK_SELECTS: dict[str, str] = {
    "QUICK1": "Quick 1",
    "QUICK2": "Quick 2",
    "QUICK3": "Quick 3",
}

# --- Input mode (SD) / digital input mode (DC) -------------------------------
INPUT_MODES: dict[str, str] = {
    "AUTO": "Auto",
    "HDMI": "HDMI",
    "DIGITAL": "Digital",
    "ANALOG": "Analog",
    "EXT.IN-1": "EXT.IN",
}

DIGITAL_INPUT_MODES: dict[str, str] = {
    "AUTO": "Auto",
    "PCM": "PCM",
    "DTS": "DTS",
}

# --- PS parameters -----------------------------------------------------------
# The PS family is irregular: the separator between key and value differs
# ("ROOM EQ:AUDYSSEY", "CINEMA EQ.ON", "DSX ONH", "SB:MTRX ON").
#
# Each entry:  canonical key -> (command prefix, query string, separator used by
# the unit in its responses).  The parser matches responses against the command
# prefix (longest first) and strips the separator.
#
# Prefixes are matched longest first, so "PSDYNSET EVE" is never read as
# "PSDYN" with value "SET EVE".
PS_PARAMS: dict[str, tuple[str, str]] = {
    # key:        (command prefix incl. separator, query)
    "ROOM EQ": ("PSROOM EQ:", "PSROOM EQ: ?"),
    "CINEMA EQ": ("PSCINEMA EQ.", "PSCINEMA EQ. ?"),
    "TONE DEFEAT": ("PSTONE DEFEAT ", "PSTONE DEFEAT ?"),
    "DYN": ("PSDYN ", "PSDYN ?"),  # OFF / ON (Dyn EQ) / VOL (Dyn EQ + Dyn Volume)
    "DYNSET": ("PSDYNSET ", "PSDYNSET ?"),
    "REFLEV": ("PSREFLEV ", "PSREFLEV ?"),
    "DSX": ("PSDSX ", "PSDSX ?"),
    "STW": ("PSSTW ", "PSSTW ?"),
    "STH": ("PSSTH ", "PSSTH ?"),
    "FH": ("PSFH:", "PSFH: ?"),
    "PHG": ("PSPHG ", "PSPHG ?"),
    "RSTR": ("PSRSTR ", "PSRSTR ?"),
    "MODE": ("PSMODE:", "PSMODE: ?"),
    "SB": ("PSSB:", "PSSB: ?"),
    "DEC": ("PSDEC:", "PSDEC: ?"),
    "DEH": ("PSDEH:", "PSDEH: ?"),
    "DRC": ("PSDRC ", "PSDRC ?"),
    "DCO": ("PSDCO ", "PSDCO ?"),
    "LFE": ("PSLFE ", "PSLFE ?"),
    "EFF": ("PSEFF ", "PSEFF ?"),
    "DEL": ("PSDEL ", "PSDEL ?"),
    "DELAY": ("PSDELAY ", "PSDELAY ?"),
    "CEN": ("PSCEN ", "PSCEN ?"),
    "CEI": ("PSCEI ", "PSCEI ?"),
    "ATT": ("PSATT ", "PSATT ?"),
    "SWR": ("PSSWR ", "PSSWR ?"),
    "RSZ": ("PSRSZ ", "PSRSZ ?"),
    "INP": ("PSINP ", "PSINP ?"),
    "BAS": ("PSBAS ", "PSBAS ?"),
    "TRE": ("PSTRE ", "PSTRE ?"),
}

# Response-side aliases -> canonical key (firmware quirks observed in captures).
PS_RESPONSE_ALIASES: dict[str, str] = {
    "DYE": "DYN",  # truncated "PSDYE ON" seen in an early capture
}

ROOM_EQ_MODES: dict[str, str] = {
    "AUDYSSEY": "Audyssey",
    "BYP.LR": "Bypass L/R",
    "FLAT": "Flat",
    "MANUAL": "Manual",
    "OFF": "Off",
}

# PSDYN: a single parameter since the 3D upgrade (protocol 6.0.2 p.15).
DYNAMIC_EQ_MODES: dict[str, str] = {
    "OFF": "Off",
    "ON": "Dynamic EQ",
    "VOL": "Dynamic EQ + Volume",
}

DYNAMIC_VOLUME_SETTINGS: dict[str, str] = {
    "DAY": "Day",
    "EVE": "Evening",
    "NGT": "Midnight",
}

# Dynamic EQ reference level offset (dB).
REFERENCE_LEVELS: dict[str, str] = {
    "0": "0 dB",
    "5": "5 dB",
    "10": "10 dB",
    "15": "15 dB",
}

# Audyssey DSX ("3D"): height or wide channels.
DSX_MODES: dict[str, str] = {
    "OFF": "Off",
    "ONH": "Height",
    "ONW": "Wide",
}

# Dolby PLIIz height gain.
PLIIZ_HEIGHT_GAINS: dict[str, str] = {
    "LOW": "Low",
    "MID": "Mid",
    "HI": "High",
}

# Stage width / height (Audyssey DSX): 40..60, 50 = 0 dB.
STAGE_ZERO_DB_CODE = 50

RESTORER_MODES: dict[str, str] = {
    "OFF": "Off",
    "MODE1": "Mode 1",
    "MODE2": "Mode 2",
    "MODE3": "Mode 3",
}

PL_MODES: dict[str, str] = {
    "CINEMA": "Cinema",
    "MUSIC": "Music",
    "GAME": "Game",
    "PRO LOGIC": "Pro Logic",
}

DRC_MODES: dict[str, str] = {
    "AUTO": "Auto",
    "LOW": "Low",
    "MID": "Mid",
    "HI": "High",
    "OFF": "Off",
}

DCOMP_MODES: dict[str, str] = {
    "OFF": "Off",
    "LOW": "Low",
    "MID": "Mid",
    "HIGH": "High",
}

# --- Cursor / menu (MN) ------------------------------------------------------
MENU_COMMANDS: dict[str, str] = {
    "cursor_up": "MNCUP",
    "cursor_down": "MNCDN",
    "cursor_left": "MNCLT",
    "cursor_right": "MNCRT",
    "cursor_enter": "MNENT",
    "back": "MNRTN",
    "menu_on": "MNMEN ON",
    "menu_off": "MNMEN OFF",
}

# --- Zones -------------------------------------------------------------------
ZONES = (2, 3, 4)

# --- Queries sent after connect / on periodic refresh -----------------------
STATUS_QUERIES_BASE = ("PW?", "ZM?")
STATUS_QUERIES_ON = (
    "MV?",
    "MU?",
    "SI?",
    "MS?",
    "CV?",
    "SD?",
    "DC?",
    "MSQUICK ?",
    "PSROOM EQ: ?",
    "PSDYN ?",
    "PSDYNSET ?",
    "PSREFLEV ?",
    "PSDSX ?",
    "PSSTW ?",
    "PSSTH ?",
    "PSFH: ?",
    "PSPHG ?",
    "PSRSTR ?",
    "PSCINEMA EQ. ?",
    "PSTONE DEFEAT ?",
    "PSMODE: ?",
    "PSDRC ?",
    "PSDCO ?",
    "Z2?",
    "Z2MU?",
    "Z3?",
    "Z3MU?",
    "Z4?",
)
