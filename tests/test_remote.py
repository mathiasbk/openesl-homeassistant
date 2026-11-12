"""The SoluM remote as a button (remote.py): its device, webhook, event, switch and triggers."""

import pytest

from homeassistant.components import automation
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.core import HomeAssistant
from homeassistant.core_config import async_process_ha_core_config
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    async_capture_events,
    async_get_device_automations,
)

from custom_components.openesl.const import DOMAIN
from custom_components.openesl.remote import CONF_REMOTE_WEBHOOK_ID, EVENT_REMOTE_BUTTON

from conftest import HEALTH, REMOTE, TAGS, URL, WIFI

HA_URL = "http://192.168.1.10:8123"


def _remote_ap(aioclient_mock, remote=None, put=None):
    remote = REMOTE if remote is None else remote
    aioclient_mock.get(f"{URL}/api/tags", json=TAGS)
    aioclient_mock.get(f"{URL}/api/health", json=HEALTH)
    aioclient_mock.get(f"{URL}/api/wifi", json=WIFI)
    aioclient_mock.get(f"{URL}/api/remote", json=remote)
    aioclient_mock.put(f"{URL}/api/remote", json=put or {**remote, "webhook": "set"})
    return aioclient_mock


def _puts(aioclient_mock):
    return [data for m, url, data, _ in aioclient_mock.mock_calls if m == "PUT" and str(url) == f"{URL}/api/remote"]


async def _setup(hass, entry):
    await async_process_ha_core_config(hass, {"internal_url": HA_URL})
    assert await async_setup_component(hass, "http", {})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _remote_device(hass):
    return dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "openesl-1a2b_remote")})


async def test_no_remote(hass: HomeAssistant, ap, entry) -> None:
    await _setup(hass, entry)
    assert _remote_device(hass) is None
    assert hass.states.get("event.solum_remote_button") is None
    assert CONF_REMOTE_WEBHOOK_ID not in entry.data
    assert not _puts(ap)


async def test_remote_device_and_webhook(hass: HomeAssistant, aioclient_mock, entry) -> None:
    _remote_ap(aioclient_mock)
    await _setup(hass, entry)
    device = _remote_device(hass)
    assert device is not None
    assert (device.name, device.manufacturer, device.model) == ("SoluM remote", "SoluM", "SLT-RC004")
    ap = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "openesl-1a2b")})
    assert device.via_device_id == ap.id
    assert hass.states.get("event.solum_remote_button") is not None
    assert hass.states.get("switch.solum_remote_listen_on_channel_11").state == "off"
    # The AP is given Home Assistant's webhook, by its internal URL
    webhook_id = entry.data[CONF_REMOTE_WEBHOOK_ID]
    assert _puts(aioclient_mock) == [{"webhook": f"{HA_URL}/api/webhook/{webhook_id}"}]


async def test_press(hass: HomeAssistant, aioclient_mock, entry, hass_client_no_auth) -> None:
    _remote_ap(aioclient_mock)
    await _setup(hass, entry)
    events = async_capture_events(hass, EVENT_REMOTE_BUTTON)
    client = await hass_client_no_auth()
    path = f"/api/webhook/{entry.data[CONF_REMOTE_WEBHOOK_ID]}"
    press = {"event": "remote", "button": "left", "id": 3, "boot": 7, "rssi": -61}
    resp = await client.post(path, json=press)
    assert resp.status == 200
    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0].data == {"device_id": _remote_device(hass).id, "button": "left", "ap": "openesl-1a2b", "id": 3}
    state = hass.states.get("event.solum_remote_button")
    assert state.attributes["event_type"] == "left"
    assert state.attributes["id"] == 3
    # The same press again is not a new one; the same id after a restart of the AP is
    assert (await client.post(path, json=press)).status == 200
    assert (await client.post(path, json={**press, "boot": 8})).status == 200
    await hass.async_block_till_done()
    assert len(events) == 2
    # Not a press
    for body in ({"event": "remote", "button": "up"}, {"event": "health"}, [1]):
        assert (await client.post(path, json=body)).status == 400
    assert (await client.post(path, data="not json")).status == 400
    await hass.async_block_till_done()
    assert len(events) == 2


async def test_listen_switch(hass: HomeAssistant, aioclient_mock, entry) -> None:
    _remote_ap(aioclient_mock, put={**REMOTE, "listen": True, "hearing": True})
    await _setup(hass, entry)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.solum_remote_listen_on_channel_11"}, blocking=True
    )
    assert {"listen": True} in _puts(aioclient_mock)
    state = hass.states.get("switch.solum_remote_listen_on_channel_11")
    assert state.state == "on"
    assert state.attributes["hearing"] is True


async def test_no_listen_switch_on_a_radio_that_cannot(hass: HomeAssistant, aioclient_mock, entry) -> None:
    _remote_ap(aioclient_mock, remote={**REMOTE, "can_listen": False})
    await _setup(hass, entry)
    assert hass.states.get("event.solum_remote_button") is not None
    assert hass.states.get("switch.solum_remote_listen_on_channel_11") is None


async def test_another_webhook_is_left(hass: HomeAssistant, aioclient_mock, entry) -> None:
    _remote_ap(aioclient_mock, remote={**REMOTE, "webhook": "http://192.168.1.20:8080/button"})
    await _setup(hass, entry)
    assert not _puts(aioclient_mock)


async def test_same_webhook_not_sent_again(hass: HomeAssistant, aioclient_mock, entry) -> None:
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_REMOTE_WEBHOOK_ID: "abc"})
    _remote_ap(aioclient_mock, remote={**REMOTE, "webhook": f"{HA_URL}/api/webhook/abc"})
    await _setup(hass, entry)
    assert not _puts(aioclient_mock)


