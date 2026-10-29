"""The integration against a running AP: esl-sim behind the esl-client bridge, or a real AP.

Skipped unless OPENESL_LIVE_URL is set. OPENESL_LIVE_URL=sim starts both itself from an openESL
checkout in OPENESL_REPO (default ../openESL), after `make -C $OPENESL_REPO/sim build/29/esl-sim`:

    OPENESL_LIVE_URL=sim pytest tests

or by hand, to watch the screen:

    $OPENESL_REPO/sim/build/29/esl-sim serve --speed 60 --png /tmp/screen.png       # prints PTY /dev/pts/N
    python3 $OPENESL_REPO/tools/esl-client/esl_client.py --serial /dev/pts/N serve   # http://localhost:8080
    OPENESL_LIVE_URL=127.0.0.1:8080 pytest tests/test_live_sim.py

A real AP over WiFi works as well: OPENESL_LIVE_URL=openesl-xxxx.local OPENESL_LIVE_TOKEN=...
It sends to the tag with the simulator's MAC unless OPENESL_LIVE_MAC names another.
"""

import asyncio
import os
import socket
import subprocess
import sys
import time
import urllib.request
import struct
import zlib

import pytest
import pytest_socket

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openesl.const import DOMAIN

# A checkout of github.com/mathiasbk/openESL, for the simulator and the bridge
ROOT = os.path.abspath(os.environ.get("OPENESL_REPO", os.path.join(os.path.dirname(__file__), "..", "..", "openESL")))
LIVE = os.environ.get("OPENESL_LIVE_URL")
TOKEN = os.environ.get("OPENESL_LIVE_TOKEN", "not-used-over-usb")
SIM_MAC = os.environ.get("OPENESL_LIVE_MAC", "00000123456789A8").upper()

pytestmark = pytest.mark.skipif(not LIVE, reason="OPENESL_LIVE_URL is not set")


@pytest.fixture(autouse=True)
def network():
    """The harness blocks sockets for every test (pytest_runtest_setup): open them again."""
    pytest_socket.enable_socket()
    pytest_socket.socket_allow_hosts(None)
    yield


@pytest.fixture(scope="module")
def ap_url():
    """The AP's address; with OPENESL_LIVE_URL=sim, a simulator and a bridge started here."""
    pytest_socket.enable_socket()
    if LIVE != "sim":
        yield LIVE
        return
    sim = subprocess.Popen([os.path.join(ROOT, "sim", "build", "29", "esl-sim"), "serve", "--speed", "60"],
                           stdout=subprocess.PIPE, text=True)
    procs = [sim]
    try:
        pty = sim.stdout.readline().split()[1]          # "PTY /dev/pts/N"
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        procs.append(subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "esl-client", "esl_client.py"),
                                       "--serial", pty, "serve", "--port", str(port)]))
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/tags", timeout=2)
                break
            except OSError:
                time.sleep(0.1)
        yield f"127.0.0.1:{port}"
    finally:
        for p in procs:
            p.terminate()
            p.wait()


def png(width, height):
    """A 1-bit PNG: black left half, white right half."""
    row = bytes([0]) + bytes((0x00 if x < width // 2 else 0xFF) for x in range(0, width, 8))
    raw = row * height

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 1, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


async def _wait_shown(hass, entity_id, timeout=60):
    """Refresh until the tag shows its content (pending off)."""
    for _ in range(timeout):
        await hass.services.async_call(DOMAIN, "refresh", {}, blocking=True)
        await hass.async_block_till_done()
        if hass.states.get(entity_id).state == "off":
            return
        await asyncio.sleep(1)
    raise AssertionError(f"{entity_id} still pending after {timeout} s")


async def test_live(hass: HomeAssistant, tmp_path, ap_url) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="live", data={"host": ap_url, "token": TOKEN})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    # The simulated tag polls once a (simulated) minute: wait until the AP lists it
    for _ in range(30):
        if SIM_MAC in entry.runtime_data.data.tags:
            break
        await asyncio.sleep(1)
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
    # The AP answers ?since= (openESL #270): later reads hold only the tags that changed
    assert entry.runtime_data._since
    name = f"tag_{SIM_MAC[4:12].lower()}"
    assert hass.states.get(f"sensor.{name}_battery_voltage").state == "2.95"
    assert hass.states.get(f"sensor.{name}_signal").state not in ("unknown", "unavailable")

    reply = await hass.services.async_call(
        DOMAIN, "send",
        {"mac": SIM_MAC, "layout": "text", "fields": ["Home Assistant", "æøå", "", "42"], "frame": True},
        blocking=True, return_response=True,
    )
    assert reply["tags"][0]["mac"] == SIM_MAC
    await _wait_shown(hass, f"binary_sensor.{name}_update_pending")

    model = entry.runtime_data.data.tags[SIM_MAC]["model"]
    size = {"2.9": (296, 128), "1.54": (200, 200)}[model]
    picture = tmp_path / "tag.png"
    picture.write_bytes(png(*size))
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    reply = await hass.services.async_call(
        DOMAIN, "send_image", {"mac": SIM_MAC, "path": str(picture)}, blocking=True, return_response=True
    )
    assert reply["tags"][0]["changed"] is True
    await _wait_shown(hass, f"binary_sensor.{name}_update_pending")

    assert await hass.config_entries.async_unload(entry.entry_id)
