"""HTTP client for the m2A / SDE private web API.

The API is the same JSON backend used by the Eaupla!/e-services web portal.
Only data for the configured meter number is retained by this client.
Raw subscription payloads are never logged.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime
import logging
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout
from yarl import URL

from .const import BASE_URL, LOGIN_PATH, REQUEST_TIMEOUT_SECONDS, WATER_API_PATH

_LOGGER = logging.getLogger(__name__)

# Headers observed on the Eaupla!/m2A SPA.  The backend is private and may use
# one or more of these values in middleware even though they are not required
# by HTTP itself.
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/152.0.0.0 Safari/537.36"
)

# The observed first-party web session lives for about two hours. Renewing at
# 90 minutes keeps normal polling away from the expiry boundary.
_AUTH_REFRESH_SECONDS = 90 * 60
_AUTH_FAILURE_STATUSES = {401, 403, 419, 440}
_LOGIN_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class M2AError(Exception):
    """Base exception for m2A Water."""


class M2AAuthError(M2AError):
    """Authentication failed."""


class M2AConnectionError(M2AError):
    """Communication with the m2A service failed."""


class M2ACounterNotFound(M2AError):
    """Configured meter was not found in the account."""


@dataclass(frozen=True, slots=True)
class M2AInstallation:
    """Minimal, privacy-preserving representation of an installation."""

    counter_number: str
    reference: str
    counter_id: int | None
    subscription_id: int | None
    starts_at: date | None


def _parse_date(value: str | None) -> date | None:
    """Parse an ISO date/datetime returned by the API."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except (ValueError, TypeError):
            return None


def parse_daily_values(payload: dict[str, Any]) -> dict[date, float]:
    """Return consoPoints.Valeurs as {date: litres}."""
    result: dict[date, float] = {}
    values = payload.get("consoPoints", {}).get("Valeurs", {})
    if not isinstance(values, dict):
        return result

    for raw_date, raw_value in values.items():
        try:
            day = datetime.strptime(str(raw_date), "%d.%m.%Y").date()
            result[day] = float(raw_value)
        except (TypeError, ValueError):
            continue
    return result


def parse_previous_year_values(payload: dict[str, Any]) -> dict[date, float]:
    """Return consoPointsBefore values.

    The portal relabels N-1 data with the current-period dates so the two
    series can be superimposed. We deliberately keep those relabelled dates
    here because they are used only for N/N-1 comparison, never for Recorder
    history.
    """
    result: dict[date, float] = {}
    values = payload.get("consoPointsBefore", {}).get("Valeurs", {})
    if not isinstance(values, dict):
        return result

    for raw_date, raw_value in values.items():
        try:
            day = datetime.strptime(str(raw_date), "%d.%m.%Y").date()
            result[day] = float(raw_value)
        except (TypeError, ValueError):
            continue
    return result


