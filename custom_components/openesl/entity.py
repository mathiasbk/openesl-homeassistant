"""Devices: one for the AP, one per tag."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SIGNAL_UPDATED, OpenEslConfigEntry, OpenEslCoordinator, tag_source

# MAC -> the config entry that made the tag's entities. A tag listed by two APs gets one
# set of entities, which shows what the AP that heard it last says (tag_source)
OWNERS = f"{DOMAIN}_owners"


def fw_version(fw: int | None) -> str | None:
    """The tag's fw_ver as a version: 100 -> 0.1.0, 803 -> 0.8.3."""
    if fw is None:
        return None
    return f"{fw // 10000}.{fw // 100 % 100}.{fw % 100}"


def tag_name(mac: str) -> str:
    """'Tag C287FC3B': the first 8 digits of the number under the label's barcode."""
    return f"Tag {mac[4:12]}"


def tag_model(tag: dict[str, Any]) -> str:
    model = tag.get("model")
    return f'{model}" tag' if model else "Tag"


def ap_identifier(coordinator: OpenEslCoordinator) -> tuple[str, str]:
    return (DOMAIN, coordinator.config_entry.unique_id or coordinator.config_entry.entry_id)


def owners(hass: HomeAssistant) -> dict[str, str]:
    return hass.data.setdefault(OWNERS, {})


def setup_tag_platform(
    hass: HomeAssistant,
    entry: OpenEslConfigEntry,
    add_entities: Callable[[Iterable[Entity]], None],
    make: Callable[[OpenEslCoordinator, str], Iterable[Entity]],
) -> None:
    """Add a tag's entities when this AP lists it and no other AP has added them."""
    coordinator = entry.runtime_data
    added: set[str] = set()

    @callback
    def add_new_tags(*_: Any) -> None:
        taken = owners(hass)
        new = [
            mac
            for mac in coordinator.data.tags
            if mac not in added and taken.get(mac, entry.entry_id) == entry.entry_id
        ]
        for mac in new:
            taken[mac] = entry.entry_id
        added.update(new)
        add_entities(e for mac in new for e in make(coordinator, mac))

    @callback
    def release() -> None:
        taken = owners(hass)
        freed = [mac for mac in added if taken.get(mac) == entry.entry_id]
        for mac in freed:
            del taken[mac]
        if freed:
            # Another AP that lists them takes them over now
            async_dispatcher_send(hass, SIGNAL_UPDATED, entry.entry_id)

    add_new_tags()
    entry.async_on_unload(coordinator.async_add_listener(add_new_tags))
    # Tags another AP gave up (it was removed) are picked up when it goes
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_UPDATED, add_new_tags))
    entry.async_on_unload(release)


class OpenEslApEntity(CoordinatorEntity[OpenEslCoordinator]):
    """An entity of the AP itself."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OpenEslCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{ap_identifier(coordinator)[1]}_{key}"
        ap = coordinator.data.ap
        self._attr_device_info = DeviceInfo(
            identifiers={ap_identifier(coordinator)},
            name=coordinator.config_entry.title,
            manufacturer="OpenESL",
            model=ap.get("board_name") or "Access point",
            model_id=ap.get("board"),
            sw_version=ap.get("fw"),
            configuration_url=coordinator.api.url + "/dashboard",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        # Firmware after an OTA of the AP
        devices = dr.async_get(self.hass)
        dev = self.device_entry and devices.async_get(self.device_entry.id)
        if dev and (fw := self.coordinator.data.ap.get("fw")) != dev.sw_version:
            devices.async_update_device(dev.id, sw_version=fw)
        super()._handle_coordinator_update()


class OpenEslTagEntity(CoordinatorEntity[OpenEslCoordinator]):
    """An entity of one tag, from the AP that heard it last."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OpenEslCoordinator, mac: str, key: str) -> None:
        super().__init__(coordinator)
        self.mac = mac
        self._attr_unique_id = f"{mac}_{key}"
        tag = coordinator.data.tags.get(mac, {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name=tag_name(mac),
            manufacturer="OpenESL",
            model=tag_model(tag),
            serial_number=mac,
            sw_version=fw_version(tag.get("fw")),
            via_device=ap_identifier(coordinator),
        )

    @property
    def source(self) -> OpenEslCoordinator:
        return tag_source(self.hass, self.mac) or self.coordinator

    @property
    def tag(self) -> dict[str, Any]:
        return self.source.data.tags.get(self.mac, {})

    @property
    def available(self) -> bool:
        source = self.source
        return source.last_update_success and self.mac in source.data.tags

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def other_ap_updated(entry_id: str) -> None:
            if entry_id != self.coordinator.config_entry.entry_id:
                self._handle_coordinator_update()

        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATED, other_ap_updated))

    @callback
    def _handle_coordinator_update(self) -> None:
        # Firmware after a tag OTA, the model once a tag has polled
        devices = dr.async_get(self.hass)
        dev = self.device_entry and devices.async_get(self.device_entry.id)
        if dev and self.mac in self.source.data.tags:
            fw, model = fw_version(self.tag.get("fw")), tag_model(self.tag)
            # Under the AP that heard it last
            ap = devices.async_get_device(identifiers={ap_identifier(self.source)})
            via = ap.id if ap else dev.via_device_id
            if (fw, model, via) != (dev.sw_version, dev.model, dev.via_device_id):
                devices.async_update_device(dev.id, sw_version=fw, model=model, via_device_id=via)
        super()._handle_coordinator_update()
