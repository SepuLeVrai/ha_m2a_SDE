"""Config flow for m2A Water."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType
import voluptuous as vol

from .api import (
    M2AAuthError,
    M2AConnectionError,
    M2ACounterNotFound,
    M2AWaterApi,
)
from .const import (
    CONF_COUNTER_NUMBER,
    CONF_REFERENCE,
    CONF_STARTS_AT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class M2AWaterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle an m2A Water config flow."""

    VERSION = 1

    async def _validate(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate credentials and meter, returning normalized config data."""
        session = async_create_clientsession(self.hass, auto_cleanup=False)
        api = M2AWaterApi(
            session,
            str(data[CONF_USERNAME]),
            str(data[CONF_PASSWORD]),
        )

        try:
            await api.async_login()
            installation = await api.async_get_installation(
                str(data[CONF_COUNTER_NUMBER]),
                force=False,
            )
        finally:
            # Home Assistant owns the shared connector. Detach this temporary
            # session instead of closing it, which HA explicitly warns against.
            session.detach()

        validated = dict(data)
        validated[CONF_COUNTER_NUMBER] = installation.counter_number
        validated[CONF_REFERENCE] = installation.reference
        if installation.starts_at is not None:
            validated[CONF_STARTS_AT] = installation.starts_at.isoformat()
        return validated

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle initial setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                validated = await self._validate(user_input)
            except M2AAuthError:
                errors["base"] = "invalid_auth"
            except M2ACounterNotFound:
                errors["base"] = "counter_not_found"
            except M2AConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error validating m2A account")
                errors["base"] = "unknown"
            else:
                counter = str(validated[CONF_COUNTER_NUMBER])
                await self.async_set_unique_id(counter)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"m2A Eau - {counter}",
                    data=validated,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.EMAIL)
                ),
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_COUNTER_NUMBER): TextSelector(),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: dict[str, Any],
    ) -> ConfigFlowResult:
        """Start reauthentication."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Confirm new credentials."""
        errors: dict[str, str] = {}
        entry = self._reauth_entry

        if user_input is not None:
            candidate = dict(entry.data)
            candidate[CONF_USERNAME] = user_input[CONF_USERNAME]
            candidate[CONF_PASSWORD] = user_input[CONF_PASSWORD]

            try:
                validated = await self._validate(candidate)
            except M2AAuthError:
                errors["base"] = "invalid_auth"
            except M2ACounterNotFound:
                errors["base"] = "counter_not_found"
            except M2AConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error reauthenticating m2A account")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=validated,
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_USERNAME,
                    default=entry.data.get(CONF_USERNAME, ""),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL)),
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
        )
