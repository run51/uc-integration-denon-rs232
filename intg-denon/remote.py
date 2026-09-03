"""Denon remote entity: hard-button mapping and custom UI pages."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from const import DeviceConfig, RemoteDef, slug
from denon_control.const import (
    DYNAMIC_VOLUME_SETTINGS,
    NIGHT_MODES,
    ROOM_EQ_MODES,
    SOURCES,
    SURROUND_MODES,
)
from device import DenonClientDevice
from ucapi import EntityTypes, StatusCodes, media_player, remote
from ucapi.media_player import States as MediaStates
from ucapi.remote import States as RemoteStates
from ucapi.ui import (
    Buttons,
    DeviceButtonMapping,
    Size,
    UiPage,
    create_btn_mapping,
    create_ui_icon,
    create_ui_text,
)
from ucapi_framework import create_entity_id
from ucapi_framework.entities import RemoteEntity
from ucapi_framework.helpers import RemoteAttributes

_LOG = logging.getLogger(__name__)

REMOTE_STATE_MAPPING = {
    MediaStates.UNKNOWN: RemoteStates.UNKNOWN,
    MediaStates.UNAVAILABLE: RemoteStates.UNAVAILABLE,
    MediaStates.OFF: RemoteStates.OFF,
    MediaStates.STANDBY: RemoteStates.OFF,
    MediaStates.ON: RemoteStates.ON,
}


class DenonRemote(RemoteEntity):
    """Remote entity exposing every Denon command."""

    _device: DenonClientDevice

    def __init__(self, config_device: DeviceConfig, device_instance: DenonClientDevice) -> None:
        self._device = device_instance
        entity_id = create_entity_id(EntityTypes.REMOTE, config_device.identifier)
        _LOG.debug("Initializing Denon remote entity: %s", entity_id)

        super().__init__(
            entity_id,
            f"{config_device.name} Remote",
            RemoteDef.features,
            attributes=dict(RemoteDef.attributes),
            simple_commands=RemoteDef.simple_commands,
            button_mapping=self.create_button_mappings(),
            ui_pages=self.create_ui(),
            cmd_handler=self.handle_command,
        )
        self.subscribe_to_device(device_instance)

    async def sync_state(self) -> None:
        """Push power state to the Remote."""
        state = REMOTE_STATE_MAPPING.get(self._device.state, RemoteStates.UNKNOWN)
        self.update(RemoteAttributes(STATE=state))

    # ------------------------------------------------------------- buttons

    @staticmethod
    def create_button_mappings() -> list[DeviceButtonMapping | dict[str, Any]]:
        """Physical buttons of the Remote."""
        return [
            create_btn_mapping(Buttons.POWER, media_player.Commands.TOGGLE),
            create_btn_mapping(Buttons.VOLUME_UP, "VOLUME_UP"),
            create_btn_mapping(Buttons.VOLUME_DOWN, "VOLUME_DOWN"),
            create_btn_mapping(Buttons.MUTE, "MUTE_ON", "MUTE_OFF"),
            create_btn_mapping(Buttons.DPAD_UP, "CURSOR_UP"),
            create_btn_mapping(Buttons.DPAD_DOWN, "CURSOR_DOWN"),
            create_btn_mapping(Buttons.DPAD_LEFT, "CURSOR_LEFT"),
            create_btn_mapping(Buttons.DPAD_RIGHT, "CURSOR_RIGHT"),
            create_btn_mapping(Buttons.DPAD_MIDDLE, "CURSOR_ENTER"),
            create_btn_mapping(Buttons.BACK, "RETURN"),
            create_btn_mapping(Buttons.MENU, "MENU_ON", "MENU_OFF"),
            create_btn_mapping(Buttons.RED, "QUICK1"),
            create_btn_mapping(Buttons.GREEN, "QUICK2"),
            create_btn_mapping(Buttons.YELLOW, "QUICK3"),
        ]

    # ----------------------------------------------------------------- UI

    def create_ui(self) -> list[UiPage | dict[str, Any]]:
        """Custom pages."""
        return [
            self._page_sources(),
            self._page_surround(),
            self._page_audyssey(),
            self._page_zones(),
        ]

    @staticmethod
    def _grid(page: UiPage, items: list[tuple[str, str]], columns: int = 2, start_row: int = 0) -> int:
        """Lay out (label, command) pairs on a grid; returns next free row."""
        width = 4 // columns
        row = start_row
        for index, (label, command) in enumerate(items):
            col = (index % columns) * width
            row = start_row + index // columns
            page.add(create_ui_text(label, col, row, Size(width, 1), command))
        return row + 1

    def _page_sources(self) -> UiPage:
        page = UiPage("sources", "Sources", grid=Size(4, 8))
        items = [(label, f"SOURCE_{slug(code)}") for code, label in SOURCES.items()]
        row = self._grid(page, items, columns=2)
        if row < 8:
            page.add(create_ui_icon("uc:volume-x", 0, 7, Size(2, 1), "MUTE_ON"))
            page.add(create_ui_icon("uc:volume", 2, 7, Size(2, 1), "MUTE_OFF"))
        return page

    def _page_surround(self) -> UiPage:
        page = UiPage("surround", "Surround", grid=Size(4, 9))
        items = [(label, f"SURROUND_{slug(code)}") for code, label in SURROUND_MODES.items()]
        self._grid(page, items, columns=2)
        return page

    def _page_audyssey(self) -> UiPage:
        page = UiPage("audyssey", "Audyssey", grid=Size(4, 8))
        page.add(create_ui_text("-- Room EQ --", 0, 0, Size(4, 1)))
        row = self._grid(
            page,
            [(label, f"ROOM_EQ_{slug(code)}") for code, label in ROOM_EQ_MODES.items()],
            columns=2,
            start_row=1,
        )
        page.add(create_ui_text("-- Dynamic EQ / Volume --", 0, row, Size(4, 1)))
        row += 1
        page.add(create_ui_text("Dyn EQ On", 0, row, Size(2, 1), "DYN_EQ_ON"))
        page.add(create_ui_text("Dyn EQ Off", 2, row, Size(2, 1), "DYN_EQ_OFF"))
        row += 1
        dyn = [(label, f"DYN_VOL_{slug(code)}") for code, label in DYNAMIC_VOLUME_SETTINGS.items()]
        dyn.append(("Dyn Vol Off", "DYN_VOL_OFF"))
        row = self._grid(page, dyn, columns=2, start_row=row)
        page.add(create_ui_text("-- Night --", 0, row, Size(4, 1)))
        row += 1
        self._grid(
            page,
            [(label, f"NIGHT_{slug(code)}") for code, label in NIGHT_MODES.items()],
            columns=4,
            start_row=row,
        )
        return page

    def _page_zones(self) -> UiPage:
        page = UiPage("zones", "Quick / Zones", grid=Size(4, 8))
        page.add(create_ui_text("-- Quick Select --", 0, 0, Size(4, 1)))
        page.add(create_ui_text("Q1", 0, 1, Size(1, 1), "QUICK1"))
        page.add(create_ui_text("Q2", 1, 1, Size(1, 1), "QUICK2"))
        page.add(create_ui_text("Q3", 2, 1, Size(1, 1), "QUICK3"))
        page.add(create_ui_text("Menu", 3, 1, Size(1, 1), "MENU_ON"))
        row = 2
        for zone in (2, 3):
            page.add(create_ui_text(f"-- Zone {zone} --", 0, row, Size(4, 1)))
            row += 1
            page.add(create_ui_text("On", 0, row, Size(1, 1), f"ZONE{zone}_ON"))
            page.add(create_ui_text("Off", 1, row, Size(1, 1), f"ZONE{zone}_OFF"))
            page.add(create_ui_icon("uc:minus", 2, row, Size(1, 1), f"ZONE{zone}_VOLUME_DOWN"))
            page.add(create_ui_icon("uc:plus", 3, row, Size(1, 1), f"ZONE{zone}_VOLUME_UP"))
            row += 1
        page.add(create_ui_text("-- Zone 4 --", 0, row, Size(4, 1)))
        row += 1
        page.add(create_ui_text("On", 0, row, Size(2, 1), "ZONE4_ON"))
        page.add(create_ui_text("Off", 2, row, Size(2, 1), "ZONE4_OFF"))
        return page

    # ------------------------------------------------------------ commands

    async def handle_command(
        self,
        _entity: RemoteEntity,
        cmd_id: str,
        params: dict[str, Any] | None,
        _: Any | None = None,
    ) -> StatusCodes:
        """Handle remote commands."""
        _LOG.info("Remote command %s params=%s", cmd_id, params)
        params = params or {}

        try:
            match cmd_id:
                case remote.Commands.ON | "on":
                    await self._device.power_on()
                case remote.Commands.OFF | "off":
                    await self._device.power_off()
                case remote.Commands.TOGGLE | "toggle":
                    await self._device.power_toggle()
                case remote.Commands.SEND_CMD | "send_cmd":
                    command = str(params.get("command", "")).strip()
                    if not command:
                        return StatusCodes.BAD_REQUEST
                    repeat = int(params.get("repeat", 1))
                    delay = int(params.get("delay", 0))
                    for i in range(max(1, repeat)):
                        if not await self._device.send_simple_command(command):
                            _LOG.warning("Unknown remote command: %s", command)
                            return StatusCodes.NOT_IMPLEMENTED
                        if delay and i < repeat - 1:
                            await asyncio.sleep(delay / 1000)
                case remote.Commands.SEND_CMD_SEQUENCE | "send_cmd_sequence":
                    sequence = params.get("sequence")
                    delay = int(params.get("delay", 100))
                    if not isinstance(sequence, list):
                        return StatusCodes.BAD_REQUEST
                    for command in sequence:
                        if not await self._device.send_simple_command(str(command)):
                            _LOG.warning("Unknown command in sequence: %s", command)
                        if delay:
                            await asyncio.sleep(delay / 1000)
                case _:
                    if not await self._device.send_simple_command(cmd_id):
                        return StatusCodes.NOT_IMPLEMENTED
            return StatusCodes.OK

        except (ConnectionError, OSError, RuntimeError, ValueError) as ex:
            _LOG.error("Error executing remote command %s: %s", cmd_id, ex)
            return StatusCodes.SERVICE_UNAVAILABLE
