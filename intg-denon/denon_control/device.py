"""Denon AVP-A1HD state model and high-level commands.

``DenonDevice`` owns a ``TcpTransport``, feeds every received line through
``parse_line`` and keeps a ``DenonState`` up to date.  Whoever is interested
registers a callback with ``add_listener`` and gets ``(state, event)`` for every
state-changing line.

The class knows nothing about Unfolded Circle — it can be reused from a Home
Assistant integration or a CLI.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .const import (
    DEFAULT_TCP_PORT,
    POWER_ON_SETTLE_S,
    STATUS_QUERIES_BASE,
    STATUS_QUERIES_ON,
    VOLUME_DEFAULT_MAX_CODE,
    VOLUME_MIN_DB,
    VOLUME_ZERO_DB_CODE,
    ZONES,
)
from .protocol import DenonEvent, EventKind, encode_level, parse_line
from .transport import TcpTransport

_LOG = logging.getLogger(__name__)

Listener = Callable[["DenonState", DenonEvent], Awaitable[None] | None]


@dataclass(slots=True)
class ZoneState:
    """State of one auxiliary zone."""

    power: bool | None = None
    source: str | None = None
    volume_db: float | None = None
    muted: bool | None = None


@dataclass(slots=True)
class DenonState:  # pylint: disable=too-many-instance-attributes
    """Everything we know about the unit."""

    power: bool | None = None  # PW
    main_zone: bool | None = None  # ZM
    volume_db: float | None = None  # MV
    volume_max_db: float = float(VOLUME_DEFAULT_MAX_CODE - VOLUME_ZERO_DB_CODE)
    muted: bool | None = None  # MU
    source: str | None = None  # SI
    video_select: str | None = None  # SV
    record_select: str | None = None  # SR
    input_mode: str | None = None  # SD
    digital_mode: str | None = None  # DC
    surround: str | None = None  # MS
    quick_select: str | None = None  # MSQUICKn
    channel_levels: dict[str, float] = field(default_factory=dict)  # CV
    parameters: dict[str, str] = field(default_factory=dict)  # PS
    video_settings: dict[str, str] = field(default_factory=dict)  # VS
    zones: dict[int, ZoneState] = field(
        default_factory=lambda: {zone: ZoneState() for zone in ZONES}
    )

    @property
    def is_on(self) -> bool:
        """True when the unit is powered on (not standby)."""
        return bool(self.power)

    def parameter(self, key: str) -> str | None:
        """Return a PS parameter value."""
        return self.parameters.get(key)


class DenonDevice:  # pylint: disable=too-many-public-methods
    """High-level Denon controller over a TCP serial bridge."""

    def __init__(self, host: str, port: int = DEFAULT_TCP_PORT) -> None:
        self._transport = TcpTransport(host, port, on_line=self._on_line)
        self._state = DenonState()
        self._listeners: list[Listener] = []
        self._unknown_seen: set[str] = set()

    # ------------------------------------------------------------ properties

    @property
    def state(self) -> DenonState:
        """Current state snapshot (mutable, do not modify)."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """True while the TCP link is up."""
        return self._transport.is_connected

    @property
    def host(self) -> str:
        """Bridge host."""
        return self._transport.host

    @property
    def port(self) -> int:
        """Bridge port."""
        return self._transport.port

    def add_listener(self, listener: Listener) -> None:
        """Register a state-change listener."""
        self._listeners.append(listener)

    def remove_listener(self, listener: Listener) -> None:
        """Unregister a listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    # ------------------------------------------------------------- lifecycle

    async def connect(self) -> None:
        """Open the link."""
        await self._transport.connect()

    async def disconnect(self) -> None:
        """Close the link."""
        await self._transport.disconnect()

    async def wait_closed(self) -> None:
        """Block until the link drops."""
        await self._transport.wait_closed()

    # -------------------------------------------------------------- raw I/O

    async def send_raw(self, command: str) -> None:
        """Send a raw protocol command (without <CR>)."""
        upper = command.upper()
        if (
            upper.startswith("PSDYNSET ")
            and not upper.endswith("?")
            and self._state.parameters.get("DYN") != "VOL"
        ):
            # The unit ignores PSDYNSET unless Dynamic Volume is enabled
            # (PSDYN VOL): enable it first, as choosing a level implies it.
            await self._transport.send("PSDYN VOL")
            self._state.parameters["DYN"] = "VOL"
        await self._transport.send(command)
        if command.upper() == "PWON":
            self._transport.hold_for(POWER_ON_SETTLE_S)

    async def query_status(self, *, full: bool | None = None) -> None:
        """Ask the unit for its state.

        ``full=None`` queries the base set then, if the unit is on (or its power
        state is unknown), the full set.
        """
        for query in STATUS_QUERIES_BASE:
            await self._transport.send(query)

        if full is False:
            return
        if full is None and self._state.power is False:
            return

        for query in STATUS_QUERIES_ON:
            await self._transport.send(query)

    # --------------------------------------------------------------- power

    async def power_on(self) -> None:
        """System power on."""
        await self.send_raw("PWON")

    async def power_off(self) -> None:
        """System standby."""
        await self.send_raw("PWSTANDBY")

    async def power_toggle(self) -> None:
        """Toggle based on last known state."""
        if self._state.power:
            await self.power_off()
        else:
            await self.power_on()

    async def main_zone(self, on: bool) -> None:
        """Main zone on/off."""
        await self.send_raw("ZMON" if on else "ZMOFF")

    # -------------------------------------------------------------- volume

    async def volume_up(self) -> None:
        """Master volume +0.5 dB."""
        await self.send_raw("MVUP")

    async def volume_down(self) -> None:
        """Master volume -0.5 dB."""
        await self.send_raw("MVDOWN")

    async def set_volume_db(self, db: float) -> None:
        """Set master volume in dB (-80 .. max)."""
        db = max(VOLUME_MIN_DB, min(self._state.volume_max_db, db))
        code = encode_level(
            db,
            VOLUME_ZERO_DB_CODE,
            max_code=int(self._state.volume_max_db + VOLUME_ZERO_DB_CODE),
        )
        await self.send_raw(f"MV{code}")

    def volume_percent(self) -> int | None:
        """Master volume as 0..100 over the -80 dB .. MVMAX range."""
        if self._state.volume_db is None:
            return None
        span = self._state.volume_max_db - VOLUME_MIN_DB
        pct = (self._state.volume_db - VOLUME_MIN_DB) / span * 100
        return int(round(max(0.0, min(100.0, pct))))

    def percent_to_db(self, percent: float) -> float:
        """Inverse of ``volume_percent``."""
        span = self._state.volume_max_db - VOLUME_MIN_DB
        return VOLUME_MIN_DB + (max(0.0, min(100.0, percent)) / 100.0) * span

    async def set_volume_percent(self, percent: float) -> None:
        """Set master volume from a 0..100 value."""
        await self.set_volume_db(self.percent_to_db(percent))

    async def mute(self, on: bool) -> None:
        """Main zone mute."""
        await self.send_raw("MUON" if on else "MUOFF")

    async def mute_toggle(self) -> None:
        """Toggle mute based on last known state."""
        await self.mute(not self._state.muted)

    async def set_channel_level_db(self, channel: str, db: float) -> None:
        """Channel volume (38..62, 50 = 0 dB)."""
        code = encode_level(db, 50, min_code=38, max_code=62)
        await self.send_raw(f"CV{channel.upper()} {code}")

    # ------------------------------------------------------------- sources

    async def select_source(self, code: str) -> None:
        """Select input source by protocol code (e.g. ``DVD``, ``TV/CBL``)."""
        await self.send_raw(f"SI{code.upper()}")

    async def select_surround(self, code: str) -> None:
        """Select surround mode by protocol code (e.g. ``STEREO``)."""
        await self.send_raw(f"MS{code.upper()}")

    async def quick_select(self, number: int) -> None:
        """Recall Quick Select 1..3."""
        await self.send_raw(f"MSQUICK{number}")

    async def quick_select_memory(self, number: int) -> None:
        """Store current setup into Quick Select 1..3."""
        await self.send_raw(f"MSQUICK{number} MEMORY")

    async def set_input_mode(self, code: str) -> None:
        """SD: AUTO / HDMI / DIGITAL / ANALOG / EXT.IN-1."""
        await self.send_raw(f"SD{code.upper()}")

    async def set_digital_mode(self, code: str) -> None:
        """DC: AUTO / PCM / DTS."""
        await self.send_raw(f"DC{code.upper()}")

    async def set_video_select(self, code: str) -> None:
        """SV: video select source or SOURCE to cancel."""
        await self.send_raw(f"SV{code.upper()}")

    # ---------------------------------------------------------- parameters

    async def set_parameter(self, key: str, value: str) -> None:
        """Set a PS parameter using its canonical key (see const.PS_PARAMS)."""
        from .const import PS_PARAMS  # pylint: disable=import-outside-toplevel

        if key not in PS_PARAMS:
            raise ValueError(f"Unknown PS parameter: {key}")
        prefix, _query = PS_PARAMS[key]
        await self.send_raw(f"{prefix}{value}")

    async def set_parameter_on_off(self, key: str, on: bool) -> None:
        """Set an ON/OFF PS parameter."""
        await self.set_parameter(key, "ON" if on else "OFF")

    # ---------------------------------------------------------------- menu

    async def menu(self, command: str) -> None:
        """Cursor/menu command (see const.MENU_COMMANDS keys)."""
        from .const import MENU_COMMANDS  # pylint: disable=import-outside-toplevel

        if command not in MENU_COMMANDS:
            raise ValueError(f"Unknown menu command: {command}")
        await self.send_raw(MENU_COMMANDS[command])

    # --------------------------------------------------------------- zones

    async def zone_power(self, zone: int, on: bool) -> None:
        """Zone 2/3/4 on/off."""
        await self.send_raw(f"Z{zone}{'ON' if on else 'OFF'}")

    async def zone_source(self, zone: int, code: str) -> None:
        """Zone 2/3/4 source (``SOURCE`` follows the main zone)."""
        await self.send_raw(f"Z{zone}{code.upper()}")

    async def zone_volume_up(self, zone: int) -> None:
        """Zone 2/3 volume up."""
        await self.send_raw(f"Z{zone}UP")

    async def zone_volume_down(self, zone: int) -> None:
        """Zone 2/3 volume down."""
        await self.send_raw(f"Z{zone}DOWN")

    async def zone_set_volume_db(self, zone: int, db: float) -> None:
        """Zone 2/3 volume (-70 .. +18 dB, 10..99 codes)."""
        code = encode_level(db, VOLUME_ZERO_DB_CODE, min_code=10, max_code=99)
        await self.send_raw(f"Z{zone}{code}")

    async def zone_mute(self, zone: int, on: bool) -> None:
        """Zone 2/3 mute."""
        await self.send_raw(f"Z{zone}MU{'ON' if on else 'OFF'}")

    # ------------------------------------------------------- line handling

    async def _on_line(self, line: str) -> None:
        event = parse_line(line)
        changed = self._apply(event)

        if event.kind is EventKind.UNKNOWN and event.raw not in self._unknown_seen:
            self._unknown_seen.add(event.raw)
            _LOG.info("Unknown line from unit: %r", event.raw)

        if changed:
            await self._notify(event)

    def _apply(self, event: DenonEvent) -> bool:  # pylint: disable=too-many-branches,too-many-return-statements
        """Apply an event to the state. Returns True if something changed."""
        state = self._state
        kind = event.kind

        if kind is EventKind.POWER:
            if state.power == event.value:
                return False
            state.power = event.value
            if not event.value:
                # In standby the unit reports nothing else; forget volatile bits.
                state.muted = None
            return True

        if kind is EventKind.MAIN_ZONE:
            return _set(state, "main_zone", event.value)

        if kind is EventKind.VOLUME:
            return _set(state, "volume_db", event.value)

        if kind is EventKind.VOLUME_MAX:
            return _set(state, "volume_max_db", event.value)

        if kind is EventKind.MUTE:
            return _set(state, "muted", event.value)

        if kind is EventKind.SOURCE:
            return _set(state, "source", event.value)

        if kind is EventKind.VIDEO_SELECT:
            return _set(state, "video_select", event.value)

        if kind is EventKind.RECORD_SELECT:
            return _set(state, "record_select", event.value)

        if kind is EventKind.INPUT_MODE:
            return _set(state, "input_mode", event.value)

        if kind is EventKind.DIGITAL_MODE:
            return _set(state, "digital_mode", event.value)

        if kind is EventKind.SURROUND:
            return _set(state, "surround", event.value)

        if kind is EventKind.QUICK_SELECT:
            return _set(state, "quick_select", event.value)

        if kind is EventKind.CHANNEL_LEVEL and event.key:
            return _set_in(state.channel_levels, event.key, event.value)

        if kind is EventKind.PARAMETER and event.key:
            return _set_in(state.parameters, event.key, event.value)

        if kind is EventKind.VIDEO_SETTING:
            key, _sep, value = event.value.partition(" ")
            return _set_in(state.video_settings, key.upper(), value.strip())

        if kind in {
            EventKind.ZONE_POWER,
            EventKind.ZONE_SOURCE,
            EventKind.ZONE_VOLUME,
            EventKind.ZONE_MUTE,
        } and event.key:
            zone = state.zones.setdefault(int(event.key), ZoneState())
            attr = {
                EventKind.ZONE_POWER: "power",
                EventKind.ZONE_SOURCE: "source",
                EventKind.ZONE_VOLUME: "volume_db",
                EventKind.ZONE_MUTE: "muted",
            }[kind]
            return _set(zone, attr, event.value)

        return False

    async def _notify(self, event: DenonEvent) -> None:
        for listener in list(self._listeners):
            try:
                result = listener(self._state, event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # pylint: disable=broad-except
                _LOG.exception("Listener failed on %r", event.raw)


def _set(obj: Any, attr: str, value: Any) -> bool:
    if getattr(obj, attr) == value:
        return False
    setattr(obj, attr, value)
    return True


def _set_in(mapping: dict[str, Any], key: str, value: Any) -> bool:
    if mapping.get(key) == value:
        return False
    mapping[key] = value
    return True
