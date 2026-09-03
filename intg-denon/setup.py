"""Setup flow: ask for the serial bridge address, validate with ``PW?``."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from const import DEFAULT_PORT, DeviceConfig
from denon_control import DenonDevice, DenonEvent, DenonState, EventKind
from ucapi import IntegrationSetupError, RequestUserInput, SetupError
from ucapi_framework import BaseSetupFlow

_LOG = logging.getLogger(__name__)

VALIDATION_TIMEOUT_S = 4.0


class SetupFlow(BaseSetupFlow[DeviceConfig]):
    """Manual setup: bridge IP + TCP port."""

    def get_manual_entry_form(self) -> RequestUserInput:
        """Form shown in the web-configurator."""
        return RequestUserInput(
            {"en": "Denon RS-232 Setup", "fr": "Configuration Denon RS-232"},
            [
                {
                    "id": "info",
                    "label": {"en": "Serial bridge", "fr": "Passerelle série"},
                    "field": {
                        "label": {
                            "value": {
                                "en": (
                                    "Enter the IP address and TCP port of the serial-to-IP "
                                    "bridge wired to the Denon RS-232 port. Unfolded Circle "
                                    "Dock 3: use port 5000 (external port 2)."
                                ),
                                "fr": (
                                    "Adresse IP et port TCP de la passerelle série-vers-IP "
                                    "reliée au port RS-232 du Denon. Dock 3 Unfolded Circle : "
                                    "utiliser le port 5000 (port externe 2)."
                                ),
                            }
                        }
                    },
                },
                {
                    "field": {"text": {"value": "Denon AVP-A1HD"}},
                    "id": "name",
                    "label": {"en": "Device name", "fr": "Nom de l'appareil"},
                },
                {
                    "field": {"text": {"value": ""}},
                    "id": "address",
                    "label": {"en": "Bridge IP address", "fr": "Adresse IP de la passerelle"},
                },
                {
                    "field": {"number": {"value": DEFAULT_PORT, "min": 1, "max": 65535}},
                    "id": "port",
                    "label": {"en": "TCP port", "fr": "Port TCP"},
                },
                {
                    "field": {"checkbox": {"value": True}},
                    "id": "validate",
                    "label": {
                        "en": "Check that the Denon answers PW? before saving",
                        "fr": "Vérifier que le Denon répond à PW? avant d'enregistrer",
                    },
                },
            ],
        )

    async def query_device(
        self, input_values: dict[str, Any]
    ) -> DeviceConfig | SetupError | RequestUserInput:
        """Validate input, optionally probe the unit, and build the config."""
        name = str(input_values.get("name", "")).strip() or "Denon AVP-A1HD"
        address = str(input_values.get("address", "")).strip()
        validate = _as_bool(input_values.get("validate", True))

        try:
            port = int(input_values.get("port", DEFAULT_PORT))
        except (TypeError, ValueError):
            return self.get_manual_entry_form()

        if not address or not 1 <= port <= 65535:
            return self.get_manual_entry_form()

        identifier = "denon_" + address.replace(".", "_").replace(":", "_")

        if validate:
            error = await _probe(address, port)
            if error is not None:
                return error

        return DeviceConfig(identifier=identifier, name=name, address=address, port=port)


async def _probe(address: str, port: int) -> SetupError | None:
    """Connect, send PW?, wait for PWON/PWSTANDBY."""
    device = DenonDevice(address, port)
    got_power = asyncio.Event()

    def listener(_state: DenonState, event: DenonEvent) -> None:
        if event.kind is EventKind.POWER:
            got_power.set()

    device.add_listener(listener)

    try:
        await device.connect()
        await device.send_raw("PW?")
        try:
            await asyncio.wait_for(got_power.wait(), timeout=VALIDATION_TIMEOUT_S)
        except asyncio.TimeoutError:
            _LOG.error(
                "No PW response from %s:%s — check wiring (TX/RX), 9600 8N1, "
                "and that the dock external port 2 is in RS232 mode",
                address,
                port,
            )
            return SetupError(IntegrationSetupError.TIMEOUT)
        _LOG.info(
            "Denon answered on %s:%s (power=%s)", address, port, device.state.power
        )
        return None

    except ConnectionRefusedError as ex:
        _LOG.error("Connection refused by %s:%s: %s", address, port, ex)
        return SetupError(IntegrationSetupError.CONNECTION_REFUSED)
    except (asyncio.TimeoutError, TimeoutError) as ex:
        _LOG.error("Timeout connecting to %s:%s: %s", address, port, ex)
        return SetupError(IntegrationSetupError.TIMEOUT)
    except OSError as ex:
        _LOG.error("Network error connecting to %s:%s: %s", address, port, ex)
        return SetupError(IntegrationSetupError.CONNECTION_REFUSED)
    finally:
        await device.disconnect()


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
