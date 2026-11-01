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
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.openesl.const import DOMAIN
from custom_components.openesl.entity import tag_model

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
    aioclient_mock.get(f"{URL}/api/wifi", status=404, json={"error": "not found"})
    await _setup(hass, entry)
    first = hass.states.get("sensor.tag_01234567_last_check_in").state

    # Two minutes later the same poll is 133 s ago (a second of drift): the time stays put.
    # A third tag has appeared.
    new = "000002079575341D"
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{URL}/api/tags",
        json={"ap": {**AP, "uptime_s": 86461, "radio": {"connected": True}},
              "tags": [tag(MAC1, seen_s_ago=133), tag(new)]},
    )
    aioclient_mock.get(f"{URL}/api/health", json={**HEALTH, "problems": []})
    aioclient_mock.get(f"{URL}/api/wifi", json=WIFI)
    # The default interval is 120 s
    freezer.tick(120)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.tag_01234567_last_check_in").state == first
    assert hass.states.get("sensor.tag_02079575_battery_voltage").state == "2.95"
    # A tag the AP no longer lists becomes unavailable
    assert hass.states.get("sensor.tag_02066346_signal").state == "unavailable"


async def test_radio_lost_and_back(
    hass: HomeAssistant, aioclient_mock, entry, freezer: FrozenDateTimeFactory
) -> None:
    """An S3 AP whose C6 on the cable stops answering: the radio sensor and a repair issue."""
    freezer.move_to("2026-11-01T08:00:00+00:00")
    s3 = {**AP, "board": "s3-n16r8-c6", "board_name": "ESP32-S3 + C6 on cable"}
    lost = {"connected": False, "via": "uart", "lost": True, "lost_s": 45}
    aioclient_mock.get(f"{URL}/api/tags", json={**TAGS, "ap": {**s3, "radio": lost}})
    aioclient_mock.get(f"{URL}/api/health", json={
        **HEALTH, "ok": False, "radio_lost": 1,
        "radio_problems": [{"radio": 0, "id": "000098880E7177C8", "via": "uart",
                            "problems": ["radio_lost"], "lost_s": 45}],
    })
    aioclient_mock.get(f"{URL}/api/wifi", json=WIFI)
    await _setup(hass, entry)

    radio = hass.states.get("binary_sensor.openesl_1a2b_radio")
    assert radio.state == "off"
    assert radio.attributes["via"] == "uart"
    assert radio.attributes["lost_s"] == 45
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"radio_lost_{entry.entry_id}_0")
    assert issue is not None
    assert issue.translation_key == "radio_lost_uart"
    assert issue.translation_placeholders == {"ap": "openesl-1a2b", "radio": ""}
    assert issue.severity == ir.IssueSeverity.ERROR

    # It answers again: the issue goes by itself
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{URL}/api/tags", json={**TAGS, "ap": {
        **s3, "radio": {"connected": True, "via": "uart", "lost": False, "seen_s": 1, "fw": 257}}})
    aioclient_mock.get(f"{URL}/api/health", json={**HEALTH, "radio_lost": 0, "radio_problems": []})
    aioclient_mock.get(f"{URL}/api/wifi", json=WIFI)
    freezer.tick(120)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.openesl_1a2b_radio").state == "on"
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"radio_lost_{entry.entry_id}_0") is None


