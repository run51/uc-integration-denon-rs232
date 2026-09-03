"""Denon switch entities (mute, Dynamic EQ, Dynamic Volume, zones...)."""

from __future__ import annotations

import logging
from typing import Any

from const import DeviceConfig, SwitchConfig
from device import DenonClientDevice
from ucapi import EntityTypes, StatusCodes
from ucapi.switch import Attributes, Commands, DeviceClasses, Features, States
from ucapi_framework import create_entity_id
from ucapi_framework.entities import SwitchEntity

_LOG = logging.getLogger(__name__)


class DenonSwitch(SwitchEntity):
    """One declarative switch."""

    _device: DenonClientDevice

    def __init__(
        self,
        config_device: DeviceConfig,
        device_instance: DenonClientDevice,
        switch_config: SwitchConfig,
    ) -> None:
        self._device = device_instance
        self._cfg = switch_config

        entity_id = create_entity_id(
            EntityTypes.SWITCH, config_device.identifier, switch_config.identifier
        )
        _LOG.debug("Initializing Denon switch entity: %s", entity_id)

        super().__init__(
            entity_id,
            f"{config_device.name} {switch_config.name}",
            [Features.ON_OFF, Features.TOGGLE],
            attributes={Attributes.STATE: States.UNAVAILABLE},
            device_class=DeviceClasses.SWITCH,
            cmd_handler=self.handle_command,
        )
        self.subscribe_to_device(device_instance)

    async def sync_state(self) -> None:
        """Push current state."""
        self.update(self._device.get_switch_attributes(self._cfg.identifier))

    async def handle_command(
        self,
        _entity: SwitchEntity,
        cmd_id: str,
        params: dict[str, Any] | None = None,
    ) -> StatusCodes:
        """Handle switch commands."""
        _LOG.info("Switch %s command %s params=%s", self._cfg.identifier, cmd_id, params)

        try:
            match cmd_id:
                case Commands.ON | "on":
                    await self._device.set_switch(self._cfg, True)
                case Commands.OFF | "off":
                    await self._device.set_switch(self._cfg, False)
                case Commands.TOGGLE | "toggle":
                    attrs = self._device.get_switch_attributes(self._cfg.identifier)
                    is_on = attrs.get(Attributes.STATE) == States.ON
                    await self._device.set_switch(self._cfg, not is_on)
                case _:
                    return StatusCodes.NOT_IMPLEMENTED
            return StatusCodes.OK

        except (ConnectionError, OSError, RuntimeError, ValueError) as ex:
            _LOG.error("Error on switch %s: %s", self._cfg.identifier, ex)
            return StatusCodes.SERVICE_UNAVAILABLE
