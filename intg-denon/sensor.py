"""Denon sensor entities (volume dB, surround mode, Audyssey state...)."""

from __future__ import annotations

import logging
from typing import Any

from const import DeviceConfig, SensorConfig
from device import DenonClientDevice
from ucapi import EntityTypes
from ucapi.sensor import Attributes, DeviceClasses, States
from ucapi_framework import create_entity_id
from ucapi_framework.entities import SensorEntity

_LOG = logging.getLogger(__name__)


class DenonSensor(SensorEntity):
    """One declarative sensor."""

    _device: DenonClientDevice

    def __init__(
        self,
        config_device: DeviceConfig,
        device_instance: DenonClientDevice,
        sensor_config: SensorConfig,
    ) -> None:
        self._device = device_instance
        self._cfg = sensor_config

        entity_id = create_entity_id(
            EntityTypes.SENSOR, config_device.identifier, sensor_config.identifier
        )
        _LOG.debug("Initializing Denon sensor entity: %s", entity_id)

        attributes: dict[str, Any] = {
            Attributes.STATE: States.UNAVAILABLE,
            Attributes.VALUE: sensor_config.default,
        }
        if sensor_config.unit:
            attributes[Attributes.UNIT] = sensor_config.unit

        super().__init__(
            identifier=entity_id,
            name=f"{config_device.name} {sensor_config.name}",
            features=[],
            attributes=attributes,
            device_class=DeviceClasses.CUSTOM,
        )
        self.subscribe_to_device(device_instance)

    async def sync_state(self) -> None:
        """Push current value."""
        self.update(self._device.get_sensor_attributes(self._cfg.identifier))
