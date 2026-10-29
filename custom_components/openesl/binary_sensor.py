"""Binary sensors: problems from GET /api/health per tag, and the AP's network radio."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import OpenEslConfigEntry, OpenEslCoordinator, OpenEslData
from .entity import OpenEslApEntity, OpenEslTagEntity, setup_tag_platform

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class TagBinaryDescription(BinarySensorEntityDescription):
    value: Callable[[OpenEslData, str, dict[str, Any]], bool | None]


TAG_BINARY: tuple[TagBinaryDescription, ...] = (
    TagBinaryDescription(
        # silent, unseen, draw_failed, low_battery or content_error; which in the attributes
        key="problem",
        translation_key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value=lambda data, mac, tag: mac in data.problems,
    ),
    TagBinaryDescription(
        key="battery_low",
        translation_key="battery_low",
        device_class=BinarySensorDeviceClass.BATTERY,
        value=lambda data, mac, tag: "low_battery" in data.problems.get(mac, ()),
    ),
    TagBinaryDescription(
        # The tag does not show its content yet: it gets it at its next poll
        key="pending",
        translation_key="pending",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data, mac, tag: tag.get("pending"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenEslConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if "radio" in coordinator.data.ap:
        async_add_entities([OpenEslRadioConnected(coordinator)])

    setup_tag_platform(
        hass,
        entry,
        async_add_entities,
        lambda c, mac: (OpenEslTagBinarySensor(c, mac, d) for d in TAG_BINARY),
    )


class OpenEslTagBinarySensor(OpenEslTagEntity, BinarySensorEntity):
    entity_description: TagBinaryDescription

    def __init__(
        self, coordinator: OpenEslCoordinator, mac: str, description: TagBinaryDescription
    ) -> None:
        super().__init__(coordinator, mac, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value(self.source.data, self.mac, self.tag)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key != "problem":
            return None
        attrs: dict[str, Any] = {"problems": self.source.data.problems.get(self.mac, [])}
        if err := self.tag.get("content_error"):
            attrs["content_error"] = err
        return attrs


class OpenEslRadioConnected(OpenEslApEntity, BinarySensorEntity):
    """The network radio (an ESP32-C6 over WiFi) is connected to the AP."""

    _attr_translation_key = "radio"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: OpenEslCoordinator) -> None:
        super().__init__(coordinator, "radio")

    @property
    def is_on(self) -> bool | None:
        radio = self.coordinator.data.ap.get("radio")
        return None if radio is None else bool(radio.get("connected"))
