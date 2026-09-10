"""Historical Recorder statistics for m2A Water."""

from __future__ import annotations

from datetime import date
import logging

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import VolumeConverter

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def statistic_id_for_counter(counter_number: str) -> str:
    """Build a valid external statistic ID."""
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in counter_number)
    slug = "_".join(part for part in slug.split("_") if part)
    return f"{DOMAIN}:{slug}_daily_consumption"


def build_statistics(
    values: dict[date, float],
    *,
    from_date: date | None = None,
) -> list[StatisticData]:
    """Build daily cumulative Recorder statistics.

    The cumulative sum is recomputed from the whole local cache, while only
    rows at/after from_date are emitted. This lets late or corrected readings
    update all affected later sums without rewriting unrelated older rows.
    """
    cumulative = 0.0
    result: list[StatisticData] = []

    for day in sorted(values):
        daily_litres = float(values[day])
        cumulative += daily_litres

        if from_date is not None and day < from_date:
            continue

        result.append(
            StatisticData(
                start=dt_util.start_of_local_day(day),
                state=daily_litres,
                sum=cumulative,
            )
        )

    return result


def add_water_statistics(
    hass: HomeAssistant,
    counter_number: str,
    values: dict[date, float],
    *,
    from_date: date | None = None,
) -> int:
    """Insert/update m2A daily water statistics in Recorder."""
    statistics = build_statistics(values, from_date=from_date)
    if not statistics:
        return 0

    metadata = StatisticMetaData(
        mean_type=StatisticMeanType.NONE,
        has_sum=True,
        name=f"m2A Eau - consommation {counter_number}",
        source=DOMAIN,
        statistic_id=statistic_id_for_counter(counter_number),
        unit_class=VolumeConverter.UNIT_CLASS,
        unit_of_measurement=UnitOfVolume.LITERS,
    )

    async_add_external_statistics(hass, metadata, statistics)
    _LOGGER.debug(
        "Queued %s m2A water statistic rows for %s",
        len(statistics),
        counter_number,
    )
    return len(statistics)
