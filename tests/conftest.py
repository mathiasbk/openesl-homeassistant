"""Fixtures for the Home Assistant integration's tests (custom_components/openesl)."""

import os
import sys

import pytest

# custom_components/ is at the root of the repository
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.openesl.const import DOMAIN  # noqa: E402

HOST = "openesl-1a2b.local"
URL = f"http://{HOST}"
TOKEN = "secret-token"

AP = {
    "fw": "0.8.3",
    "board": "c6-supermini",
    "board_name": "ESP32-C6",
    "uptime_s": 86400,
    "channel": 25,
    "max_tags": 64,
    "table_full": False,
    "poll_s": 0,
    "reset": "poweron",
}


def tag(mac, **kw):
    """A row of GET /api/tags, as the openapi.yaml example."""
    row = {
        "mac": mac,
        "seen_s_ago": 12,
        "battery_mv": 2950,
        "rssi": -61,
        "fw": 803,
        "model": "2.9",
        "draw_failed": False,
        "content_id": 2914470401,
        "shown_content_id": 2914470401,
        "pending": False,
        "poll_s": 120,
        "config": {"poll_s": 120, "max_poll_s": None, "lost_ap_s": None, "long_poll_s": None, "long_after_min": None},
        "config_pending": False,
        "content_error": None,
        "ota": True,
        "signal": {"rssi": [-62, -61], "lost": [0, 1], "retry": [0, 0], "polls": 1440, "lost_total": 3, "retries": 5, "tag_rssi": 196, "tag_lqi": 108},
        "image": True,
        "image_id": 3522432519,
        "shown_image_id": 3522432519,
        "fw_update": None,
    }
    row.update(kw)
    return row


MAC1 = "00000123456789A8"
MAC2 = "0000020663463415"

TAGS = {"ap": AP, "tags": [tag(MAC1), tag(MAC2, model="1.54", battery_mv=0, rssi=-80, pending=True)]}
HEALTH = {
    "problems": [{"mac": MAC2, "problems": ["silent"], "seen_s_ago": 1260, "battery_mv": 0}],
    "ok": False,
    "tags": 2,
    "with_problems": 1,
    "silent": 1,
    "unseen": 0,
    "draw_failed": 0,
    "low_battery": 0,
    "content_error": 0,
}
WIFI = {"mode": "sta", "ssid": "Hjemme", "connected": True, "ip": "192.168.0.170", "rssi": -58,
        "setup_ssid": None, "token_set": True, "hostname": "openesl-1A2B", "networks": []}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def ap(aioclient_mock):
    """A healthy AP with two tags."""
    aioclient_mock.get(f"{URL}/api/tags", json=TAGS)
    aioclient_mock.get(f"{URL}/api/health", json=HEALTH)
    aioclient_mock.get(f"{URL}/api/wifi", json=WIFI)
    return aioclient_mock


@pytest.fixture
def entry(hass):
    e = MockConfigEntry(domain=DOMAIN, unique_id="openesl-1a2b", title="openesl-1a2b",
                        data={"host": HOST, "token": TOKEN})
    e.add_to_hass(hass)
    return e
