"""A small client for the AP's HTTP API (docs/openapi.yaml).

Only what the integration uses. Every call sends the token; the AP answers 401 for a
missing or wrong one, and after five wrong ones in a row 429 for every request for 60 s.
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlsplit

import aiohttp

TIMEOUT = aiohttp.ClientTimeout(total=15)
# GET /api/tags is about 600 bytes a tag: give a large table on weak WiFi time
LIST_TIMEOUT = aiohttp.ClientTimeout(total=60)
# A PNG goes to the AP over WiFi, decoded as it arrives: give it longer
IMAGE_TIMEOUT = aiohttp.ClientTimeout(total=60)


class OpenEslError(Exception):
    """The AP could not be reached or refused the request."""


class OpenEslConnectionError(OpenEslError):
    """No answer from the AP (network, timeout, not an OpenESL AP)."""


class OpenEslAuthError(OpenEslError):
    """Wrong or missing token (401)."""


class OpenEslApiError(OpenEslError):
    """The AP answered with an error, {"error": "..."}."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


def normalize_host(host: str) -> str:
    """'openesl.local', '192.168.1.40:80' or 'http://openesl.local/' -> 'http://host[:port]'."""
    host = host.strip()
    if "://" not in host:
        host = "http://" + host
    parts = urlsplit(host)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"not a host name or address: {host}")
    return f"{parts.scheme}://{parts.netloc}"


class OpenEslApi:
    """One AP."""

    def __init__(self, session: aiohttp.ClientSession, host: str, token: str) -> None:
        self._session = session
        self.url = normalize_host(host)
        self._token = token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        data: bytes | None = None,
        params: dict[str, str] | None = None,
        timeout: aiohttp.ClientTimeout = TIMEOUT,
    ) -> Any:
        headers = {"Authorization": f"Bearer {self._token}"}
        if data is not None:
            headers["Content-Type"] = "image/png"
        try:
            async with self._session.request(
                method,
                self.url + path,
                json=json,
                data=data,
                params=params,
                headers=headers,
                timeout=timeout,
            ) as resp:
                try:
                    body = await resp.json(content_type=None)
                except ValueError as err:
                    raise OpenEslConnectionError(
                        f"{self.url} did not answer as an OpenESL AP ({resp.status})"
                    ) from err
                if resp.status == 401:
                    raise OpenEslAuthError("wrong or missing API token")
                if resp.status >= 400:
                    msg = body.get("error") if isinstance(body, dict) else None
                    raise OpenEslApiError(resp.status, msg or resp.reason or "error")
                return body
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise OpenEslConnectionError(f"{self.url}: {str(err) or type(err).__name__}") from err

    async def get_tags(self) -> dict[str, Any]:
        """GET /api/tags: {"ap": {...}, "tags": [...]}."""
        return await self._request("GET", "/api/tags", timeout=LIST_TIMEOUT)

    async def get_health(self) -> dict[str, Any]:
        """GET /api/health: the tags that need attention."""
        return await self._request("GET", "/api/health", timeout=LIST_TIMEOUT)

    async def get_wifi(self) -> dict[str, Any]:
        """GET /api/wifi: the AP's network, with its hostname."""
        return await self._request("GET", "/api/wifi")

    async def set_tags(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """PUT /api/tags with at most 50 rows; all or nothing on the AP."""
        reply = await self._request("PUT", "/api/tags", json={"tags": rows})
        return reply["tags"]

    async def set_image(self, mac: str, png: bytes, dither: bool = False) -> dict[str, Any]:
        """PUT /api/tags/{mac}/image with a PNG of the tag's screen size."""
        params = {"dither": "true"} if dither else None
        return await self._request(
            "PUT",
            f"/api/tags/{mac}/image",
            data=png,
            params=params,
            timeout=IMAGE_TIMEOUT,
        )
