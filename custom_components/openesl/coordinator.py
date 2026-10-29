"""Polls the AP: GET /api/tags, /api/health and /api/wifi, every scan_interval seconds.

GET /api/tags asks with ?since= for only the tags that changed since the last read
(openESL #270); the others are kept from the last read, their seen_s_ago counted on
from their last check-in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import math
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import OpenEslApi, OpenEslApiError, OpenEslAuthError, OpenEslError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

# A tag's last poll is "now - seen_s_ago", which moves by a second or so between two
# reads of the same poll; keep the old time within this so the state does not flicker
SEEN_JITTER = timedelta(seconds=5)

# Sent after each update with the entry id: tag entities follow every AP, not only their own
SIGNAL_UPDATED = f"{DOMAIN}_updated"

type OpenEslConfigEntry = ConfigEntry[OpenEslCoordinator]


@dataclass
class OpenEslData:
    """One poll of the AP."""

    ap: dict[str, Any]
    tags: dict[str, dict[str, Any]]
    # MAC -> its problems in GET /api/health (silent, low_battery, ...); no key: none
    problems: dict[str, list[str]] = field(default_factory=dict)
    health: dict[str, Any] = field(default_factory=dict)
    # MAC -> when it last polled; None: not known
    last_seen: dict[str, datetime | None] = field(default_factory=dict)
    started: datetime | None = None
    # GET /api/wifi, {} when the AP has no WiFi (behind a bridge)
    wifi: dict[str, Any] = field(default_factory=dict)


def coordinators(hass: HomeAssistant) -> dict[str, OpenEslCoordinator]:
    """Every AP that is set up, by config entry id."""
    return hass.data.setdefault(DOMAIN, {})


def tag_source(hass: HomeAssistant, mac: str) -> OpenEslCoordinator | None:
    """The AP that heard the tag last, of those that list it.

    An AP keeps a tag in its table after the tag has moved to another AP (it is then
    "unseen"), so two APs can list the same MAC: the newest poll tells where it is now.
    """
    best, best_ago = None, math.inf
    for coordinator in coordinators(hass).values():
        if coordinator.data is None or not coordinator.last_update_success:
            continue
        tag = coordinator.data.tags.get(mac)
        if tag is None:
            continue
        ago = tag.get("seen_s_ago")
        ago = math.inf if ago is None else ago
        if best is None or ago < best_ago:
            best, best_ago = coordinator, ago
    return best


class OpenEslCoordinator(DataUpdateCoordinator[OpenEslData]):
    """The AP and its tags."""

    config_entry: OpenEslConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: OpenEslConfigEntry, api: OpenEslApi
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
            # The same reply again (nothing polled) writes no states
            always_update=False,
        )
        self.api = api
        # The AP's "since" from the last read that went through; "" gets every tag
        self._since = ""

    async def _async_update_data(self) -> OpenEslData:
        try:
            listing = await self.api.get_tags(self._since)
            health = await self.api.get_health()
            try:
                wifi = await self.api.get_wifi()
            except OpenEslApiError as err:
                if err.status != 404:
                    raise
                wifi = {}
        except OpenEslAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except OpenEslError as err:
            raise UpdateFailed(str(err)) from err

        now = dt_util.utcnow()
        old = self.data
        tags = {t["mac"].upper(): t for t in listing.get("tags", [])}
        if listing.get("full") is False and old is not None:
            # Only the tags that changed: the rest as they were, a check-in further back
            for mac, tag in old.tags.items():
                if mac in tags:
                    continue
                if (before := old.last_seen.get(mac)) is not None:
                    tag = {**tag, "seen_s_ago": max(0, round((now - before).total_seconds()))}
                tags[mac] = tag

        last_seen: dict[str, datetime | None] = {}
        for mac, tag in tags.items():
            ago = tag.get("seen_s_ago")
            if ago is None:
                last_seen[mac] = None
                continue
            seen = now - timedelta(seconds=ago)
            before = old.last_seen.get(mac) if old else None
            last_seen[mac] = before if before and abs(seen - before) <= SEEN_JITTER else seen

        ap = listing.get("ap", {})
        started = None
        if (up := ap.get("uptime_s")) is not None:
            started = now - timedelta(seconds=up)
            if old and old.started and abs(started - old.started) <= SEEN_JITTER:
                started = old.started

        self._since = listing.get("since", "")
        problems = {
            p["mac"].upper(): list(p.get("problems", []))
            for p in health.get("problems", [])
        }
        return OpenEslData(
            ap=ap,
            tags=tags,
            problems=problems,
            health=health,
            last_seen=last_seen,
            started=started,
            wifi=wifi,
        )

    def async_update_listeners(self) -> None:
        super().async_update_listeners()
        async_dispatcher_send(self.hass, SIGNAL_UPDATED, self.config_entry.entry_id)
