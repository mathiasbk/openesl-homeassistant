"""Downloadable diagnostics for OpenESL."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.loader import async_get_integration

from .api import OpenEslError
from .coordinator import OpenEslConfigEntry
from .const import DOMAIN

TO_REDACT = {"token", "host", "ssid", "setup_ssid", "ip", "fields", "content"}


async def _base_diagnostics(
    hass: HomeAssistant, entry: OpenEslConfigEntry
) -> dict[str, Any]:
    """Return the last coordinator update, without querying the AP."""
    integration = await async_get_integration(hass, DOMAIN)
    data = entry.runtime_data.data
    return {
        "version": integration.manifest["version"],
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "ap": async_redact_data(data.ap, TO_REDACT),
        "health": async_redact_data(data.health, TO_REDACT),
        "wifi": async_redact_data(data.wifi, TO_REDACT),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: OpenEslConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for an access point config entry."""
    return await _base_diagnostics(hass, entry)


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: OpenEslConfigEntry, device: dr.DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for a tag device."""
    data = entry.runtime_data.data
    diagnostics = await _base_diagnostics(hass, entry)
    mac = next(
        (
            ident
            for domain, ident in device.identifiers
            if domain == DOMAIN and ident in data.tags
        ),
        None,
    )
    if mac is None:
        return diagnostics
    diagnostics["tag"] = async_redact_data(data.tags[mac], TO_REDACT)
    try:
        details = await entry.runtime_data.api.get_tag(mac)
    except OpenEslError as err:
        details = {"error": str(err)}
    diagnostics["details"] = async_redact_data(details, TO_REDACT)
    return diagnostics