async def test_several_radios(
    hass: HomeAssistant, aioclient_mock, entry, freezer: FrozenDateTimeFactory
) -> None:
    """Radios over WiFi: one sensor each, also for a C6 that joins later, and which one is lost."""
    freezer.move_to("2026-11-01T08:00:00+00:00")
    r0 = {"radio": 0, "id": "0000F0F5BDFFFE01", "channel": 25, "tags": 1, "connected": True,
          "via": "wifi", "lost": False, "ip": "192.168.3.249", "seen_s": 2, "fw": 1000}
    link0 = {k: r0[k] for k in ("connected", "via", "lost", "ip", "seen_s", "fw")}
    aioclient_mock.get(f"{URL}/api/tags", json={**TAGS, "ap": {**AP, "radio": link0, "radios": [r0]}})
    aioclient_mock.get(f"{URL}/api/health", json={**HEALTH, "radio_lost": 0, "radio_problems": []})
    aioclient_mock.get(f"{URL}/api/wifi", json=WIFI)
    await _setup(hass, entry)
    assert hass.states.get("binary_sensor.openesl_1a2b_radio").attributes["id"] == "0000F0F5BDFFFE01"
    assert hass.states.get("binary_sensor.openesl_1a2b_radio_1") is None

    # A second C6 took place 1, and has now been gone for a while
    r1 = {"radio": 1, "id": "0000F0F5BDFFFE02", "channel": 15, "tags": 0, "connected": False,
          "via": "wifi", "lost": True, "lost_s": 90}
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{URL}/api/tags", json={**TAGS, "ap": {**AP, "radio": link0, "radios": [r0, r1]}})
    aioclient_mock.get(f"{URL}/api/health", json={
        **HEALTH, "radio_lost": 1,
        "radio_problems": [{"radio": 1, "id": r1["id"], "via": "wifi", "problems": ["radio_lost"], "lost_s": 90}],
    })
    aioclient_mock.get(f"{URL}/api/wifi", json=WIFI)
    freezer.tick(120)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    one = hass.states.get("binary_sensor.openesl_1a2b_radio_1")
    assert one.state == "off"
    assert one.attributes["channel"] == 15
    assert hass.states.get("binary_sensor.openesl_1a2b_radio").state == "on"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"radio_lost_{entry.entry_id}_1")
    assert issue.translation_key == "radio_lost_wifi"
    assert issue.translation_placeholders["radio"] == " 1"

    # Unloading the AP takes its issues with it
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"radio_lost_{entry.entry_id}_1") is None


async def test_only_changed_tags(
    hass: HomeAssistant, aioclient_mock, entry, freezer: FrozenDateTimeFactory
) -> None:
    """GET /api/tags?since=: a reply with "full": false holds only the tags that changed."""
    freezer.move_to("2026-10-29T12:00:00+00:00")
    aioclient_mock.get(f"{URL}/api/tags", json={**TAGS, "since": "5eed0001-1", "full": True})
    aioclient_mock.get(f"{URL}/api/health", json=HEALTH)
    aioclient_mock.get(f"{URL}/api/wifi", json=WIFI)
    await _setup(hass, entry)
    seen2 = hass.states.get("sensor.tag_02066346_last_check_in").state

    # Two minutes later only MAC1 has polled, with a lower battery
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{URL}/api/tags",
        json={"ap": AP, "since": "5eed0001-2", "full": False,
              "tags": [tag(MAC1, seen_s_ago=3, battery_mv=2900)]},
    )
    aioclient_mock.get(f"{URL}/api/health", json=HEALTH)
    aioclient_mock.get(f"{URL}/api/wifi", json=WIFI)
    freezer.tick(120)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert [str(url) for m, url, *_ in aioclient_mock.mock_calls if "/api/tags" in str(url)] == [
        f"{URL}/api/tags?since=5eed0001-1"
    ]
    assert hass.states.get("sensor.tag_01234567_battery_voltage").state == "2.9"
    assert hass.states.get("sensor.tag_01234567_last_check_in").state == "2026-10-29T12:01:57+00:00"
    # The tag not in the reply is still there, with the same check-in
    assert hass.states.get("sensor.tag_02066346_signal").state == "-80"
    assert hass.states.get("sensor.tag_02066346_last_check_in").state == seen2
    coordinator = entry.runtime_data
    assert coordinator.data.tags[MAC2]["seen_s_ago"] == 12 + 120

    # "full": true again (the AP restarted): the list is replaced, MAC2 is gone
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{URL}/api/tags",
        json={"ap": AP, "since": "77770001-1", "full": True, "tags": [tag(MAC1)]},
    )
    aioclient_mock.get(f"{URL}/api/health", json=HEALTH)
    aioclient_mock.get(f"{URL}/api/wifi", json=WIFI)
    freezer.tick(120)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert [str(url) for m, url, *_ in aioclient_mock.mock_calls if "/api/tags" in str(url)] == [
        f"{URL}/api/tags?since=5eed0001-2"
    ]
    assert hass.states.get("sensor.tag_02066346_signal").state == "unavailable"