class M2AWaterApi:
    """Async API client."""

    def __init__(
        self,
        session: ClientSession,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._token: str | None = None
        self._login_monotonic: float | None = None
        self._auth_lock = asyncio.Lock()
        self._timeout = ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)

    async def _prime_session(self) -> None:
        """Prime the first-party web session before authenticating.

        The browser obtains a mulhouse_session cookie before POST /api/auth/login.
        Reproducing that sequence avoids treating a session-validation failure as
        invalid credentials.
        """
        common_headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Authorization": "Bearer false",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/login",
            "Service": "undefined",
            "User-Agent": _BROWSER_USER_AGENT,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

        # First load the public SPA entry point, then the API root observed by
        # the browser. Either response may establish/refresh mulhouse_session.
        try:
            async with self._session.get(
                f"{BASE_URL}/login",
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Referer": f"{BASE_URL}/",
                },
                timeout=self._timeout,
            ) as response:
                await response.read()

            async with self._session.get(
                f"{BASE_URL}/api/",
                headers=common_headers,
                timeout=self._timeout,
            ) as response:
                await response.read()
        except (ClientError, asyncio.TimeoutError) as err:
            raise M2AConnectionError(
                "Unable to initialize the m2A web session"
            ) from err

    def _auth_is_stale(self) -> bool:
        """Return whether the current authentication should be renewed."""
        if self._token is None or self._login_monotonic is None:
            return True
        age = asyncio.get_running_loop().time() - self._login_monotonic
        return age >= _AUTH_REFRESH_SECONDS

    def _clear_auth_state(self) -> None:
        """Discard the JWT and all first-party cookies for the portal."""
        self._token = None
        self._login_monotonic = None

        domain = URL(BASE_URL).host
        if domain:
            # The portal couples the JWT with its server-side session cookie.
            # Clearing the whole first-party cookie jar avoids carrying a dead
            # mulhouse_session into the next login attempt.
            self._session.cookie_jar.clear_domain(domain)

    async def _async_login_locked(self) -> None:
        """Authenticate while the caller holds the authentication lock."""
        self._clear_auth_state()
        await self._prime_session()

        payload = {
            "login": self._username,
            "password": self._password,
            "is_redirect": False,
            "_role": "user",
        }

        try:
            async with self._session.post(
                f"{BASE_URL}{LOGIN_PATH}",
                json=payload,
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Authorization": "Bearer false",
                    "Content-Type": "application/json;charset=UTF-8",
                    "Origin": BASE_URL,
                    "Referer": f"{BASE_URL}/login",
                    "Service": "undefined",
                    "User-Agent": _BROWSER_USER_AGENT,
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-origin",
                },
                timeout=self._timeout,
                allow_redirects=False,
            ) as response:
                if response.status in (401, 403):
                    await response.read()
                    _LOGGER.warning(
                        "m2A login rejected stored credentials (HTTP %s)",
                        response.status,
                    )
                    raise M2AAuthError("Invalid m2A credentials")

                if response.status == 422:
                    await response.read()
                    raise M2AConnectionError(
                        "m2A login request validation failed (HTTP 422)"
                    )

                if response.status == 429:
                    await response.read()
                    raise M2AConnectionError("m2A API rate limit reached")

                if response.status in _LOGIN_REDIRECT_STATUSES:
                    location = response.headers.get("Location", "")
                    await response.read()
                    raise M2AConnectionError(
                        f"m2A login unexpectedly redirected to {location or 'another page'}"
                    )

                if response.status >= 400:
                    await response.read()
                    raise M2AConnectionError(
                        f"m2A login returned HTTP {response.status}"
                    )

                data = await self._json(response)
        except M2AError:
            raise
        except (ClientError, asyncio.TimeoutError) as err:
            raise M2AConnectionError("Unable to reach m2A login service") from err

        token = data.get("token") if isinstance(data, dict) else None
        if not token or not isinstance(token, str):
            keys = sorted(data.keys()) if isinstance(data, dict) else []
            _LOGGER.warning(
                "m2A login returned HTTP 200 but no JWT token "
                "(response keys: %s)",
                keys,
            )
            raise M2AConnectionError(
                "m2A login returned HTTP 200 without an authentication token"
            )

        self._token = token
        self._login_monotonic = asyncio.get_running_loop().time()
        _LOGGER.debug("m2A authentication session renewed")

        # The browser stores the same JWT as a first-party cookie in addition
        # to sending it in Authorization. Keep both mechanisms aligned.
        self._session.cookie_jar.update_cookies(
            {"frontendaccess_token": token},
            response_url=URL(BASE_URL),
        )

    async def async_login(self) -> None:
        """Force a fresh login using the credentials stored by Home Assistant."""
        async with self._auth_lock:
            await self._async_login_locked()

    async def _async_ensure_authenticated(
        self,
        *,
        force: bool = False,
        failed_token: str | None = None,
    ) -> None:
        """Ensure a usable session, coalescing concurrent login attempts."""
        if not force and not self._auth_is_stale():
            return

        async with self._auth_lock:
            # Another request may already have refreshed the session while this
            # coroutine was waiting for the lock. In that case, reuse it.
            if (
                failed_token is not None
                and self._token is not None
                and self._token != failed_token
                and not self._auth_is_stale()
            ):
                return

            if not force and not self._auth_is_stale():
                return

            await self._async_login_locked()

    async def _json(self, response: ClientResponse) -> Any:
        """Decode a JSON response with a useful error."""
        try:
            return await response.json(content_type=None)
        except (ValueError, TypeError) as err:
            raise M2AConnectionError("m2A returned an invalid JSON response") from err

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        retry_auth: bool = True,
    ) -> Any:
        """Perform an authenticated request with one transparent session replay."""
        # Renew before the observed two-hour session boundary. This also logs
        # in lazily after startup if no token is present.
        await self._async_ensure_authenticated()

        token_used = self._token
        if token_used is None:
            raise M2AConnectionError("m2A authentication did not produce a token")

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Authorization": f"Bearer {token_used}",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/services/sde",
            "Service": "undefined",
            "User-Agent": _BROWSER_USER_AGENT,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

        try:
            async with self._session.request(
                method,
                f"{BASE_URL}{path}",
                params=params,
                headers=headers,
                timeout=self._timeout,
                allow_redirects=False,
            ) as response:
                location = response.headers.get("Location", "")
                redirected_to_login = (
                    response.status in _LOGIN_REDIRECT_STATUSES
                    and "/login" in location.lower()
                )
                returned_login_page = (
                    response.status < 400
                    and "text/html" in response.headers.get("Content-Type", "").lower()
                )
                session_expired = (
                    response.status in _AUTH_FAILURE_STATUSES
                    or redirected_to_login
                    or returned_login_page
                )

                if session_expired:
                    await response.read()
                    if retry_auth:
                        _LOGGER.debug(
                            "m2A session expired during %s %s (HTTP %s); "
                            "renewing credentials and replaying once",
                            method,
                            path,
                            response.status,
                        )
                        await self._async_ensure_authenticated(
                            force=True,
                            failed_token=token_used,
                        )
                        return await self._request_json(
                            method,
                            path,
                            params=params,
                            retry_auth=False,
                        )

                    # A fresh login succeeded, but the API still rejected the
                    # session. This is a transient service/session problem, not
                    # proof that the stored credentials are wrong.
                    raise M2AConnectionError(
                        "m2A session was rejected after automatic renewal"
                    )

                if response.status == 429:
                    await response.read()
                    raise M2AConnectionError("m2A API rate limit reached")

                if response.status >= 400:
                    await response.read()
                    raise M2AConnectionError(
                        f"m2A API returned HTTP {response.status}"
                    )

                return await self._json(response)
        except M2AError:
            raise
        except (ClientError, asyncio.TimeoutError) as err:
            raise M2AConnectionError("Unable to communicate with m2A API") from err

    async def async_get_installation(
        self,
        counter_number: str,
        *,
        force: bool = False,
    ) -> M2AInstallation:
        """Find exactly the configured meter and discard every other record.

        The portal has been observed returning unrelated subscriptions to an
        authenticated user. For privacy, no unrelated record is persisted,
        exposed as an entity, or logged.
        """
        params = {"is_visible": "true"}
        if force:
            params["force"] = "true"

        payload = await self._request_json(
            "GET",
            f"{WATER_API_PATH}/subscriptions",
            params=params,
        )

        if not isinstance(payload, list):
            raise M2AConnectionError("Unexpected subscriptions response")

        wanted = counter_number.strip().upper()

        for subscription in payload:
            if not isinstance(subscription, dict):
                continue
            installations = subscription.get("installations")
            if not isinstance(installations, list):
                continue

            for installation in installations:
                if not isinstance(installation, dict):
                    continue
                found_number = str(installation.get("counter_number", "")).strip().upper()
                if found_number != wanted:
                    continue

                reference = str(installation.get("reference", "")).strip()
                if not reference:
                    raise M2AConnectionError(
                        "Matching m2A meter has no consumption reference"
                    )

                _LOGGER.debug(
                    "Authenticated subscriptions request succeeded; configured "
                    "meter %s was found",
                    found_number,
                )
                return M2AInstallation(
                    counter_number=found_number,
                    reference=reference,
                    counter_id=installation.get("counter_id"),
                    subscription_id=subscription.get("abonnement_id"),
                    starts_at=_parse_date(subscription.get("starts_at")),
                )

        raise M2ACounterNotFound(f"Meter {wanted} was not found")

    async def async_get_consumption(
        self,
        reference: str,
        start: date,
        end: date,
    ) -> dict[str, Any]:
        """Fetch graph/daily consumption data for a date range."""
        start_text = start.strftime("%d.%m.%Y")
        end_text = end.strftime("%d.%m.%Y")
        payload = await self._request_json(
            "GET",
            (
                f"{WATER_API_PATH}/conso/{reference}/mesure/"
                f"{start_text}/{end_text}"
            ),
            params={"is_graph": "true"},
        )
        if not isinstance(payload, dict):
            raise M2AConnectionError("Unexpected consumption response")
        return payload
