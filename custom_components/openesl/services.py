"""Actions: openesl.send (layout + fields), openesl.send_image (a PNG), openesl.refresh."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .api import OpenEslApiError, OpenEslAuthError, OpenEslError
from .const import (
    ATTR_AT,
    ATTR_DITHER,
    ATTR_FIELDS,
    ATTR_FRAME,
    ATTR_LAYOUT,
    ATTR_MAC,
    ATTR_PATH,
    ATTR_PRICE_HIGHLIGHT,
    BATCH_MAX,
    DOMAIN,
    SERVICE_REFRESH,
    SERVICE_SEND,
    SERVICE_SEND_IMAGE,
)
from .coordinator import OpenEslConfigEntry, tag_source

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
MAC_RE = re.compile(r"^[0-9A-F]{16}$")


def _mac(value: Any) -> str:
    mac = re.sub(r"[:\-\s]", "", str(value)).upper()
    if not MAC_RE.match(mac):
        raise vol.Invalid(f"not a 16-digit hex MAC: {value}")
    return mac


def _field(value: Any) -> str:
    # A number from a template (a price, a temperature) is sent as its text
    return "" if value is None else str(value)


TARGET = {
    vol.Optional(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
    vol.Optional(ATTR_MAC): vol.All(cv.ensure_list, [_mac]),
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
}

SEND_SCHEMA = vol.Schema(
    {
        **TARGET,
        vol.Required(ATTR_LAYOUT): cv.string,
        vol.Required(ATTR_FIELDS): vol.All(cv.ensure_list, [_field]),
        vol.Optional(ATTR_PRICE_HIGHLIGHT): cv.boolean,
        vol.Optional(ATTR_FRAME): cv.boolean,
        vol.Optional(ATTR_AT): cv.datetime,
    }
)

SEND_IMAGE_SCHEMA = vol.Schema(
    {
        **TARGET,
        vol.Required(ATTR_PATH): cv.string,
        vol.Optional(ATTR_DITHER, default=False): cv.boolean,
    }
)

REFRESH_SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string})


def _entries(hass: HomeAssistant) -> list[OpenEslConfigEntry]:
    return [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]


def _resolve(hass: HomeAssistant, call: ServiceCall) -> dict[str, list[str]]:
    """The tags the call is for, as config entry id -> MACs, in the order given."""
    entries = _entries(hass)
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_loaded"
        )
    by_id = {e.entry_id: e for e in entries}
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    out: dict[str, list[str]] = defaultdict(list)

    def add(entry_id: str, mac: str) -> None:
        if mac not in out[entry_id]:
            out[entry_id].append(mac)

    device_ids = list(call.data.get(ATTR_DEVICE_ID, []))
    for entity_id in call.data.get(ATTR_ENTITY_ID, []):
        ent = ent_reg.async_get(entity_id)
        if ent is None or ent.device_id is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="not_a_tag",
                translation_placeholders={"target": entity_id},
            )
        device_ids.append(ent.device_id)

    for device_id in device_ids:
        device = dev_reg.async_get(device_id)
        mac = None
        if device is not None:
            mac = next(
                (i for d, i in device.identifiers if d == DOMAIN and MAC_RE.match(i)),
                None,
            )
        entry_id = next(
            (eid for eid in (device.config_entries if device else ()) if eid in by_id),
            None,
        )
        if mac is not None and entry_id is not None and (source := tag_source(hass, mac)):
            entry_id = source.config_entry.entry_id
        if mac is None or entry_id is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="not_a_tag",
                translation_placeholders={"target": device.name if device else device_id},
            )
        add(entry_id, mac)

    chosen = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if chosen is not None and chosen not in by_id:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="unknown_ap"
        )
    for mac in call.data.get(ATTR_MAC, []):
        # The AP that heard the tag last; a MAC no AP lists yet goes to the one AP (it keeps
        # the content until the tag appears), or to config_entry_id with more than one
        source = tag_source(hass, mac)
        entry_id = chosen or (source.config_entry.entry_id if source else None)
        if entry_id is None:
            if len(entries) > 1:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="which_ap",
                    translation_placeholders={"mac": mac},
                )
            entry_id = entries[0].entry_id
        add(entry_id, mac)

    if not out:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_tags")
    return out


def _error(err: OpenEslError, done: int = 0) -> HomeAssistantError:
    if done:
        # A later batch of 50 failed: the ones before it are on the AP
        return HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="failed_partly",
            translation_placeholders={"error": str(err), "done": str(done)},
        )
    if isinstance(err, OpenEslApiError):
        # 422 and the like: the AP says what is wrong (text too long, unknown layout)
        return HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="ap_refused",
            translation_placeholders={"status": str(err.status), "message": err.message},
        )
    if isinstance(err, OpenEslAuthError):
        return HomeAssistantError(translation_domain=DOMAIN, translation_key="auth")
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="cannot_connect",
        translation_placeholders={"error": str(err)},
    )


def _unix(when: datetime) -> int:
    # A time without a zone is Home Assistant's own time zone
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt_util.get_default_time_zone())
    return int(when.timestamp())


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    async def send(call: ServiceCall) -> ServiceResponse:
        content: dict[str, Any] = {
            "layout": call.data[ATTR_LAYOUT],
            "fields": call.data[ATTR_FIELDS],
        }
        for key in (ATTR_PRICE_HIGHLIGHT, ATTR_FRAME):
            if key in call.data:
                content[key] = call.data[key]
        if ATTR_AT in call.data:
            content["at"] = _unix(call.data[ATTR_AT])

        results: list[dict[str, Any]] = []
        for entry_id, macs in _resolve(hass, call).items():
            entry: OpenEslConfigEntry = hass.config_entries.async_get_known_entry(entry_id)
            coordinator = entry.runtime_data
            try:
                for i in range(0, len(macs), BATCH_MAX):
                    rows = [{"mac": m, **content} for m in macs[i : i + BATCH_MAX]]
                    results += await coordinator.api.set_tags(rows)
            except OpenEslError as err:
                raise _error(err, len(results)) from err
            finally:
                await coordinator.async_request_refresh()
        return {"tags": results}

    async def send_image(call: ServiceCall) -> ServiceResponse:
        path = call.data[ATTR_PATH]
        if not hass.config.is_allowed_path(path):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="path_not_allowed",
                translation_placeholders={"path": path},
            )
        try:
            png = await hass.async_add_executor_job(Path(path).read_bytes)
        except OSError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="cannot_read",
                translation_placeholders={"path": path, "error": str(err)},
            ) from err

        results: list[dict[str, Any]] = []
        for entry_id, macs in _resolve(hass, call).items():
            entry: OpenEslConfigEntry = hass.config_entries.async_get_known_entry(entry_id)
            coordinator = entry.runtime_data
            try:
                for mac in macs:
                    results.append(
                        await coordinator.api.set_image(mac, png, call.data[ATTR_DITHER])
                    )
            except OpenEslError as err:
                raise _error(err) from err
            finally:
                await coordinator.async_request_refresh()
        return {"tags": results}

    async def refresh(call: ServiceCall) -> None:
        chosen = call.data.get(ATTR_CONFIG_ENTRY_ID)
        for entry in _entries(hass):
            if chosen in (None, entry.entry_id):
                await entry.runtime_data.async_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_SEND, send, SEND_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_IMAGE,
        send_image,
        SEND_IMAGE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, refresh, REFRESH_SCHEMA)
