"""Denon media player entity."""

from __future__ import annotations

import logging
from typing import Any

import ucapi
from const import DeviceConfig, MediaPlayerDef
from device import DenonClientDevice
from ucapi import EntityTypes, media_player
from ucapi.media_player import Commands, DeviceClasses
from ucapi_framework import create_entity_id
from ucapi_framework.entities import MediaPlayerEntity

_LOG = logging.getLogger(__name__)


class DenonMediaPlayer(MediaPlayerEntity):
    """Media player entity for the Denon main zone."""

    _device: DenonClientDevice

    def __init__(self, config_device: DeviceConfig, device_instance: DenonClientDevice) -> None:
        self._device = device_instance
        entity_id = create_entity_id(EntityTypes.MEDIA_PLAYER, config_device.identifier)
        _LOG.debug("Initializing Denon media player entity: %s", entity_id)

        super().__init__(
            entity_id,
            config_device.name,
            MediaPlayerDef.features,
            attributes=dict(MediaPlayerDef.attributes),
            device_class=DeviceClasses.RECEIVER,
            options={
                media_player.Options.SIMPLE_COMMANDS: MediaPlayerDef.simple_commands,
                media_player.Options.VOLUME_STEPS: 196,  # 0.5 dB steps over -80..+18
            },
            cmd_handler=self.handle_command,
        )
        self.subscribe_to_device(device_instance)

    async def sync_state(self) -> None:
        """Push device state to the Remote."""
        self.update(self._device.get_media_player_attributes())

    async def handle_command(  # pylint: disable=too-many-branches,too-many-return-statements
        self,
        entity: MediaPlayerEntity,
        cmd_id: str,
        params: dict[str, Any] | None = None,
    ) -> ucapi.StatusCodes:
        """Handle media player commands."""
        _LOG.info("[%s] command %s params=%s", entity.id, cmd_id, params)
        params = params or {}

        try:
            match cmd_id:
                case Commands.ON | "on":
                    await self._device.power_on()
                case Commands.OFF | "off":
                    await self._device.power_off()
                case Commands.TOGGLE | "toggle":
                    await self._device.power_toggle()
                case Commands.VOLUME | "volume":
                    await self._device.set_volume_percent(float(params.get("volume", 0)))
                case Commands.VOLUME_UP | "volume_up":
                    await self._device.volume_up()
                case Commands.VOLUME_DOWN | "volume_down":
                    await self._device.volume_down()
                case Commands.MUTE_TOGGLE | "mute_toggle":
                    await self._device.mute_toggle()
                case Commands.MUTE | "mute":
                    await self._device.mute(True)
                case Commands.UNMUTE | "unmute":
                    await self._device.mute(False)
                case Commands.SELECT_SOURCE | "select_source":
                    await self._device.select_source(params.get("source"))
                case Commands.SELECT_SOUND_MODE | "select_sound_mode":
                    await self._device.select_sound_mode(params.get("mode"))
                case Commands.CURSOR_UP | "cursor_up":
                    await self._device.send_simple_command("CURSOR_UP")
                case Commands.CURSOR_DOWN | "cursor_down":
                    await self._device.send_simple_command("CURSOR_DOWN")
                case Commands.CURSOR_LEFT | "cursor_left":
                    await self._device.send_simple_command("CURSOR_LEFT")
                case Commands.CURSOR_RIGHT | "cursor_right":
                    await self._device.send_simple_command("CURSOR_RIGHT")
                case Commands.CURSOR_ENTER | "cursor_enter":
                    await self._device.send_simple_command("CURSOR_ENTER")
                case Commands.BACK | "back":
                    await self._device.send_simple_command("RETURN")
                case Commands.MENU | "menu" | Commands.SETTINGS | "settings":
                    await self._device.send_simple_command("MENU_ON")
                case Commands.HOME | "home":
                    await self._device.send_simple_command("MENU_OFF")
                case _:
                    command = str(params.get("command") or params.get("simple_command") or cmd_id)
                    if not await self._device.send_simple_command(command):
                        _LOG.warning("[%s] unhandled command: %s", entity.id, cmd_id)
                        return ucapi.StatusCodes.NOT_IMPLEMENTED
            return ucapi.StatusCodes.OK

        except ValueError as ex:
            _LOG.error("[%s] bad request %s: %s", entity.id, cmd_id, ex)
            return ucapi.StatusCodes.BAD_REQUEST
        except (ConnectionError, OSError, RuntimeError) as ex:
            _LOG.error("[%s] error executing %s: %s", entity.id, cmd_id, ex)
            return ucapi.StatusCodes.SERVICE_UNAVAILABLE
