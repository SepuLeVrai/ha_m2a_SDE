"""Data coordinator for m2A Water."""

from __future__ import annotations

import asyncio
import calendar
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
import logging
from typing import Any

from aiohttp import ClientSession

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    M2AAuthError,
    M2AConnectionError,
    M2ACounterNotFound,
    M2AInstallation,
    M2AWaterApi,
    parse_daily_values,
    parse_previous_year_values,
)
from .const import (
    CONF_COUNTER_NUMBER,
    CONF_REFERENCE,
    CONF_STARTS_AT,
    DOMAIN,
    FORCE_REFRESH_INTERVAL,
    HISTORY_REQUEST_DELAY_SECONDS,
    RECENT_HISTORY_DAYS,
    STORE_VERSION,
    UPDATE_INTERVAL,
)
from .statistics import add_water_statistics, statistic_id_for_counter

_LOGGER = logging.getLogger(__name__)

_HISTORY_IMPORT_VERSION = 2


@dataclass(frozen=True, slots=True)
class M2AWaterData:
    """Current data exposed to entities."""

    counter_number: str
    reference: str
    index_l: float | None
    last_reading_date: date | None
    last_daily_l: float | None
    last_daily_date: date | None
    month_l: float
    previous_year_same_period_l: float | None
    evolution_percent: float | None
    average_daily_l: float | None
    previous_year_average_daily_l: float | None
    history_days: int
    history_first_date: date | None
    history_last_date: date | None
    history_last_sync: datetime | None
    statistic_id: str


type M2AWaterConfigEntry = ConfigEntry["M2AWaterCoordinator"]


def _month_bounds(day: date) -> tuple[date, date]:
    """Return first and last date of a month."""
    last_day = calendar.monthrange(day.year, day.month)[1]
    return day.replace(day=1), day.replace(day=last_day)


def _next_month(day: date) -> date:
    """Return first day of the next month."""
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def _parse_last_reading(payload: dict[str, Any]) -> tuple[date | None, float | None]:
    """Extract the latest official meter index, expressed in litres."""
    last = payload.get("dernierReleve")
    if not isinstance(last, dict):
        return None, None

    raw_date = last.get("date")
    reading_date: date | None = None
    if raw_date:
        try:
            reading_date = datetime.fromisoformat(
                str(raw_date).replace("Z", "+00:00")
            ).date()
        except ValueError:
            try:
                reading_date = date.fromisoformat(str(raw_date)[:10])
            except ValueError:
                pass

    raw_index = last.get("index")
    try:
        index_l = float(raw_index) if raw_index is not None else None
    except (TypeError, ValueError):
        index_l = None

    return reading_date, index_l


