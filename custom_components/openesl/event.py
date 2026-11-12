"""The SoluM remote's buttons as an event entity (remote.py)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import OpenEslConfigEntry, OpenEslCoordinator
from .remote import BUTTONS, remote_device_info, remote_identifier, signal_press

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenEslConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.data.remote is not None:
        async_add_entities([OpenEslRemoteButton(coordinator)])


class OpenEslRemoteButton(EventEntity):
    """W, left or right, as the AP heard it."""

    _attr_has_entity_name = True
    _attr_translation_key = "remote_button"
    _attr_device_class = EventDeviceClass.BUTTON
    _attr_event_types = list(BUTTONS)
    _attr_should_poll = False

    def __init__(self, coordinator: OpenEslCoordinator) -> None:
        self._entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{remote_identifier(coordinator)[1]}_button"
        self._attr_device_info = remote_device_info(coordinator)

    async def async_added_to_hass(self) -> None:
        @callback
        def pressed(button: str, body: dict[str, Any]) -> None:
            self._trigger_event(button, {"id": body.get("id"), "rssi": body.get("rssi")})
            self.async_write_ha_state()

        self.async_on_remove(async_dispatcher_connect(self.hass, signal_press(self._entry_id), pressed))
