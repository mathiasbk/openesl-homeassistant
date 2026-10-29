"""OpenESL: price tags and signs on an OpenESL access point (https://github.com/mathiasbk/openESL).

Uses only the AP's HTTP API (docs/openapi.yaml): GET /api/tags and /api/health once a
minute for the sensors, PUT /api/tags and /api/tags/{mac}/image for the actions.
"""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import OpenEslApi
from .const import DOMAIN
from .coordinator import OpenEslConfigEntry, OpenEslCoordinator
from .services import async_setup_services

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: OpenEslConfigEntry) -> bool:
    api = OpenEslApi(
        async_get_clientsession(hass), entry.data[CONF_HOST], entry.data[CONF_TOKEN]
    )
    coordinator = OpenEslCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OpenEslConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: OpenEslConfigEntry, device: dr.DeviceEntry
) -> bool:
    """A tag the AP no longer lists may be removed; the AP itself and listed tags not."""
    data = entry.runtime_data.data
    for domain, ident in device.identifiers:
        if domain == DOMAIN and (
            ident in (entry.unique_id, entry.entry_id) or ident.upper() in data.tags
        ):
            return False
    return True
