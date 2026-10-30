"""Framework-facing Denon device wrapper.

Built on ``ucapi_framework.PersistentConnectionDevice`` which gives us the
connection loop with exponential backoff.  On top of that:

* initial status query after each (re)connect,
* a slow safety-net poll (the unit pushes every change spontaneously, so 30 s
  is plenty),
* debounced ``push_update()`` so a burst of 30 lines after power-on produces a
  handful of entity updates rather than 30,
* label <-> protocol code translation for the Remote's selects and lists.
"""

from __future__ import annotations

import asyncio
import logging
from asyncio import AbstractEventLoop
from typing import Any

from const import (
    RAW_COMMAND_RE,
    SELECT_BY_ID,
    SENSOR_BY_ID,
    SIMPLE_COMMANDS,
    SWITCH_BY_ID,
    DeviceConfig,
    SelectConfig,
    SensorConfig,
    SwitchConfig,
)
from denon_control import DenonDevice, DenonEvent, DenonState, EventKind
from denon_control.const import POWER_ON_SETTLE_S, SOURCES, SURROUND_MODES
from ucapi import media_player, select, sensor, switch
from ucapi_framework import BaseConfigManager, BaseIntegrationDriver, PersistentConnectionDevice

_LOG = logging.getLogger(__name__)

POLL_INTERVAL_S = 30.0
UPDATE_DEBOUNCE_S = 0.08


