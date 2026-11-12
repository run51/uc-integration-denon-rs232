"""Denon number entities (master volume in dB, channel levels, tone, LFE).

The number entity type is new in the Remote core API (core 0.85): the ucapi Python library does not
have it yet, so the entity is built on the generic ucapi Entity with the type "number".
"""

from __future__ import annotations

import logging
import time
from typing import Any

from const import DeviceConfig, NumberConfig
from device import DenonClientDevice
from ucapi import StatusCodes
from ucapi.entity import Entity as UcEntity
from ucapi_framework import create_entity_id
from ucapi_framework.entity import Entity as FrameworkEntity

_LOG = logging.getLogger(__name__)

# A held volume button sends increment/decrement faster than the unit reports the new level: steps
# made within this time build on the value last sent, not on the level last reported.
PENDING_S = 1.5


class _EntityType(str):
    """Entity type not in ucapi.EntityTypes: a str that also has the enum's ``value``."""

    @property
    def value(self) -> str:
        return str(self)


NUMBER = _EntityType("number")


class DenonNumber(UcEntity, FrameworkEntity):
    """One declarative number entity."""

    _device: DenonClientDevice

    def __init__(
        self,
        config_device: DeviceConfig,
        device_instance: DenonClientDevice,
        number_config: NumberConfig,
    ) -> None:
        self._device = device_instance
        self._cfg = number_config
        self._sent: float | None = None  # value last sent
        self._sent_at = 0.0  # monotonic time it was sent
        entity_id = create_entity_id("number", config_device.identifier, number_config.identifier)
        _LOG.debug("Initializing Denon number entity: %s", entity_id)
        super().__init__(
            entity_id,
            f"{config_device.name} {number_config.name}",
            NUMBER,  # type: ignore[arg-type]
            ["value"],
            {"state": "UNAVAILABLE", "value": None},
            options={
                "min": number_config.minimum,
                "max": number_config.maximum,
                "step": number_config.step,
                "decimals": 1 if number_config.step < 1 else 0,
                "unit": "dB",
                "display_mode": "slider",
            },
            cmd_handler=self.handle_command,
        )
        self.subscribe_to_device(device_instance)

    async def sync_state(self) -> None:
        """Push the current value."""
        self.update(self._device.get_number_attributes(self._cfg.identifier))

    async def handle_command(
        self, _entity: Any, cmd_id: str, params: dict[str, Any] | None = None, *_: Any
    ) -> StatusCodes:
        """set_value, increment, decrement."""
        params = params or {}
        current = self._device.number_value(self._cfg)
        if self._sent is not None and time.monotonic() - self._sent_at < PENDING_S:
            current = self._sent
        try:
            if cmd_id == "set_value":
                value = float(params["value"])
            elif cmd_id in ("increment", "decrement"):
                if current is None:
                    return StatusCodes.SERVICE_UNAVAILABLE
                step = float(params.get("step") or self._cfg.step)
                value = current + step if cmd_id == "increment" else current - step
            else:
                return StatusCodes.NOT_IMPLEMENTED
        except (KeyError, TypeError, ValueError):
            return StatusCodes.BAD_REQUEST
        value = self._cfg.clamp(value)
        self._sent, self._sent_at = value, time.monotonic()
        try:
            await self._device.set_number(self._cfg.identifier, value)
        except (ConnectionError, OSError) as ex:
            _LOG.warning("[%s] %s failed: %s", self.id, cmd_id, ex)
            return StatusCodes.SERVICE_UNAVAILABLE
        return StatusCodes.OK