async def test_older_ap_ignores_since(hass: HomeAssistant, ap, entry) -> None:
    """An AP without since sends every tag and no "since": the next read asks with since= again."""
    await _setup(hass, entry)
    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    calls = [str(url) for m, url, *_ in ap.mock_calls if "/api/tags" in str(url)]
    assert calls == [f"{URL}/api/tags?since=", f"{URL}/api/tags?since="]
    assert set(coordinator.data.tags) == {MAC1, MAC2}


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


async def test_send_fields_by_name(hass: HomeAssistant, ap, entry) -> None:
    await _setup(hass, entry)
    ap.put(f"{URL}/api/tags", json={"tags": [{"mac": MAC1, "content_id": 2, "changed": True, "pending": True}]})
    await hass.services.async_call(
        DOMAIN, "send",
        {"mac": MAC1, "layout": "price", "fields": {"name": "Butter", "price": 44.9, "subtitle": None}},
        blocking=True,
    )
    (body, _), = _sent(ap, "PUT", "/api/tags")
    # Passed on as a mapping, numbers as text
    assert body["tags"][0]["fields"] == {"name": "Butter", "price": "44.9", "subtitle": ""}


async def test_send_fields_by_name_old_ap(hass: HomeAssistant, ap, entry) -> None:
    await _setup(hass, entry)
    # What an AP with 0.9.2 or older answers to fields as a mapping
    ap.put(f"{URL}/api/tags", status=422, json={"error": "fields must be an array of strings", "index": 0})
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN, "send", {"mac": MAC1, "layout": "price", "fields": {"price": "44.90"}}, blocking=True
        )
    assert err.value.translation_key == "fields_by_name_unsupported"
    assert "newer than 0.9.2" in str(err.value)


async def test_send_list_old_ap_message_kept(hass: HomeAssistant, ap, entry) -> None:
    await _setup(hass, entry)
    # The same message to a list is the AP's own (a field that is not text): passed on as it is
    ap.put(f"{URL}/api/tags", status=422, json={"error": "fields must be an array of strings", "index": 0})
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(DOMAIN, "send", {"mac": MAC1, "layout": "text", "fields": ["Hei"]}, blocking=True)
    assert err.value.translation_key == "ap_refused"


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


# --- review fixes ------------------------------------------------------------------------


URL2 = "http://192.168.0.171"


def _second_ap(hass, aioclient_mock, tags, hostname="openesl-9f00"):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    aioclient_mock.get(f"{URL2}/api/tags", json=tags)
    aioclient_mock.get(f"{URL2}/api/health", json={**HEALTH, "problems": [], "with_problems": 0})
    aioclient_mock.get(f"{URL2}/api/wifi", json={**WIFI, "hostname": hostname})
    e = MockConfigEntry(domain=DOMAIN, unique_id=hostname, title=hostname,
                        data={"host": "192.168.0.171", "token": TOKEN})
    e.add_to_hass(hass)
    return e


