"""The SoluM remote's "listen on channel 11" (PUT /api/remote {"listen": ...}, remote.py)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import OpenEslError
from .coordinator import OpenEslConfigEntry, OpenEslCoordinator
from .remote import remote_device_info, remote_identifier

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenEslConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    remote = coordinator.data.remote
    if remote is not None and remote.get("can_listen"):
        async_add_entities([OpenEslRemoteListen(coordinator)])


class OpenEslRemoteListen(CoordinatorEntity[OpenEslCoordinator], SwitchEntity):
    """On: the AP's radio visits channel 11 for the remote while the AP runs on another one."""

    _attr_has_entity_name = True
    _attr_translation_key = "remote_listen"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: OpenEslCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{remote_identifier(coordinator)[1]}_listen"
        self._attr_device_info = remote_device_info(coordinator)

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.remote is not None

    @property
    def is_on(self) -> bool | None:
        remote = self.coordinator.data.remote
        return None if remote is None else bool(remote.get("listen"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        remote = self.coordinator.data.remote or {}
        # hearing: the AP hears the remote now (listen, or the AP is on channel 11)
        return {"hearing": remote.get("hearing")}

    async def _set(self, listen: bool) -> None:
        try:
            remote = await self.coordinator.api.set_remote(listen=listen)
        except OpenEslError as err:
            raise HomeAssistantError(f"The AP did not take it: {err}") from err
        self.coordinator.data.remote = remote
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
