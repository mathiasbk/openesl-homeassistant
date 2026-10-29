"""The Home Assistant integration against a mocked AP (the replies of docs/openapi.yaml)."""

from datetime import datetime, timezone
import json

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.openesl.const import DOMAIN

from conftest import AP, HEALTH, HOST, MAC1, MAC2, TAGS, TOKEN, URL, WIFI, tag


def _sent(aioclient_mock, method, path):
    """The bodies sent to path."""
    return [
        (data, headers)
        for m, url, data, headers in aioclient_mock.mock_calls
        if m == method and str(url).split("?")[0] == URL + path
    ]


async def _setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


# --- setup -------------------------------------------------------------------------------


async def test_user_flow(hass: HomeAssistant, ap) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST, "token": TOKEN})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "openesl-1a2b"
    assert result["data"] == {"host": HOST, "token": TOKEN}
    assert result["result"].unique_id == "openesl-1a2b"
    # The token goes with every request
    assert all(h["Authorization"] == f"Bearer {TOKEN}" for _, _, _, h in ap.mock_calls)


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, {"token": "invalid_auth"}), (429, {"base": "locked"}), (None, {"base": "cannot_connect"})],
)
async def test_user_flow_errors(hass: HomeAssistant, aioclient_mock, status, error) -> None:
    if status is None:
        aioclient_mock.get(f"{URL}/api/tags", exc=TimeoutError)
    else:
        aioclient_mock.get(f"{URL}/api/tags", status=status, json={"error": "no"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST, "token": "wrong"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == error


async def test_not_an_ap(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(f"{URL}/api/tags", text="<html>router</html>")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST, "token": TOKEN})
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_already_configured(hass: HomeAssistant, ap, entry) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": HOST, "token": TOKEN})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


def _zc(host="192.168.0.170", name="openesl-1a2b"):
    return ZeroconfServiceInfo(
        ip_address=__import__("ipaddress").ip_address(host),
        ip_addresses=[__import__("ipaddress").ip_address(host)],
        hostname=f"{name}.local.",
        name=f"{name}._http._tcp.local.",
        port=80,
        type="_http._tcp.local.",
        properties={},
    )


async def test_zeroconf_flow(hass: HomeAssistant, aioclient_mock) -> None:
    url = "http://192.168.0.170"
    aioclient_mock.get(f"{url}/api/tags", json=TAGS)
    aioclient_mock.get(f"{url}/api/wifi", json=WIFI)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=_zc())
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"token": TOKEN})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"host": "192.168.0.170", "token": TOKEN}
    assert result["result"].unique_id == "openesl-1a2b"