class DenonClientDevice(PersistentConnectionDevice):  # pylint: disable=too-many-public-methods
    """One Denon unit behind a serial-to-IP bridge."""

    _device_config: DeviceConfig

    def __init__(
        self,
        device_config: DeviceConfig,
        loop: AbstractEventLoop | None,
        config_manager: BaseConfigManager | None = None,
        driver: BaseIntegrationDriver | None = None,
    ) -> None:
        super().__init__(device_config, loop, config_manager=config_manager, driver=driver)
        self._client = DenonDevice(device_config.address, device_config.port)
        self._client.add_listener(self._on_denon_event)
        self._update_handle: asyncio.TimerHandle | None = None
        self._refresh_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------ identity

    @property
    def identifier(self) -> str:
        """Device identifier."""
        return self._device_config.identifier

    @property
    def name(self) -> str:
        """Friendly name."""
        return self._device_config.name

    @property
    def address(self) -> str | None:
        """Bridge address."""
        return self._device_config.address

    @property
    def log_id(self) -> str:
        """Log prefix."""
        return self._device_config.name or self._device_config.identifier

    @property
    def denon(self) -> DenonState:
        """Raw protocol state."""
        return self._client.state

    @property
    def state(self) -> media_player.States:
        """Power state mapped to media_player.States."""
        if not self.is_connected:
            return media_player.States.UNAVAILABLE
        power = self._client.state.power
        if power is None:
            return media_player.States.UNKNOWN
        return media_player.States.ON if power else media_player.States.STANDBY

    # ------------------------------------------- PersistentConnectionDevice

    async def establish_connection(self) -> DenonDevice:
        """Open the TCP link and ask the unit for its state."""
        await self._client.connect()
        await self._client.query_status(full=True)
        return self._client

    async def maintain_connection(self) -> None:
        """Block while the link is up; poll slowly as a safety net."""
        while self._client.is_connected:
            try:
                await asyncio.wait_for(self._client.wait_closed(), timeout=POLL_INTERVAL_S)
                break
            except asyncio.TimeoutError:
                try:
                    await self._client.query_status()
                except ConnectionError:
                    break
        raise ConnectionError("Serial bridge link lost")

    async def close_connection(self) -> None:
        """Close the TCP link."""
        self._cancel_refresh()
        await self._client.disconnect()

    async def disconnect(self) -> None:
        """Disconnect and mark entities unavailable."""
        await super().disconnect()
        self.push_update()

    # ------------------------------------------------------------- events

    def _on_denon_event(self, _state: DenonState, event: DenonEvent) -> None:
        if event.kind is EventKind.POWER and event.value:
            # Protocol note K: the unit needs ~4 s after power on before it
            # accepts commands; it then reports everything spontaneously, but a
            # refresh catches parameters it does not push (PS family, zones).
            self._schedule_refresh(POWER_ON_SETTLE_S + 0.5)
        self._debounced_push()

    def _debounced_push(self) -> None:
        if self._update_handle is not None:
            self._update_handle.cancel()
        self._update_handle = self._loop.call_later(UPDATE_DEBOUNCE_S, self._fire_push)

    def _fire_push(self) -> None:
        self._update_handle = None
        self.push_update()

    def _schedule_refresh(self, delay: float) -> None:
        self._cancel_refresh()

        async def _refresh() -> None:
            await asyncio.sleep(delay)
            try:
                await self._client.query_status(full=True)
            except ConnectionError:
                pass

        self._refresh_task = self._loop.create_task(_refresh())

    def _cancel_refresh(self) -> None:
        if self._refresh_task is not None and not self._refresh_task.done():
            self._refresh_task.cancel()
        self._refresh_task = None

    # ---------------------------------------------------------- commands

    async def send_raw(self, command: str) -> None:
        """Send a raw protocol command."""
        await self._client.send_raw(command)

    async def send_simple_command(self, name: str) -> bool:
        """Send a simple command by name, or a raw pass-through. Returns False if unknown."""
        key = name.strip()
        if key.startswith("remote."):
            key = key.split(".", 1)[1]
        if key.lower().startswith("raw:"):
            await self.send_raw(key[4:].strip())
            return True

        upper = key.upper()
        if upper in SIMPLE_COMMANDS:
            await self.send_raw(SIMPLE_COMMANDS[upper])
            return True

        if RAW_COMMAND_RE.match(upper):
            _LOG.debug("[%s] Raw pass-through: %s", self.log_id, upper)
            await self.send_raw(upper)
            return True

        return False

    async def power_on(self) -> None:
        """Power on."""
        await self._client.power_on()

    async def power_off(self) -> None:
        """Standby."""
        await self._client.power_off()

    async def power_toggle(self) -> None:
        """Toggle power."""
        await self._client.power_toggle()

    async def volume_up(self) -> None:
        """+0.5 dB."""
        await self._client.volume_up()

    async def volume_down(self) -> None:
        """-0.5 dB."""
        await self._client.volume_down()

    async def set_volume_percent(self, percent: float) -> None:
        """0..100."""
        await self._client.set_volume_percent(percent)

    async def mute(self, on: bool) -> None:
        """Mute on/off."""
        await self._client.mute(on)

    async def mute_toggle(self) -> None:
        """Toggle mute."""
        await self._client.mute_toggle()

    async def select_source(self, option: str | None) -> None:
        """Select a source by label or protocol code."""
        code = _code_for(option, SOURCES)
        if code is None:
            raise ValueError(f"Unknown source: {option}")
        await self._client.select_source(code)

    async def select_sound_mode(self, option: str | None) -> None:
        """Select a surround mode by label or protocol code."""
        code = _code_for(option, SURROUND_MODES)
        if code is None:
            raise ValueError(f"Unknown surround mode: {option}")
        await self._client.select_surround(code)

    async def select_option(self, cfg: SelectConfig, option: str) -> None:
        """Apply a select entity option."""
        code = _code_for(option, cfg.options)
        if code is None:
            raise ValueError(f"Unknown option for {cfg.identifier}: {option}")

        match cfg.kind:
            case "source":
                await self._client.select_source(code)
            case "surround":
                await self._client.select_surround(code)
            case "input_mode":
                await self._client.set_input_mode(code)
            case "digital_mode":
                await self._client.set_digital_mode(code)
            case "quick":
                await self._client.quick_select(int(code[-1]))
            case "ps":
                assert cfg.key is not None
                await self._client.set_parameter(cfg.key, code)
            case "zone_source":
                assert cfg.key is not None
                await self._client.zone_source(int(cfg.key), code)

    async def set_switch(self, cfg: SwitchConfig, on: bool) -> None:
        """Apply a switch entity command."""
        match cfg.kind:
            case "mute":
                await self._client.mute(on)
            case "main_zone":
                await self._client.main_zone(on)
            case "ps":
                assert cfg.key is not None
                await self._client.set_parameter_on_off(cfg.key, on)
            case "zone_power":
                assert cfg.key is not None
                await self._client.zone_power(int(cfg.key), on)
            case "zone_mute":
                assert cfg.key is not None
                await self._client.zone_mute(int(cfg.key), on)

    # ----------------------------------------------------- entity attributes

    def get_media_player_attributes(self) -> dict[media_player.Attributes, Any]:
        """Attributes for the media player entity."""
        st = self.denon
        attrs: dict[media_player.Attributes, Any] = {
            media_player.Attributes.STATE: self.state,
            media_player.Attributes.SOURCE_LIST: list(SOURCES.values()),
            media_player.Attributes.SOUND_MODE_LIST: list(SURROUND_MODES.values()),
        }
        volume = self._client.volume_percent()
        if volume is not None:
            attrs[media_player.Attributes.VOLUME] = volume
        if st.muted is not None:
            attrs[media_player.Attributes.MUTED] = st.muted
        if st.source is not None:
            attrs[media_player.Attributes.SOURCE] = SOURCES.get(st.source, st.source)
        if st.surround is not None:
            attrs[media_player.Attributes.SOUND_MODE] = SURROUND_MODES.get(
                st.surround, st.surround.title()
            )
        attrs.update(self._media_info_attributes())
        return attrs

    def _media_info_attributes(self) -> dict[media_player.Attributes, str]:
        """Show source / surround mode / volume in the title / artist / album lines.

        The media widget on activity pages only displays these text fields, so this
        is how the unit's state becomes visible without opening the entity.
        Cleared outside of ON so standby does not show stale values.
        """
        st = self.denon
        if self.state is not media_player.States.ON:
            return {
                media_player.Attributes.MEDIA_TITLE: "",
                media_player.Attributes.MEDIA_ARTIST: "",
                media_player.Attributes.MEDIA_ALBUM: "",
            }
        volume = "" if st.volume_db is None else f"{st.volume_db:.1f} dB"
        if st.muted:
            volume = f"{volume} · Muted" if volume else "Muted"
        return {
            media_player.Attributes.MEDIA_TITLE: (
                SOURCES.get(st.source, st.source) if st.source else ""
            ),
            media_player.Attributes.MEDIA_ARTIST: (
                SURROUND_MODES.get(st.surround, st.surround.title()) if st.surround else ""
            ),
            media_player.Attributes.MEDIA_ALBUM: volume,
        }

    def _select_current_code(self, cfg: SelectConfig) -> str | None:
        st = self.denon
        match cfg.kind:
            case "source":
                return st.source
            case "surround":
                return st.surround
            case "input_mode":
                return st.input_mode
            case "digital_mode":
                return st.digital_mode
            case "quick":
                return st.quick_select
            case "ps":
                return st.parameters.get(cfg.key or "")
            case "zone_source":
                zone = st.zones.get(int(cfg.key or 0))
                return zone.source if zone else None
        return None

    def get_select_attributes(self, select_id: str) -> dict[select.Attributes, Any]:
        """Attributes for a select entity."""
        cfg = SELECT_BY_ID[select_id]
        code = self._select_current_code(cfg)
        available = self.is_connected and self.denon.power is not None
        return {
            select.Attributes.STATE: select.States.ON if available else select.States.UNAVAILABLE,
            select.Attributes.CURRENT_OPTION: cfg.options.get(code, code or "") if code else "",
            select.Attributes.OPTIONS: list(cfg.options.values()),
        }

    def _switch_is_on(self, cfg: SwitchConfig) -> bool | None:
        st = self.denon
        match cfg.kind:
            case "mute":
                return st.muted
            case "main_zone":
                return st.main_zone
            case "ps":
                value = st.parameters.get(cfg.key or "")
                if value is None:
                    return None
                return value.upper() == "ON"
            case "zone_power":
                zone = st.zones.get(int(cfg.key or 0))
                return zone.power if zone else None
            case "zone_mute":
                zone = st.zones.get(int(cfg.key or 0))
                return zone.muted if zone else None
        return None

    def get_switch_attributes(self, switch_id: str) -> dict[switch.Attributes, Any]:
        """Attributes for a switch entity."""
        cfg = SWITCH_BY_ID[switch_id]
        if not self.is_connected:
            return {switch.Attributes.STATE: switch.States.UNAVAILABLE}
        is_on = self._switch_is_on(cfg)
        if is_on is None:
            return {switch.Attributes.STATE: switch.States.UNKNOWN}
        return {switch.Attributes.STATE: switch.States.ON if is_on else switch.States.OFF}

    def _sensor_value(self, cfg: SensorConfig) -> str:  # pylint: disable=too-many-return-statements
        st = self.denon

        def label(code: str | None) -> str:
            if code is None:
                return cfg.default
            return cfg.labels.get(code, code)

        match cfg.identifier:
            case "volume_db":
                return cfg.default if st.volume_db is None else f"{st.volume_db:.1f}"
            case "source":
                return label(st.source)
            case "surround_mode":
                return cfg.default if st.surround is None else st.surround
            case "input_mode":
                return label(st.input_mode)
            case "digital_mode":
                return label(st.digital_mode)
            case "quick_select":
                return label(st.quick_select)
            case "room_eq":
                return label(st.parameters.get("ROOM EQ"))
            case "dynamic_eq":
                return label(st.parameters.get("DYNEQ"))
            case "dynamic_volume":
                return label(st.parameters.get("DYNSET"))
            case "night_mode":
                return label(st.parameters.get("NIGHT"))
            case "audio_restorer":
                return label(st.parameters.get("RSTR"))
            case "zone2_source":
                return label(st.zones[2].source)
            case "zone2_volume_db":
                vol = st.zones[2].volume_db
                return cfg.default if vol is None else f"{vol:.1f}"
        return cfg.default

    def get_sensor_attributes(self, sensor_id: str) -> dict[sensor.Attributes, Any]:
        """Attributes for a sensor entity."""
        cfg = SENSOR_BY_ID[sensor_id]
        attrs: dict[sensor.Attributes, Any] = {
            sensor.Attributes.STATE: sensor.States.ON if self.is_connected else sensor.States.UNAVAILABLE,
            sensor.Attributes.VALUE: self._sensor_value(cfg),
        }
        if cfg.unit:
            attrs[sensor.Attributes.UNIT] = cfg.unit
        return attrs


def _code_for(option: str | None, table: dict[str, str]) -> str | None:
    """Accept either a label ("TV/CBL"), a code, or a case-insensitive match."""
    if not option:
        return None
    if option in table:
        return option
    for code, label in table.items():
        if option == label:
            return code
    lowered = option.strip().lower()
    for code, label in table.items():
        if lowered in {code.lower(), label.lower()}:
            return code
    return None
