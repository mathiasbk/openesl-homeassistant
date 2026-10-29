"""Setup: the AP's address (or found with mDNS) and its API token."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_TOKEN
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import (
    OpenEslApi,
    OpenEslApiError,
    OpenEslAuthError,
    OpenEslConnectionError,
    OpenEslError,
    normalize_host,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class OpenEslConfigFlow(ConfigFlow, domain=DOMAIN):
    """One entry per AP, known by its hostname (openesl-xxxx)."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._name: str | None = None

    async def _try(self, host: str, token: str) -> tuple[dict[str, str], str | None]:
        """Check the token with GET /api/tags. Returns (errors, hostname)."""
        try:
            api = OpenEslApi(async_get_clientsession(self.hass), host, token)
        except ValueError:
            return {CONF_HOST: "invalid_host"}, None
        try:
            await api.get_tags()
            try:
                wifi = await api.get_wifi()
            except OpenEslApiError as err:
                # An AP without WiFi behind a bridge: known by its address instead
                if err.status != 404:
                    raise
                wifi = {}
        except OpenEslAuthError:
            return {CONF_TOKEN: "invalid_auth"}, None
        except OpenEslConnectionError:
            return {"base": "cannot_connect"}, None
        except OpenEslError as err:
            if isinstance(err, OpenEslApiError) and err.status == 429:
                return {"base": "locked"}, None
            _LOGGER.exception("Unexpected answer from %s", host)
            return {"base": "unknown"}, None
        return {}, (wifi.get("hostname") or "").lower() or None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            errors, hostname = await self._try(host, user_input[CONF_TOKEN])
            if not errors:
                await self.async_set_unique_id(hostname or normalize_host(host))
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=hostname or host,
                    data={CONF_HOST: host, CONF_TOKEN: user_input[CONF_TOKEN]},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_HOST): str,
                        vol.Required(CONF_TOKEN): TOKEN_SELECTOR,
                    }
                ),
                user_input or {CONF_HOST: "openesl.local"},
            ),
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """An AP found on the network: its HTTP service is named after its hostname."""
        name = discovery_info.hostname.removesuffix(".").removesuffix(".local").lower()
        if not name.startswith("openesl"):
            return self.async_abort(reason="not_openesl")
        host = discovery_info.host
        if discovery_info.port and discovery_info.port != 80:
            host = f"{host}:{discovery_info.port}"
        await self.async_set_unique_id(name)
        # The AP got a new address: follow it
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._host = host
        self._name = name
        self.context["title_placeholders"] = {"name": name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._host is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            errors, hostname = await self._try(self._host, user_input[CONF_TOKEN])
            if not errors:
                return self.async_create_entry(
                    title=hostname or self._name or self._host,
                    data={CONF_HOST: self._host, CONF_TOKEN: user_input[CONF_TOKEN]},
                )
        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): TOKEN_SELECTOR}),
            description_placeholders={"name": self._name or "", "host": self._host},
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors, _ = await self._try(entry.data[CONF_HOST], user_input[CONF_TOKEN])
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_TOKEN: user_input[CONF_TOKEN]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): TOKEN_SELECTOR}),
            description_placeholders={"name": entry.title},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """A new address for the AP (a fixed IP instead of the .local name)."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            errors, hostname = await self._try(host, entry.data[CONF_TOKEN])
            if not errors and hostname and entry.unique_id not in (None, hostname):
                errors = {CONF_HOST: "wrong_ap"}
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: host}
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_HOST): str}),
                user_input or {CONF_HOST: entry.data[CONF_HOST]},
            ),
            errors=errors,
        )
