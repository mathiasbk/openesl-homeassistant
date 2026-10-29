"""Sensors: battery, signal and last check-in per tag; firmware, uptime and counts for the AP."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricPotential,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import OpenEslConfigEntry, OpenEslCoordinator, OpenEslData
from .entity import OpenEslApEntity, OpenEslTagEntity, setup_tag_platform, fw_version

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class TagSensorDescription(SensorEntityDescription):
    value: Callable[[OpenEslData, str, dict[str, Any]], Any]


@dataclass(frozen=True, kw_only=True)
class ApSensorDescription(SensorEntityDescription):
    value: Callable[[OpenEslData], Any]


def _battery(data: OpenEslData, mac: str, tag: dict[str, Any]) -> int | None:
    # 0: the tag cannot measure it (the 1.54")
    return tag.get("battery_mv") or None


TAG_SENSORS: tuple[TagSensorDescription, ...] = (
    TagSensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        suggested_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
        value=_battery,
    ),
    TagSensorDescription(
        key="signal",
        translation_key="signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        value=lambda data, mac, tag: tag.get("rssi"),
    ),
    TagSensorDescription(
        key="last_seen",
        translation_key="last_seen",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda data, mac, tag: data.last_seen.get(mac),
    ),
    TagSensorDescription(
        key="firmware",
        translation_key="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data, mac, tag: fw_version(tag.get("fw")),
    ),
    TagSensorDescription(
        key="poll_interval",
        translation_key="poll_interval",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="s",
        device_class=SensorDeviceClass.DURATION,
        entity_registry_enabled_default=False,
        value=lambda data, mac, tag: tag.get("poll_s"),
    ),
    TagSensorDescription(
        key="lost_polls",
        translation_key="lost_polls",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        value=lambda data, mac, tag: (tag.get("signal") or {}).get("lost_total"),
    ),
)

AP_SENSORS: tuple[ApSensorDescription, ...] = (
    ApSensorDescription(
        key="tags",
        translation_key="tags",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: len(data.tags),
    ),
    ApSensorDescription(
        key="tags_with_problems",
        translation_key="tags_with_problems",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda data: data.health.get("with_problems"),
    ),
    ApSensorDescription(
        key="firmware",
        translation_key="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data: data.ap.get("fw"),
    ),
    ApSensorDescription(
        key="started",
        translation_key="started",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data: data.started,
    ),
    ApSensorDescription(
        # The AP's own WiFi: the first thing to look at when it answers slowly
        key="wifi_signal",
        translation_key="wifi_signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data: data.wifi.get("rssi"),
    ),
    ApSensorDescription(
        key="channel",
        translation_key="channel",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data: data.ap.get("channel"),
    ),
    ApSensorDescription(
        key="scheduled",
        translation_key="scheduled",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value=lambda data: data.ap.get("scheduled"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenEslConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(OpenEslApSensor(coordinator, d) for d in AP_SENSORS)

    setup_tag_platform(
        hass,
        entry,
        async_add_entities,
        lambda c, mac: (OpenEslTagSensor(c, mac, d) for d in TAG_SENSORS),
    )


class OpenEslTagSensor(OpenEslTagEntity, SensorEntity):
    entity_description: TagSensorDescription

    def __init__(
        self, coordinator: OpenEslCoordinator, mac: str, description: TagSensorDescription
    ) -> None:
        super().__init__(coordinator, mac, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.source.data, self.mac, self.tag)


class OpenEslApSensor(OpenEslApEntity, SensorEntity):
    entity_description: ApSensorDescription

    def __init__(self, coordinator: OpenEslCoordinator, description: ApSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.coordinator.data)
