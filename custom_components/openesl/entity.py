"""Devices: one for the AP, one per tag."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OpenEslCoordinator


def fw_version(fw: int | None) -> str | None:
    """The tag's fw_ver as a version: 100 -> 0.1.0, 803 -> 0.8.3."""
    if fw is None:
        return None
    return f"{fw // 10000}.{fw // 100 % 100}.{fw % 100}"


def tag_name(mac: str) -> str:
    """'Tag C287FC3B': the first 8 digits of the number under the label's barcode."""
    return f"Tag {mac[4:12]}"


def ap_identifier(coordinator: OpenEslCoordinator) -> tuple[str, str]:
    return (DOMAIN, coordinator.config_entry.unique_id or coordinator.config_entry.entry_id)


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


class OpenEslTagEntity(CoordinatorEntity[OpenEslCoordinator]):
    """An entity of one tag."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OpenEslCoordinator, mac: str, key: str) -> None:
        super().__init__(coordinator)
        self.mac = mac
        self._attr_unique_id = f"{mac}_{key}"
        tag = coordinator.data.tags.get(mac, {})
        model = tag.get("model")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            name=tag_name(mac),
            manufacturer="OpenESL",
            model=f'{model}" tag' if model else "Tag",
            serial_number=mac,
            sw_version=fw_version(tag.get("fw")),
            via_device=ap_identifier(coordinator),
        )

    @property
    def tag(self) -> dict[str, Any]:
        return self.coordinator.data.tags.get(self.mac, {})

    @property
    def available(self) -> bool:
        return super().available and self.mac in self.coordinator.data.tags
