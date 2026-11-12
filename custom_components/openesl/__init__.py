"""OpenESL: price tags and signs on an OpenESL access point (https://github.com/mathiasbk/openESL).

Uses only the AP's HTTP API (docs/openapi.yaml): GET /api/tags and /api/health once a
minute for the sensors, a webhook for the presses of a SoluM remote (remote.py), GET /api/tags/{mac}/image when a tag's
screen changed and is looked at, PUT /api/tags and /api/tags/{mac}/image for the actions.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import CONF_HOST, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType

from .api import OpenEslApi
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import SIGNAL_UPDATED, OpenEslConfigEntry, OpenEslCoordinator, coordinators
from .remote import async_remove_remote, async_setup_remote
from .services import async_setup_services

PLATFORMS = [Platform.BINARY_SENSOR, Platform.EVENT, Platform.IMAGE, Platform.SENSOR, Platform.SWITCH]

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
    coordinators(hass)[entry.entry_id] = coordinator

    @callback
    def forget() -> None:
        coordinators(hass).pop(entry.entry_id, None)
        coordinator.clear_radio_issues()

    entry.async_on_unload(forget)
    # A new update interval in the options
    entry.async_on_unload(entry.add_update_listener(_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # The SoluM remote's presses come through a webhook (AP firmware after 0.11.0)
    await async_setup_remote(hass, entry)
    if coordinator.data.remote is None:
        # The AP gets firmware with /api/remote while Home Assistant runs (an OTA update):
        # set up again, so the remote's device, entities and webhook come without a restart
        @callback
        def _remote_appeared() -> None:
            if coordinator.data.remote is not None:
                hass.config_entries.async_schedule_reload(entry.entry_id)

        entry.async_on_unload(coordinator.async_add_listener(_remote_appeared))
    # The first refresh told the other APs' tag entities before this AP and its device
    # were set up: tell them again, so a tag this AP heard last shows what it says and
    # hangs under it now, not only from the next poll
    async_dispatcher_send(hass, SIGNAL_UPDATED, entry.entry_id)
    return True


async def _reload(hass: HomeAssistant, entry: OpenEslConfigEntry) -> None:
    # Only for a new interval: a new token or address (reauth, reconfigure) reloads already
    interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = coordinators(hass).get(entry.entry_id)
    if coordinator and coordinator.update_interval != timedelta(seconds=interval):
        await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: OpenEslConfigEntry) -> None:
    await async_remove_remote(hass, entry)


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
            or (ident.endswith("_remote") and data.remote is not None)
        ):
            return False
    return True
