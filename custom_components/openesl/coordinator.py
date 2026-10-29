"""Polls the AP: GET /api/tags and GET /api/health once a minute."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import OpenEslApi, OpenEslAuthError, OpenEslError
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

# A tag's last poll is "now - seen_s_ago", which moves by a second or so between two
# reads of the same poll; keep the old time within this so the state does not flicker
SEEN_JITTER = timedelta(seconds=5)

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
            update_interval=SCAN_INTERVAL,
        )
        self.api = api

    async def _async_update_data(self) -> OpenEslData:
        try:
            listing = await self.api.get_tags()
            health = await self.api.get_health()
        except OpenEslAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except OpenEslError as err:
            raise UpdateFailed(str(err)) from err

        now = dt_util.utcnow()
        old = self.data
        tags = {t["mac"].upper(): t for t in listing.get("tags", [])}

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
        )