class M2AWaterCoordinator(DataUpdateCoordinator[M2AWaterData]):
    """Coordinate m2A API updates and Recorder history."""

    config_entry: M2AWaterConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: M2AWaterConfigEntry,
        session: ClientSession,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            always_update=True,
            config_entry=config_entry,
        )
        self._session = session
        self._counter_number = str(
            config_entry.data[CONF_COUNTER_NUMBER]
        ).strip().upper()
        self._api = M2AWaterApi(
            session,
            str(config_entry.data[CONF_USERNAME]),
            str(config_entry.data[CONF_PASSWORD]),
        )
        self._installation: M2AInstallation | None = None
        self._last_force_refresh: datetime | None = None
        self._history_lock = asyncio.Lock()
        self._history: dict[date, float] = {}
        self._history_last_sync: datetime | None = None
        self._history_import_version = 0
        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORE_VERSION,
            f"{DOMAIN}.{config_entry.entry_id}.history",
        )

    @property
    def counter_number(self) -> str:
        return self._counter_number

    @property
    def reference(self) -> str:
        if self._installation:
            return self._installation.reference
        return str(self.config_entry.data.get(CONF_REFERENCE, ""))

    @property
    def has_history(self) -> bool:
        return bool(self._history)

    @property
    def full_history_synced(self) -> bool:
        """Return whether the current full-history algorithm completed."""
        return self._history_import_version >= _HISTORY_IMPORT_VERSION

    async def _async_setup(self) -> None:
        """Authenticate, validate the selected meter and load local cache."""
        cached = await self._store.async_load()
        if isinstance(cached, dict):
            raw_values = cached.get("values", {})
            if isinstance(raw_values, dict):
                for raw_day, raw_value in raw_values.items():
                    try:
                        self._history[date.fromisoformat(raw_day)] = float(raw_value)
                    except (TypeError, ValueError):
                        continue

            raw_sync = cached.get("last_sync")
            if raw_sync:
                try:
                    self._history_last_sync = datetime.fromisoformat(raw_sync)
                except ValueError:
                    pass

            # v0.1.4 deliberately ignores the old boolean-only completion
            # marker once. The previous forward importer could stop on the
            # first unavailable historical month and therefore falsely leave
            # users with only recent history.
            self._history_import_version = int(
                cached.get("history_import_version", 0) or 0
            )

        try:
            await self._api.async_login()
            self._installation = await self._api.async_get_installation(
                self._counter_number,
                force=False,
            )
        except M2AAuthError as err:
            raise ConfigEntryAuthFailed("Invalid m2A credentials") from err
        except M2ACounterNotFound as err:
            raise ConfigEntryAuthFailed(
                f"Configured meter {self._counter_number} is not available"
            ) from err
        except M2AConnectionError as err:
            raise ConfigEntryNotReady("Unable to connect to m2A water service") from err

        # Keep discovered, non-secret metadata current.
        data = dict(self.config_entry.data)
        changed = False
        if data.get(CONF_REFERENCE) != self._installation.reference:
            data[CONF_REFERENCE] = self._installation.reference
            changed = True
        if self._installation.starts_at:
            starts_at = self._installation.starts_at.isoformat()
            if data.get(CONF_STARTS_AT) != starts_at:
                data[CONF_STARTS_AT] = starts_at
                changed = True
        if changed:
            self.hass.config_entries.async_update_entry(self.config_entry, data=data)

    async def _async_update_data(self) -> M2AWaterData:
        """Fetch the current month and request a meter-data refresh hourly."""
        try:
            now = dt_util.now()
            if (
                self._last_force_refresh is None
                or now - self._last_force_refresh >= FORCE_REFRESH_INTERVAL
            ):
                self._installation = await self._api.async_get_installation(
                    self._counter_number,
                    force=True,
                )
                self._last_force_refresh = now

            month_start, month_end = _month_bounds(now.date())
            payload = await self._api.async_get_consumption(
                self.reference,
                month_start,
                month_end,
            )

            current_values = parse_daily_values(payload)
            previous_values = parse_previous_year_values(payload)
            await self._merge_history(current_values)

            return self._build_data(payload, current_values, previous_values)

        except M2AAuthError as err:
            raise ConfigEntryAuthFailed("m2A authentication expired") from err
        except M2ACounterNotFound as err:
            raise ConfigEntryAuthFailed(
                f"Configured meter {self._counter_number} is no longer available"
            ) from err
        except M2AConnectionError as err:
            raise UpdateFailed("Error communicating with m2A water service") from err

    def _build_data(
        self,
        payload: dict[str, Any],
        current_values: dict[date, float],
        previous_values: dict[date, float],
    ) -> M2AWaterData:
        """Build entity-facing data."""
        last_reading_date, index_l = _parse_last_reading(payload)

        last_daily_date = max(current_values) if current_values else None
        last_daily_l = (
            current_values[last_daily_date] if last_daily_date is not None else None
        )
        month_l = sum(current_values.values())

        # consoPointsBefore is N-1 relabelled with N dates. Compare only through
        # the latest day actually available in N, avoiding partial-vs-full-month
        # distortion early in the current month.
        comparable_previous = previous_values
        if last_daily_date is not None:
            comparable_previous = {
                day: value
                for day, value in previous_values.items()
                if day <= last_daily_date
            }

        previous_l = (
            sum(comparable_previous.values()) if comparable_previous else None
        )
        evolution = None
        if previous_l not in (None, 0):
            evolution = ((month_l - previous_l) / previous_l) * 100.0

        avg = (
            sum(current_values.values()) / len(current_values)
            if current_values
            else None
        )
        previous_avg = (
            sum(comparable_previous.values()) / len(comparable_previous)
            if comparable_previous
            else None
        )

        history_days = len(self._history)
        history_first = min(self._history) if self._history else None
        history_last = max(self._history) if self._history else None

        return M2AWaterData(
            counter_number=self._counter_number,
            reference=self.reference,
            index_l=index_l,
            last_reading_date=last_reading_date,
            last_daily_l=last_daily_l,
            last_daily_date=last_daily_date,
            month_l=month_l,
            previous_year_same_period_l=previous_l,
            evolution_percent=evolution,
            average_daily_l=avg,
            previous_year_average_daily_l=previous_avg,
            history_days=history_days,
            history_first_date=history_first,
            history_last_date=history_last,
            history_last_sync=self._history_last_sync,
            statistic_id=statistic_id_for_counter(self._counter_number),
        )

    async def _save_history(self) -> None:
        """Persist the local daily cache without credentials or raw API data."""
        await self._store.async_save(
            {
                "values": {
                    day.isoformat(): value
                    for day, value in sorted(self._history.items())
                },
                "last_sync": (
                    self._history_last_sync.isoformat()
                    if self._history_last_sync
                    else None
                ),
                "full_history_synced": self.full_history_synced,
                "history_import_version": self._history_import_version,
            }
        )

    async def _merge_history(self, values: dict[date, float]) -> int:
        """Merge values and update Recorder from the earliest changed date."""
        if not values:
            return 0

        changed_dates: list[date] = []
        for day, value in values.items():
            old = self._history.get(day)
            if old is None or abs(old - value) > 0.0001:
                self._history[day] = value
                changed_dates.append(day)

        if not changed_dates:
            return 0

        earliest = min(changed_dates)
        self._history_last_sync = dt_util.now()

        try:
            rows = add_water_statistics(
                self.hass,
                self._counter_number,
                self._history,
                from_date=earliest,
            )
        except Exception:
            # Current sensors must keep working even if Recorder is disabled or
            # unavailable. History stays cached and will retry on next change.
            _LOGGER.exception("Unable to queue m2A water Recorder statistics")
            rows = 0

        await self._save_history()
        return rows

    async def async_sync_history(self, *, full: bool = False) -> None:
        """Import full history once, then refresh a rolling recent window."""
        async with self._history_lock:
            if self._installation is None:
                return

            try:
                if full or not self._history:
                    await self._async_full_history_sync()
                else:
                    await self._async_recent_history_sync()
            except M2AAuthError as err:
                _LOGGER.warning("Historical m2A sync stopped: authentication failed")
                raise ConfigEntryAuthFailed from err
            except M2ACounterNotFound as err:
                _LOGGER.warning("Historical m2A sync stopped: meter not found")
                raise ConfigEntryAuthFailed from err
            except M2AConnectionError as err:
                _LOGGER.warning("Historical m2A sync failed: %s", err)
            except Exception:
                _LOGGER.exception("Unexpected error during m2A historical sync")

    @staticmethod
    def _map_previous_year_history(
        values: dict[date, float],
    ) -> dict[date, float]:
        """Map portal N-1 comparison dates back to their real year.

        consoPointsBefore is returned with the current graph's year so the web
        UI can overlay both curves. The values are genuinely N-1, therefore
        historical storage must shift them back one year.
        """
        mapped: dict[date, float] = {}
        for displayed_day, value in values.items():
            try:
                real_day = displayed_day.replace(year=displayed_day.year - 1)
            except ValueError:
                # Defensive handling for a 29-Feb label mapped onto a
                # non-leap previous year. The portal normally omits this case.
                continue
            mapped[real_day] = value
        return mapped

    async def _async_full_history_sync(self) -> None:
        """Fetch all available history, newest month first.

        Subscription start is not necessarily telemetry start. Some old
        periods may therefore be unavailable or rejected by the provider.
        A failed month is skipped instead of aborting the entire import.
        Progress is persisted after every successful month so an interruption
        never loses already downloaded history.
        """
        start_day = self._installation.starts_at
        if start_day is None:
            raw = self.config_entry.data.get(CONF_STARTS_AT)
            try:
                start_day = date.fromisoformat(str(raw)) if raw else None
            except ValueError:
                start_day = None

        if start_day is None:
            start_day = dt_util.now().date() - timedelta(days=365)

        oldest_month = start_day.replace(day=1)
        cursor = dt_util.now().date().replace(day=1)

        # Force v0.1.4+ to complete before considering the backfill valid.
        self._history_import_version = 0
        await self._save_history()

        attempted = 0
        successful = 0
        unavailable = 0
        total_new_or_updated = 0

        _LOGGER.debug(
            "m2A history: full backfill started (newest month first)"
        )

        while cursor >= oldest_month:
            attempted += 1
            month_start, month_end = _month_bounds(cursor)

            try:
                payload = await self._api.async_get_consumption(
                    self.reference,
                    month_start,
                    month_end,
                )
            except M2AAuthError:
                raise
            except M2AConnectionError as err:
                # Rate limiting should pause the whole operation and retry on
                # the next restart/manual backfill rather than hammering API.
                if "rate limit" in str(err).lower():
                    _LOGGER.warning(
                        "m2A history: API rate limit reached after %s months; "
                        "progress has been kept and the backfill will retry later",
                        attempted - 1,
                    )
                    await self._save_history()
                    return

                unavailable += 1
                _LOGGER.debug(
                    "m2A history: skipping unavailable period %s (%s)",
                    cursor.strftime("%Y-%m"),
                    err,
                )
            else:
                successful += 1
                current = parse_daily_values(payload)

                # User confirmed that consoPointsBefore is the same period N-1.
                previous = self._map_previous_year_history(
                    parse_previous_year_values(payload)
                )

                changed = 0
                for day, value in {**previous, **current}.items():
                    old = self._history.get(day)
                    if old is None or abs(old - value) > 0.0001:
                        self._history[day] = value
                        changed += 1

                total_new_or_updated += changed
                if changed:
                    self._history_last_sync = dt_util.now()

                # Persist and publish each step: the "historical days" sensor
                # visibly grows while the backfill runs.
                await self._save_history()
                self._publish_history_metadata()

            # Move one month backwards.
            if cursor.month == 1:
                cursor = date(cursor.year - 1, 12, 1)
            else:
                cursor = date(cursor.year, cursor.month - 1, 1)

            if cursor >= oldest_month:
                await asyncio.sleep(HISTORY_REQUEST_DELAY_SECONDS)

        # Recorder sums must be generated only after the complete cache has
        # been assembled, because we downloaded it in reverse chronological
        # order.
        if self._history:
            try:
                add_water_statistics(
                    self.hass,
                    self._counter_number,
                    self._history,
                    from_date=min(self._history),
                )
            except Exception:
                _LOGGER.exception("Unable to queue full m2A Recorder history")

        self._history_import_version = _HISTORY_IMPORT_VERSION
        self._history_last_sync = dt_util.now()
        await self._save_history()
        self._publish_history_metadata()

        _LOGGER.debug(
            "m2A history: full backfill completed: %s periods requested, "
            "%s successful, %s unavailable, %s daily values cached "
            "(%s changed during this run)",
            attempted,
            successful,
            unavailable,
            len(self._history),
            total_new_or_updated,
        )

    async def _async_recent_history_sync(self) -> None:
        """Refetch recent months to catch late/missing/corrected daily readings."""
        today = dt_util.now().date()
        start = today - timedelta(days=RECENT_HISTORY_DAYS)
        cursor = start.replace(day=1)
        current_month = today.replace(day=1)
        values: dict[date, float] = {}

        while cursor <= current_month:
            month_start, month_end = _month_bounds(cursor)
            payload = await self._api.async_get_consumption(
                self.reference,
                month_start,
                month_end,
            )
            values.update(parse_daily_values(payload))
            cursor = _next_month(cursor)
            if cursor <= current_month:
                await asyncio.sleep(HISTORY_REQUEST_DELAY_SECONDS)

        await self._merge_history(values)
        self._history_last_sync = dt_util.now()
        await self._save_history()
        self._publish_history_metadata()

    def _publish_history_metadata(self) -> None:
        """Refresh diagnostic history fields on already-created entities."""
        if self.data is None:
            return
        self.async_set_updated_data(
            replace(
                self.data,
                history_days=len(self._history),
                history_first_date=min(self._history) if self._history else None,
                history_last_date=max(self._history) if self._history else None,
                history_last_sync=self._history_last_sync,
            )
        )

    async def async_manual_refresh(self) -> None:
        """Equivalent of the portal's 'update data' button."""
        try:
            self._installation = await self._api.async_get_installation(
                self._counter_number,
                force=True,
            )
            self._last_force_refresh = dt_util.now()
        except M2AAuthError as err:
            raise ConfigEntryAuthFailed from err
        except (M2AConnectionError, M2ACounterNotFound) as err:
            raise UpdateFailed("Unable to force m2A meter refresh") from err

        await self.async_request_refresh()

    async def async_close(self) -> None:
        """Detach the private session without closing HA's shared connector."""
        if not self._session.closed:
            self._session.detach()