async def test_tag_on_two_aps(hass: HomeAssistant, ap, entry, caplog, entity_registry) -> None:
    """A tag moved to a new AP is still in the old one's table: one set of entities,
    showing the AP that heard it last, and actions go there."""
    entry2 = _second_ap(hass, ap, {"ap": AP, "tags": [tag(MAC1, seen_s_ago=5, rssi=-40)]})
    # Setting up the integration sets up both entries
    await _setup(hass, entry)
    assert "does not generate unique IDs" not in caplog.text
    assert entry2.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.tag_01234567_signal").state == "-40"
    assert hass.states.get("sensor.openesl_9f00_tags").state == "1"
    # The device hangs under the AP that heard it last, from its next poll
    ap.clear_requests()
    ap.get(f"{URL}/api/tags", json=TAGS)
    ap.get(f"{URL}/api/health", json=HEALTH)
    ap.get(f"{URL}/api/wifi", json=WIFI)
    ap.get(f"{URL2}/api/tags", json={"ap": AP, "tags": [tag(MAC1, seen_s_ago=5, rssi=-41)]})
    ap.get(f"{URL2}/api/health", json={**HEALTH, "problems": [], "with_problems": 0})
    ap.get(f"{URL2}/api/wifi", json={**WIFI, "hostname": "openesl-9f00"})
    await hass.services.async_call(DOMAIN, "refresh", {}, blocking=True)
    await hass.async_block_till_done()
    devices = dr.async_get(hass)
    ap2 = devices.async_get_device(identifiers={(DOMAIN, "openesl-9f00")})
    assert devices.async_get_device(identifiers={(DOMAIN, MAC1)}).via_device_id == ap2.id

    ap.put(f"{URL2}/api/tags", json={"tags": [{"mac": MAC1, "content_id": 1, "changed": True, "pending": True}]})
    await hass.services.async_call(DOMAIN, "send", {"mac": MAC1, "layout": "text", "fields": ["Hei"]}, blocking=True)
    assert _sent(ap, "PUT", "/api/tags") == []
    assert len([c for c in ap.mock_calls if c[0] == "PUT" and str(c[1]) == f"{URL2}/api/tags"]) == 1

    # The first AP goes: the tag's entities follow the other one
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.tag_01234567_signal").state == "-41"
    assert entity_registry.async_get("sensor.tag_01234567_signal").config_entry_id == entry2.entry_id


async def test_legacy_hostname_user_flow(hass: HomeAssistant, aioclient_mock) -> None:
    """APs set up with 0.6.0 or older are all named openesl: a second one is a new entry,
    and the first keeps its address."""
    for url in (URL, URL2):
        aioclient_mock.get(f"{url}/api/tags", json=TAGS)
        aioclient_mock.get(f"{url}/api/wifi", json={**WIFI, "hostname": "openesl"})
    for host in (HOST, "192.168.0.171"):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": host, "token": TOKEN})
        assert result["type"] is FlowResultType.CREATE_ENTRY
    entries = hass.config_entries.async_entries(DOMAIN)
    assert [e.data["host"] for e in entries] == [HOST, "192.168.0.171"]
    assert [e.unique_id for e in entries] == [URL, URL2]


async def test_legacy_hostname_zeroconf(hass: HomeAssistant) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    MockConfigEntry(domain=DOMAIN, unique_id="http://openesl.local", data={"host": "openesl.local", "token": TOKEN}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=_zc(name="openesl")
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    # Not overwritten with the discovered address
    assert hass.config_entries.async_entries(DOMAIN)[0].data["host"] == "openesl.local"


async def test_options_interval(hass: HomeAssistant, ap, entry) -> None:
    await _setup(hass, entry)
    assert entry.runtime_data.update_interval.total_seconds() == 120
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"scan_interval": 600})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {"scan_interval": 600}
    assert entry.runtime_data.update_interval.total_seconds() == 600