@pytest.mark.parametrize("internal_url", ["http://homeassistant.local:8123", "https://192.168.1.10:8123"])
async def test_url_the_ap_cannot_use(hass: HomeAssistant, aioclient_mock, entry, internal_url) -> None:
    """A .local name or HTTPS: Home Assistant's own IP and port instead."""
    _remote_ap(aioclient_mock)
    await async_process_ha_core_config(hass, {"internal_url": internal_url})
    assert await async_setup_component(hass, "http", {})
    api = hass.config.api
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    webhook_id = entry.data[CONF_REMOTE_WEBHOOK_ID]
    assert _puts(aioclient_mock) == [{"webhook": f"http://{api.local_ip}:{api.port}/api/webhook/{webhook_id}"}]


async def test_no_url_behind_https(hass: HomeAssistant, aioclient_mock, entry) -> None:
    """Home Assistant serves only HTTPS: nothing the AP can post to, so nothing is set."""
    _remote_ap(aioclient_mock)
    await async_process_ha_core_config(hass, {"internal_url": "https://homeassistant.local:8123"})
    assert await async_setup_component(hass, "http", {})
    hass.config.api.use_ssl = True
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert not _puts(aioclient_mock)
    assert hass.states.get("event.solum_remote_button") is not None


async def test_device_triggers(hass: HomeAssistant, aioclient_mock, entry, hass_client_no_auth) -> None:
    _remote_ap(aioclient_mock)
    await _setup(hass, entry)
    device = _remote_device(hass)
    triggers = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, device.id)
    assert {t["type"] for t in triggers if t["domain"] == DOMAIN} == {"w_pressed", "left_pressed", "right_pressed"}
    # A tag has none
    tag = next(d for d in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
               if (DOMAIN, "00000123456789A8") in d.identifiers)
    tag_triggers = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, tag.id)
    assert not [t for t in tag_triggers if t["domain"] == DOMAIN]

    calls = async_capture_events(hass, "w_was_pressed")
    assert await async_setup_component(hass, automation.DOMAIN, {automation.DOMAIN: [{
        "triggers": [{"trigger": "device", "domain": DOMAIN, "device_id": device.id, "type": "w_pressed"}],
        "actions": [{"event": "w_was_pressed"}],
    }]})
    client = await hass_client_no_auth()
    path = f"/api/webhook/{entry.data[CONF_REMOTE_WEBHOOK_ID]}"
    await client.post(path, json={"event": "remote", "button": "right", "id": 1, "boot": 1})
    await client.post(path, json={"event": "remote", "button": "w", "id": 2, "boot": 1})
    await hass.async_block_till_done()
    assert len(calls) == 1


async def test_unload_removes_the_webhook(hass: HomeAssistant, aioclient_mock, entry, hass_client_no_auth) -> None:
    _remote_ap(aioclient_mock)
    await _setup(hass, entry)
    events = async_capture_events(hass, EVENT_REMOTE_BUTTON)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()
    path = f"/api/webhook/{entry.data[CONF_REMOTE_WEBHOOK_ID]}"
    # Home Assistant answers 200 for a webhook it does not know, but nothing fires
    await client.post(path, json={"event": "remote", "button": "w", "id": 1, "boot": 1})
    await hass.async_block_till_done()
    assert not events
    # Set up again: the same webhook, registered again
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await client.post(path, json={"event": "remote", "button": "w", "id": 1, "boot": 1})
    await hass.async_block_till_done()
    assert len(events) == 1


async def test_long_internal_url_falls_back_to_the_ip(hass: HomeAssistant, aioclient_mock, entry) -> None:
    """An internal URL too long for the AP (127 characters with the path): the IP instead."""
    _remote_ap(aioclient_mock)
    await async_process_ha_core_config(hass, {"internal_url": f"http://{'h' * 60}.example.org:8123"})
    assert await async_setup_component(hass, "http", {})
    api = hass.config.api
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    webhook_id = entry.data[CONF_REMOTE_WEBHOOK_ID]
    assert _puts(aioclient_mock) == [{"webhook": f"http://{api.local_ip}:{api.port}/api/webhook/{webhook_id}"}]


async def test_remote_appears_after_an_ap_update(hass: HomeAssistant, aioclient_mock, entry) -> None:
    """The AP answered 404 at setup and /api/remote after an OTA update: set up again."""
    aioclient_mock.get(f"{URL}/api/tags", json=TAGS)
    aioclient_mock.get(f"{URL}/api/health", json=HEALTH)
    aioclient_mock.get(f"{URL}/api/wifi", json=WIFI)
    aioclient_mock.get(f"{URL}/api/remote", status=404, json={"error": "not found"})
    await _setup(hass, entry)
    assert _remote_device(hass) is None
    aioclient_mock.clear_requests()
    _remote_ap(aioclient_mock)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _remote_device(hass) is not None
    assert hass.states.get("event.solum_remote_button") is not None
    assert len(_puts(aioclient_mock)) == 1


async def test_press_without_id_is_never_a_repeat(hass: HomeAssistant, aioclient_mock, entry, hass_client_no_auth) -> None:
    _remote_ap(aioclient_mock)
    await _setup(hass, entry)
    events = async_capture_events(hass, EVENT_REMOTE_BUTTON)
    client = await hass_client_no_auth()
    path = f"/api/webhook/{entry.data[CONF_REMOTE_WEBHOOK_ID]}"
    for _ in range(2):
        assert (await client.post(path, json={"event": "remote", "button": "w"})).status == 200
    await hass.async_block_till_done()
    assert len(events) == 2
