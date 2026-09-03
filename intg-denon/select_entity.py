"""Denon select entities (source, surround, Room EQ, zones...)."""

from __future__ import annotations

import logging
from typing import Any

from const import DeviceConfig, SelectConfig
from device import DenonClientDevice
from ucapi import EntityTypes, StatusCodes
from ucapi.select import Attributes, Commands, States
from ucapi_framework import create_entity_id
from ucapi_framework.entities import SelectEntity

_LOG = logging.getLogger(__name__)


class DenonSelect(SelectEntity):
    """One declarative select."""

    _device: DenonClientDevice

    def __init__(
        self,
        config_device: DeviceConfig,
        device_instance: DenonClientDevice,
        select_config: SelectConfig,
    ) -> None:
        self._device = device_instance
        self._cfg = select_config

        entity_id = create_entity_id(
            EntityTypes.SELECT, config_device.identifier, select_config.identifier
        )
        _LOG.debug("Initializing Denon select entity: %s", entity_id)

        super().__init__(
            identifier=entity_id,
            name=f"{config_device.name} {select_config.name}",
            attributes={
                Attributes.STATE: States.UNAVAILABLE,
                Attributes.CURRENT_OPTION: "",
                Attributes.OPTIONS: list(select_config.options.values()),
            },
            cmd_handler=self.handle_command,
        )
        self.subscribe_to_device(device_instance)

    async def sync_state(self) -> None:
        """Push current option."""
        self.update(self._device.get_select_attributes(self._cfg.identifier))

    def _options(self) -> list[str]:
        return list(self._cfg.options.values())

    def _current(self) -> str:
        attrs = self._device.get_select_attributes(self._cfg.identifier)
        return str(attrs.get(Attributes.CURRENT_OPTION, ""))

    def _relative(self, step: int, cycle: bool) -> str:
        options = self._options()
        current = self._current()
        try:
            index = options.index(current) + step
        except ValueError:
            index = 0 if step > 0 else len(options) - 1
        if index >= len(options):
            index = 0 if cycle else len(options) - 1
        if index < 0:
            index = len(options) - 1 if cycle else 0
        return options[index]

    async def handle_command(
        self,
        _entity: SelectEntity,
        cmd_id: str,
        params: dict[str, Any] | None = None,
    ) -> StatusCodes:
        """Handle select commands."""
        params = params or {}
        _LOG.info("Select %s command %s params=%s", self._cfg.identifier, cmd_id, params)

        try:
            match cmd_id:
                case Commands.SELECT_OPTION | "select_option":
                    option = str(params.get("option", ""))
                case Commands.SELECT_FIRST | "select_first":
                    option = self._options()[0]
                case Commands.SELECT_LAST | "select_last":
                    option = self._options()[-1]
                case Commands.SELECT_NEXT | "select_next":
                    option = self._relative(1, bool(params.get("cycle", False)))
                case Commands.SELECT_PREVIOUS | "select_previous":
                    option = self._relative(-1, bool(params.get("cycle", False)))
                case _:
                    return StatusCodes.NOT_IMPLEMENTED

            await self._device.select_option(self._cfg, option)
            return StatusCodes.OK

        except ValueError as ex:
            _LOG.error("Invalid option for %s: %s", self._cfg.identifier, ex)
            return StatusCodes.BAD_REQUEST
        except (ConnectionError, OSError, RuntimeError) as ex:
            _LOG.error("Error on select %s: %s", self._cfg.identifier, ex)
            return StatusCodes.SERVICE_UNAVAILABLE