async def test_zeroconf_new_address(hass: HomeAssistant, entry) -> None:
    """A known AP seen at a new address: the entry follows it."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=_zc("192.168.0.99")
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data["host"] == "192.168.0.99"


async def test_zeroconf_other_http_device(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=_zc(name="printer")
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_openesl"


async def test_reauth(hass: HomeAssistant, aioclient_mock, entry) -> None:
    aioclient_mock.get(f"{URL}/api/tags", status=401, json={"error": "unauthorized"})
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{URL}/api/tags", json=TAGS)
    aioclient_mock.get(f"{URL}/api/health", json=HEALTH)
    aioclient_mock.get(f"{URL}/api/wifi", json=WIFI)
    result = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {"token": "new-token"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["token"] == "new-token"
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


async def test_reconfigure_wrong_ap(hass: HomeAssistant, aioclient_mock, entry) -> None:
    other = "http://192.168.0.50"
    aioclient_mock.get(f"{other}/api/tags", json=TAGS)
    aioclient_mock.get(f"{other}/api/wifi", json={**WIFI, "hostname": "openesl-9999"})
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": "192.168.0.50"})
    assert result["errors"] == {"host": "wrong_ap"}


# --- entities ----------------------------------------------------------------------------


async def test_sensors(hass: HomeAssistant, ap, entry, freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to("2026-10-29T12:00:00+00:00")
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    # Tag C2: 2.9", 2950 mV
    assert hass.states.get("sensor.tag_01234567_battery_voltage").state == "2.95"
    assert hass.states.get("sensor.tag_01234567_signal").state == "-61"
    assert hass.states.get("sensor.tag_01234567_last_check_in").state == "2026-10-29T11:59:48+00:00"
    assert hass.states.get("sensor.tag_01234567_firmware").state == "0.8.3"
    assert hass.states.get("binary_sensor.tag_01234567_problem").state == "off"
    assert hass.states.get("binary_sensor.tag_01234567_update_pending").state == "off"

    # The 1.54" cannot measure its battery; silent in /api/health
    assert hass.states.get("sensor.tag_02066346_battery_voltage").state == "unknown"
    problem = hass.states.get("binary_sensor.tag_02066346_problem")
    assert problem.state == "on"
    assert problem.attributes["problems"] == ["silent"]
    assert hass.states.get("binary_sensor.tag_02066346_battery").state == "off"
    assert hass.states.get("binary_sensor.tag_02066346_update_pending").state == "on"

    # The AP
    assert hass.states.get("sensor.openesl_1a2b_tags").state == "2"
    assert hass.states.get("sensor.openesl_1a2b_tags_with_problems").state == "1"
    assert hass.states.get("sensor.openesl_1a2b_firmware").state == "0.8.3"
    assert hass.states.get("sensor.openesl_1a2b_started").state == "2026-10-28T12:00:00+00:00"
    # No network radio on this AP
    assert hass.states.get("binary_sensor.openesl_1a2b_radio") is None

    devices = dr.async_get(hass)
    tag_dev = devices.async_get_device(identifiers={(DOMAIN, MAC1)})
    ap_dev = devices.async_get_device(identifiers={(DOMAIN, "openesl-1a2b")})
    assert tag_dev.model == '2.9" tag'
    assert tag_dev.serial_number == MAC1
    assert tag_dev.via_device_id == ap_dev.id
    assert ap_dev.model == "ESP32-C6"


async def test_new_tag_and_steady_last_seen(
    hass: HomeAssistant, aioclient_mock, entry, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to("2026-10-29T12:00:00+00:00")
    aioclient_mock.get(f"{URL}/api/tags", json=TAGS)
    aioclient_mock.get(f"{URL}/api/health", json=HEALTH)
    await _setup(hass, entry)
    first = hass.states.get("sensor.tag_01234567_last_check_in").state

    # A minute later the same poll is 73 s ago (a second of drift): the time stays put.
    # A third tag has appeared.
    new = "000002079575341D"
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{URL}/api/tags",
        json={"ap": {**AP, "uptime_s": 86461, "radio": {"connected": True}},
              "tags": [tag(MAC1, seen_s_ago=73), tag(new)]},
    )
    aioclient_mock.get(f"{URL}/api/health", json={**HEALTH, "problems": []})
    freezer.tick(60)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.tag_01234567_last_check_in").state == first
    assert hass.states.get("sensor.tag_02079575_battery_voltage").state == "2.95"
    # A tag the AP no longer lists becomes unavailable
    assert hass.states.get("sensor.tag_02066346_signal").state == "unavailable"


async def test_ap_unreachable(hass: HomeAssistant, aioclient_mock, entry) -> None:
    aioclient_mock.get(f"{URL}/api/tags", exc=TimeoutError)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


# --- actions -----------------------------------------------------------------------------


async def test_send_to_devices(hass: HomeAssistant, ap, entry) -> None:
    await _setup(hass, entry)
    ap.put(f"{URL}/api/tags", json={"tags": [
        {"mac": MAC1, "content_id": 1, "changed": True, "pending": True},
        {"mac": MAC2, "content_id": 1, "changed": False, "pending": False},
    ]})
    devices = dr.async_get(hass)
    ids = [devices.async_get_device(identifiers={(DOMAIN, m)}).id for m in (MAC1, MAC2)]

    reply = await hass.services.async_call(
        DOMAIN, "send",
        {"device_id": ids, "layout": "3d-printer", "fields": ["Core One", "", 40, "Left 1 h"], "price_highlight": True},
        blocking=True, return_response=True,
    )
    assert [r["mac"] for r in reply["tags"]] == [MAC1, MAC2]
    (body, _), = _sent(ap, "PUT", "/api/tags")
    assert body == {"tags": [
        {"mac": MAC1, "layout": "3d-printer", "fields": ["Core One", "", "40", "Left 1 h"], "price_highlight": True},
        {"mac": MAC2, "layout": "3d-printer", "fields": ["Core One", "", "40", "Left 1 h"], "price_highlight": True},
    ]}


async def test_send_by_mac_scheduled(hass: HomeAssistant, ap, entry) -> None:
    await hass.config.async_update(time_zone="Europe/Oslo")
    await _setup(hass, entry)
    ap.put(f"{URL}/api/tags", json={"tags": [{"mac": "00000123456789B2", "scheduled": True, "at": 1792069200}]})
    await hass.services.async_call(
        DOMAIN, "send",
        # A MAC the AP does not list yet; a time without a zone is Home Assistant's (CEST)
        {"mac": "00:00:01:23:45:67:89:b2", "layout": "price", "fields": ["Butter", "44.90"], "at": "2026-10-15 15:00:00"},
        blocking=True,
    )
    (body, _), = _sent(ap, "PUT", "/api/tags")
    assert body["tags"][0]["mac"] == "00000123456789B2"
    assert body["tags"][0]["at"] == int(datetime(2026, 10, 15, 13, tzinfo=timezone.utc).timestamp())


async def test_send_batches_of_50(hass: HomeAssistant, ap, entry) -> None:
    await _setup(hass, entry)
    ap.put(f"{URL}/api/tags", json={"tags": []})
    macs = [f"{i:016X}" for i in range(1, 121)]
    await hass.services.async_call(DOMAIN, "send", {"mac": macs, "layout": "text", "fields": ["Hei"]}, blocking=True)
    assert [len(b["tags"]) for b, _ in _sent(ap, "PUT", "/api/tags")] == [50, 50, 20]


async def test_send_refused(hass: HomeAssistant, ap, entry) -> None:
    await _setup(hass, entry)
    ap.put(f"{URL}/api/tags", status=422, json={"error": "the text is too long", "index": 0})
    with pytest.raises(HomeAssistantError, match="the text is too long"):
        await hass.services.async_call(DOMAIN, "send", {"mac": MAC1, "layout": "text", "fields": ["x" * 200]}, blocking=True)


async def test_send_needs_a_tag(hass: HomeAssistant, ap, entry) -> None:
    await _setup(hass, entry)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "send", {"layout": "text", "fields": ["Hei"]}, blocking=True)
    ap_dev = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "openesl-1a2b")})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "send", {"device_id": ap_dev.id, "layout": "text", "fields": ["Hei"]}, blocking=True)


async def test_send_image(hass: HomeAssistant, ap, entry, tmp_path) -> None:
    await _setup(hass, entry)
    png = tmp_path / "tag.png"
    png.write_bytes(b"\x89PNG fake")
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    ap.put(f"{URL}/api/tags/{MAC1}/image", json={"mac": MAC1, "content_id": 5, "changed": True, "pending": True})
    reply = await hass.services.async_call(
        DOMAIN, "send_image", {"mac": MAC1, "path": str(png), "dither": True}, blocking=True, return_response=True
    )
    assert reply["tags"][0]["content_id"] == 5
    (body, headers), = _sent(ap, "PUT", f"/api/tags/{MAC1}/image")
    assert body == b"\x89PNG fake"
    assert headers["Content-Type"] == "image/png"
    assert any(m == "PUT" and str(u).endswith("dither=true") for m, u, _, _ in ap.mock_calls)


async def test_send_image_not_allowed(hass: HomeAssistant, ap, entry) -> None:
    await _setup(hass, entry)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "send_image", {"mac": MAC1, "path": "/etc/passwd"}, blocking=True)


async def test_refresh(hass: HomeAssistant, ap, entry) -> None:
    await _setup(hass, entry)
    before = len(_sent(ap, "GET", "/api/tags"))
    await hass.services.async_call(DOMAIN, "refresh", {}, blocking=True)
    assert len(_sent(ap, "GET", "/api/tags")) == before + 1


async def test_unload(hass: HomeAssistant, ap, entry) -> None:
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
