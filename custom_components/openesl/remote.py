"""The SoluM remote (SLT-RC004) as a button with three buttons: W, left and right.

AP firmware after 0.11.0 hears the remote on 802.15.4 channel 11 and POSTs each press to a
webhook (openESL docs/solum-remote.md, GET/PUT /api/remote). Here that webhook is one of
Home Assistant's own: each press fires the event openesl_remote_button, moves the remote's
event entity and runs its device triggers. Only an AP that answers GET /api/remote (a C6 or
C5 as its own radio) gets a remote device.
"""

from __future__ import annotations

from collections import deque
import logging
from typing import Any
from urllib.parse import urlsplit

from aiohttp import web

from homeassistant.components import webhook
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .api import OpenEslError
from .const import DOMAIN
from .coordinator import OpenEslConfigEntry, OpenEslCoordinator
from .entity import ap_identifier

_LOGGER = logging.getLogger(__name__)

EVENT_REMOTE_BUTTON = f"{DOMAIN}_remote_button"
BUTTONS = ("w", "left", "right")
# The webhook's id, made once per AP and kept in the entry's data
CONF_REMOTE_WEBHOOK_ID = "remote_webhook_id"
# The AP takes a webhook URL of at most this many characters
WEBHOOK_URL_MAX = 127
# Presses already handled, (boot, id): the AP does not resend, but a client may
SEEN_MAX = 32


def signal_press(entry_id: str) -> str:
    """Sent with the button's name on each press, for the event entity."""
    return f"{DOMAIN}_remote_press_{entry_id}"


def remote_identifier(coordinator: OpenEslCoordinator) -> tuple[str, str]:
    entry = coordinator.config_entry
    return (DOMAIN, f"{entry.unique_id or entry.entry_id}_remote")


def remote_device_info(coordinator: OpenEslCoordinator) -> DeviceInfo:
    return DeviceInfo(
        identifiers={remote_identifier(coordinator)},
        name="SoluM remote",
        manufacturer="SoluM",
        model="SLT-RC004",
        via_device=ap_identifier(coordinator),
    )


def webhook_url(hass: HomeAssistant, webhook_id: str) -> str | None:
    """The webhook's URL as the AP can reach it: plain HTTP to a name its DNS knows, or an IP.

    The AP cannot resolve .local names and does not speak HTTPS to Home Assistant, so the
    internal URL is used only when it is neither; else Home Assistant's own address.
    """
    path = webhook.async_generate_path(webhook_id)
    try:
        base = get_url(hass, allow_external=False, allow_cloud=False, prefer_external=False)
    except NoURLAvailableError:
        base = None
    if base:
        parts = urlsplit(base)
        if parts.scheme == "http" and parts.hostname and not parts.hostname.endswith(".local"):
            url = base.rstrip("/") + path
            if len(url) <= WEBHOOK_URL_MAX:
                return url
            # Too long for the AP: Home Assistant's own address below is shorter
    api = hass.config.api
    if api is None or api.use_ssl or not api.local_ip:
        return None
    url = f"http://{api.local_ip}:{api.port}{path}"
    return url if len(url) <= WEBHOOK_URL_MAX else None


def is_ours(url: str | None) -> bool:
    """A webhook the AP may have from Home Assistant (this or an earlier setup)."""
    return not url or "/api/webhook/" in url


async def async_setup_remote(hass: HomeAssistant, entry: OpenEslConfigEntry) -> None:
    """Takes the AP's presses through a webhook, if the AP can hear a remote."""
    coordinator = entry.runtime_data
    remote = coordinator.data.remote
    if remote is None:
        return
    # Under the AP: its device may not have existed yet when the remote's was made
    devices = dr.async_get(hass)
    ap = devices.async_get_device(identifiers={ap_identifier(coordinator)})
    dev = devices.async_get_device(identifiers={remote_identifier(coordinator)})
    if ap and dev and dev.via_device_id != ap.id:
        devices.async_update_device(dev.id, via_device_id=ap.id)
    webhook_id = entry.data.get(CONF_REMOTE_WEBHOOK_ID)
    if not webhook_id:
        webhook_id = webhook.async_generate_id()
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_REMOTE_WEBHOOK_ID: webhook_id}
        )
    seen: deque[tuple[Any, Any]] = deque(maxlen=SEEN_MAX)

    async def handle(hass: HomeAssistant, webhook_id: str, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except ValueError:
            return web.Response(status=400)
        if not isinstance(body, dict) or body.get("event") != "remote" or body.get("button") not in BUTTONS:
            return web.Response(status=400)
        button = body["button"]
        key = (body.get("boot"), body.get("id"))
        if key[1] is None or key not in seen:
            # Without an id a press cannot be told from a resent one: taken as new
            seen.append(key)
            fire_press(hass, entry, button, body)
        return web.Response(status=200)

    webhook.async_register(
        hass, DOMAIN, f"OpenESL remote ({entry.title})", webhook_id, handle,
        local_only=True, allowed_methods=["POST"],
    )
    entry.async_on_unload(lambda: webhook.async_unregister(hass, webhook_id))

    url = webhook_url(hass, webhook_id)
    current = remote.get("webhook")
    if url is None:
        _LOGGER.warning(
            "The SoluM remote on %s cannot reach Home Assistant: the AP needs a plain "
            "http:// address of Home Assistant with an IP or a DNS name (not .local)", entry.title,
        )
    elif current != url and is_ours(current):
        try:
            remote = await coordinator.api.set_remote(webhook=url)
        except OpenEslError as err:
            _LOGGER.warning("Could not give %s the remote's webhook: %s", entry.title, err)
        else:
            coordinator.data.remote = remote
    elif current != url:
        _LOGGER.info(
            "%s posts the remote's presses to another webhook, which is left as it is", entry.title
        )


@callback
def fire_press(hass: HomeAssistant, entry: OpenEslConfigEntry, button: str, body: dict[str, Any]) -> None:
    device = dr.async_get(hass).async_get_device(identifiers={remote_identifier(entry.runtime_data)})
    hass.bus.async_fire(
        EVENT_REMOTE_BUTTON,
        {
            CONF_DEVICE_ID: device.id if device else None,
            "button": button,
            "ap": entry.title,
            "id": body.get("id"),
        },
    )
    async_dispatcher_send(hass, signal_press(entry.entry_id), button, body)
