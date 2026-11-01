"""Binary sensors: problems from GET /api/health per tag, and the AP's radios (the C6 of an S3 AP)."""

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
from homeassistant.core import HomeAssistant, callback
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
        async_add_entities([OpenEslRadioConnected(coordinator, 0)])
        # Several radios over WiFi: one each for radios 1-3, also those a new C6 takes later
        added: set[int] = set()

        @callback
        def add_new_radios() -> None:
            new = [
                n
                for r in coordinator.data.ap.get("radios") or []
                if (n := r.get("radio")) and r.get("id") and n not in added
            ]
            added.update(new)
            if new:
                async_add_entities(OpenEslRadioConnected(coordinator, n) for n in new)

        add_new_radios()
        entry.async_on_unload(coordinator.async_add_listener(add_new_radios))

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
    """The AP has contact with its radio: the ESP32-C6 on the cable or over WiFi of an S3 AP.

    Off when the C6 does not answer: then no tag (or none of that radio's) hears the AP,
    and after 30 s the AP reports it as radio_lost in GET /api/health (a repair issue).
    """

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: OpenEslCoordinator, radio: int) -> None:
        # radio 0 keeps the key from before there were several radios
        super().__init__(coordinator, f"radio_{radio}" if radio else "radio")
        self.radio = radio
        if radio:
            self._attr_translation_key = "radio_n"
            self._attr_translation_placeholders = {"radio": str(radio)}
        else:
            self._attr_translation_key = "radio"

    @property
    def _link(self) -> dict[str, Any] | None:
        ap = self.coordinator.data.ap
        known = next((r for r in ap.get("radios") or [] if r.get("radio") == self.radio), None)
        if not self.radio and (link := ap.get("radio")) is not None:
            return {**(known or {}), **link}  # radios[0] adds its id and channel
        return known

    @property
    def available(self) -> bool:
        return super().available and self._link is not None

    @property
    def is_on(self) -> bool | None:
        link = self._link
        return None if link is None else bool(link.get("connected"))

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        link = self._link
        if link is None:
            return None
        # via (uart: on the cable, wifi), lost (gone for 30 s), lost_s, ip, seen_s; as the AP sends them
        keys = ("id", "via", "channel", "ip", "lost", "lost_s")
        return {k: link[k] for k in keys if k in link}