async def test_send_refused_after_a_batch(hass: HomeAssistant, aioclient_mock, entry) -> None:
    aioclient_mock.get(f"{URL}/api/tags", json=TAGS)
    aioclient_mock.get(f"{URL}/api/health", json=HEALTH)
    aioclient_mock.get(f"{URL}/api/wifi", json=WIFI)
    await _setup(hass, entry)
    calls = []

    async def put(method, url, data):
        from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

        calls.append(data)
        if len(calls) == 1:
            return AiohttpClientMockResponse(method, url, json={"tags": [{"mac": r["mac"], "content_id": 1, "changed": True, "pending": True} for r in data["tags"]]})
        return AiohttpClientMockResponse(method, url, status=422, json={"error": "the text is too long", "index": 3})

    aioclient_mock.put(f"{URL}/api/tags", side_effect=put)
    with pytest.raises(HomeAssistantError, match="first 50 tags"):
        await hass.services.async_call(
            DOMAIN, "send", {"mac": [f"{i:016X}" for i in range(1, 80)], "layout": "text", "fields": ["Hei"]}, blocking=True
        )


async def test_device_info_follows(hass: HomeAssistant, aioclient_mock, entry, freezer: FrozenDateTimeFactory) -> None:
    """New tag firmware (OTA) and AP firmware show on the devices without a restart."""
    aioclient_mock.get(f"{URL}/api/tags", json=TAGS)
    aioclient_mock.get(f"{URL}/api/health", json=HEALTH)
    aioclient_mock.get(f"{URL}/api/wifi", json=WIFI)
    await _setup(hass, entry)
    assert hass.states.get("sensor.openesl_1a2b_wifi_signal").state == "-58"

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{URL}/api/tags", json={"ap": {**AP, "fw": "0.9.0"}, "tags": [tag(MAC1, fw=900), TAGS["tags"][1]]})
    aioclient_mock.get(f"{URL}/api/health", json=HEALTH)
    aioclient_mock.get(f"{URL}/api/wifi", json={**WIFI, "rssi": -70})
    freezer.tick(120)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    devices = dr.async_get(hass)
    assert devices.async_get_device(identifiers={(DOMAIN, MAC1)}).sw_version == "0.9.0"
    assert devices.async_get_device(identifiers={(DOMAIN, "openesl-1a2b")}).sw_version == "0.9.0"
    assert hass.states.get("sensor.openesl_1a2b_wifi_signal").state == "-70"


async def test_send_connection_lost_after_a_batch(hass: HomeAssistant, ap, entry) -> None:
    await _setup(hass, entry)
    calls = []

    async def put(method, url, data):
        from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

        calls.append(data)
        if len(calls) == 1:
            return AiohttpClientMockResponse(method, url, json={"tags": [{"mac": r["mac"], "content_id": 1, "changed": True, "pending": True} for r in data["tags"]]})
        raise TimeoutError

    ap.put(f"{URL}/api/tags", side_effect=put)
    # The timeout is named, not an empty error
    with pytest.raises(HomeAssistantError, match=r"TimeoutError\). The first 50 tags"):
        await hass.services.async_call(
            DOMAIN, "send", {"mac": [f"{i:016X}" for i in range(1, 80)], "layout": "text", "fields": ["Hei"]}, blocking=True
        )


async def test_reauth_reloads_once(hass: HomeAssistant, ap, entry) -> None:
    """A new token reloads the entry once (the options listener leaves it alone)."""
    from unittest.mock import patch

    await _setup(hass, entry)
    result = await entry.start_reauth_flow(hass)
    real = hass.config_entries.async_reload
    with patch.object(hass.config_entries, "async_reload", side_effect=real) as reload:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"token": "new-token"})
        await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert reload.call_count == 1
    assert entry.state is ConfigEntryState.LOADED


def test_tag_model_names() -> None:
    """The device model as people read it, with the experimental 2.9" red marked."""
    assert tag_model({"model": "2.9"}) == '2.9" tag'
    assert tag_model({"model": "1.54"}) == '1.54" tag'
    assert tag_model({"model": "2.9-bwr"}) == '2.9" red tag (experimental)'
    assert tag_model({"model": None}) == "Tag"
    assert tag_model({}) == "Tag"
