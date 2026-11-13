"""Denon RS-232 integration driver (AVP-A1HD generation) for Unfolded Circle Remote Two/3."""

from __future__ import annotations

import asyncio
import logging
import os

import level_images
from const import LEVEL_SENSORS, NUMBERS, SELECTS, SENSORS, SWITCHES, DeviceConfig
from device import DenonClientDevice
from media_player import DenonMediaPlayer
from number_entity import DenonNumber
from remote import DenonRemote
from select_entity import DenonSelect
from sensor import DenonSensor
from setup import SetupFlow
from switch_entity import DenonSwitch
from ucapi_framework import BaseConfigManager, BaseIntegrationDriver, get_config_path

_LOG = logging.getLogger("driver")


async def main() -> None:
    """Start the driver."""
    logging.basicConfig(
        format="%(asctime)s.%(msecs)03d %(levelname)s:%(name)s:%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    level = os.getenv("UC_LOG_LEVEL", "INFO").upper()
    for name in (
        "driver",
        "device",
        "media_player",
        "remote",
        "select_entity",
        "switch_entity",
        "sensor",
        "setup",
        "level_images",
        "denon_control",
        "denon_control.transport",
        "denon_control.device",
    ):
        logging.getLogger(name).setLevel(level)

    driver = BaseIntegrationDriver(
        device_class=DenonClientDevice,
        entity_classes=[
            DenonMediaPlayer,
            DenonRemote,
            lambda cfg, dev: [DenonSelect(cfg, dev, s) for s in SELECTS],
            lambda cfg, dev: [DenonSwitch(cfg, dev, s) for s in SWITCHES],
            lambda cfg, dev: [DenonSensor(cfg, dev, s) for s in SENSORS],
            lambda cfg, dev: (
                [DenonNumber(cfg, dev, n) for n in NUMBERS] if cfg.number_entities else []
            ),
            lambda cfg, dev: (
                [DenonSensor(cfg, dev, s) for s in LEVEL_SENSORS] if cfg.number_entities else []
            ),
        ],
        require_connection_before_registry=False,
    )

    driver.config_manager = BaseConfigManager(
        get_config_path(driver.api.config_dir_path),
        driver.on_device_added,
        driver.on_device_removed,
        config_class=DeviceConfig,
    )

    # Level pictures shown by the level sensors (number entities)
    await level_images.SERVER.start()

    await driver.register_all_configured_devices()

    setup_handler = SetupFlow.create_handler(driver)
    await driver.api.init("driver.json", setup_handler)

    await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        raise SystemExit(0) from None
