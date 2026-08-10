"""Long-term statistics injection for the Energy Dashboard.

APS publishes usage in daily batches with a ~1-day lag, so live sensors can
only ever record a whole day's energy in the hour HA happens to poll it.
Instead, this module writes history straight into HA's recorder as external
statistics (the same approach as the core Opower integration): hourly values
fetched day-by-day from APS, backdated to the hour they actually occurred.

Statistic IDs (selectable in the Energy Dashboard under "statistics"):
  aps_usage:<account>_consumption       (non-solar accounts)
  aps_usage:<account>_grid_import       (solar accounts)
  aps_usage:<account>_grid_export      (solar accounts)
  aps_usage:<account>_solar_generation  (solar accounts)
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .api import APSSolarData, APSUsageAPI, APSUsageData, _ci_get
from .const import (
    DOMAIN,
    STATS_BACKFILL_DAYS,
    STATS_MAX_DAYS_PER_RUN,
    STATS_OVERLAP_DAYS,
)

try:  # HA >= 2025.4 deprecates has_mean in favor of mean_type
    from homeassistant.components.recorder.models import StatisticMeanType

    _MEAN_KWARGS: dict[str, Any] = {"mean_type": StatisticMeanType.NONE}
except ImportError:
    _MEAN_KWARGS = {"has_mean": False}

_LOGGER = logging.getLogger(__name__)

_TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\s*(AM|PM)?", re.IGNORECASE)


def _parse_hour(text: Any) -> int | None:
    """Hour of day from an APS time label ("01:00 AM", "13:00", ...)."""
    match = _TIME_RE.search(str(text or ""))
    if not match:
        return None
    hour = int(match.group(1))
    meridiem = (match.group(3) or "").upper()
    if meridiem == "AM":
        hour = 0 if hour == 12 else hour
    elif meridiem == "PM":
        hour = 12 if hour == 12 else hour + 12
    return hour if 0 <= hour <= 23 else None


def _parse_day(text: Any) -> date | None:
    try:
        return datetime.strptime(str(text or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _fnum(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _usage_kwh(item: dict) -> float | None:
    value = _fnum(_ci_get(item, "totalUsage"))
    if value is None:
        value = _fnum(_ci_get(item, "totalDailyUsage"))
    return value


def _row_ts(row: dict) -> float:
    """Row start as a unix timestamp (older HA returned datetimes)."""
    start = row["start"]
    return start if isinstance(start, (int, float)) else start.timestamp()


@dataclass(frozen=True)
class _Stream:
    """One statistic series and how to read its kWh from an APS series item."""

    key: str
    name: str
    value: Callable[[dict], float | None]


_USAGE_STREAMS: tuple[_Stream, ...] = (
    _Stream("consumption", "APS Energy Consumption", _usage_kwh),
)

_SOLAR_STREAMS: tuple[_Stream, ...] = (
    _Stream(
        "grid_import",
        "APS Grid Import",
        lambda item: APSSolarData._value(item, *APSSolarData._IMPORT),
    ),
    _Stream(
        "grid_export",
        "APS Grid Export",
        lambda item: APSSolarData._value(item, *APSSolarData._EXPORTED),
    ),
    _Stream(
        "solar_generation",
        "APS Solar Generation",
        lambda item: APSSolarData._value(item, *APSSolarData._GENERATED),
    ),
)


class APSStatistics:
    """Fetches hourly APS history and writes it into recorder statistics."""

    def __init__(self, hass: HomeAssistant, api: APSUsageAPI) -> None:
        self.hass = hass
        self.api = api
        # Latest data date already written, per source — skips the day-by-day
        # refetch on the (hourly) coordinator refreshes that bring no new data.
        self._last_processed: dict[str, date] = {}

    def _stat_id(self, key: str) -> str:
        account = re.sub(
            r"[^a-z0-9]", "", str(self.api.account_id or "account").lower()
        )
        return f"{DOMAIN}:{account}_{key}"

    async def async_update(
        self, usage: APSUsageData | None, solar: APSSolarData | None
    ) -> None:
        """Bring long-term statistics up to date with the latest APS data."""
        if self.api.is_solar:
            if solar is not None:
                await self._update_source(
                    "solar", _SOLAR_STREAMS, solar.series, self._fetch_solar_day
                )
        elif usage is not None:
            await self._update_source(
                "usage", _USAGE_STREAMS, usage.series, self._fetch_usage_day
            )

    async def _fetch_usage_day(self, day: str) -> list[dict] | None:
        try:
            return await self.api.get_hourly_usage(day)
        except Exception as err:  # noqa: BLE001 — fall back to daily totals
            _LOGGER.debug("APS: hourly usage fetch failed for %s: %s", day, err)
            return None

    async def _fetch_solar_day(self, day: str) -> list[dict] | None:
        try:
            return await self.api.get_solar_hourly(day)
        except Exception as err:  # noqa: BLE001 — fall back to daily totals
            _LOGGER.debug("APS: hourly solar fetch failed for %s: %s", day, err)
            return None

    async def _update_source(
        self,
        source: str,
        streams: tuple[_Stream, ...],
        daily_series: list[dict],
        fetch_day: Callable[[str], Awaitable[list[dict] | None]],
    ) -> None:
        # Per-day totals from the already-fetched daily series: they define
        # which days APS has published, and serve as the hourly fallback.
        daily: dict[str, dict[date, float]] = {s.key: {} for s in streams}
        for item in daily_series:
            day = _parse_day(_ci_get(item, "date"))
            if day is None:
                continue
            for stream in streams:
                value = stream.value(item)
                if value is not None:
                    daily[stream.key][day] = value

        published = {day for per_day in daily.values() for day in per_day}
        if not published:
            return
        latest = max(published)
        if self._last_processed.get(source) == latest:
            return

        recorder = get_instance(self.hass)

        # Where each stream's statistics currently end.
        last_day: dict[str, date] = {}
        for stream in streams:
            stat_id = self._stat_id(stream.key)
            last = await recorder.async_add_executor_job(
                get_last_statistics, self.hass, 1, stat_id, True, {"sum"}
            )
            if last:
                last_day[stream.key] = dt_util.as_local(
                    dt_util.utc_from_timestamp(_row_ts(last[stat_id][0]))
                ).date()

        # Window: everything new, plus the last OVERLAP days already written
        # (APS revises estimated readings), or a full backfill for new streams.
        starts = [
            last_day[s.key] - timedelta(days=STATS_OVERLAP_DAYS - 1)
            if s.key in last_day
            else latest - timedelta(days=STATS_BACKFILL_DAYS - 1)
            for s in streams
        ]
        window_start = max(
            min(starts), latest - timedelta(days=STATS_MAX_DAYS_PER_RUN - 1)
        )
        days = [
            window_start + timedelta(days=offset)
            for offset in range((latest - window_start).days + 1)
        ]

        # One hourly request per published day, shared by all streams.
        hourly: dict[date, list[dict] | None] = {}
        for day in days:
            if day not in published:
                continue
            hourly[day] = await fetch_day(day.strftime("%Y-%m-%d"))
            await asyncio.sleep(0.2)

        fetched = sum(1 for series in hourly.values() if series)
        _LOGGER.debug(
            "APS: statistics update (%s): %d day(s), hourly data for %d",
            source,
            len(days),
            fetched,
        )

        for stream in streams:
            await self._write_stream(
                stream, daily[stream.key], hourly, days, last_day.get(stream.key)
            )

        self._last_processed[source] = latest

    async def _write_stream(
        self,
        stream: _Stream,
        daily_map: dict[date, float],
        hourly: dict[date, list[dict] | None],
        days: list[date],
        stream_last_day: date | None,
    ) -> None:
        stat_id = self._stat_id(stream.key)
        window_start_dt = dt_util.start_of_local_day(days[0])

        # Existing rows around the window: seed the running sum and anchor
        # any already-written day we cannot re-fetch this run.
        existing = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            window_start_dt - timedelta(days=45),
            None,
            {stat_id},
            "hour",
            None,
            {"sum"},
        )
        existing_rows = existing.get(stat_id, [])

        running = self._existing_sum_before(existing_rows, window_start_dt)
        if running is None:
            running = 0.0

        stats: list[StatisticData] = []
        for day in days:
            day_start = dt_util.start_of_local_day(day)
            next_day_start = dt_util.start_of_local_day(day + timedelta(days=1))

            buckets: dict[int, float] = {}
            for item in hourly.get(day) or []:
                # Usage items label the hour via readTime; solar items via date
                hour = _parse_hour(_ci_get(item, "readTime"))
                if hour is None:
                    hour = _parse_hour(_ci_get(item, "date"))
                value = stream.value(item)
                if hour is None or value is None:
                    continue
                buckets[hour] = buckets.get(hour, 0.0) + value

            if buckets:
                for hour in sorted(buckets):
                    start = day_start + timedelta(hours=hour)
                    if start >= next_day_start and stats:
                        # DST short day: fold the spillover hour into the
                        # previous row rather than colliding with midnight.
                        running += buckets[hour]
                        prev = stats[-1]
                        prev["state"] = round(prev["state"] + buckets[hour], 3)
                        prev["sum"] = round(running, 3)
                        continue
                    running += buckets[hour]
                    stats.append(
                        StatisticData(
                            start=start,
                            state=round(buckets[hour], 3),
                            sum=round(running, 3),
                        )
                    )
            elif stream_last_day is None or day > stream_last_day:
                # No hourly data for a not-yet-written day — record the day
                # total at midnight so the day is at least attributed
                # correctly. Never do this for days that may already hold
                # hourly rows: a midnight row would double-count them.
                day_total = daily_map.get(day)
                if day_total is not None:
                    running += day_total
                    stats.append(
                        StatisticData(
                            start=day_start,
                            state=round(day_total, 3),
                            sum=round(running, 3),
                        )
                    )
            else:
                # Already-written day we couldn't re-fetch: anchor the
                # running sum to the DB so later days stay consistent.
                anchored = self._existing_sum_before(existing_rows, next_day_start)
                if anchored is not None:
                    running = anchored

        if not stats:
            return

        metadata = StatisticMetaData(
            has_sum=True,
            name=stream.name,
            source=DOMAIN,
            statistic_id=stat_id,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            **_MEAN_KWARGS,
        )
        async_add_external_statistics(self.hass, metadata, stats)

    @staticmethod
    def _existing_sum_before(rows: list[dict], cutoff: datetime) -> float | None:
        """Last recorded cumulative sum strictly before a point in time."""
        cutoff_ts = cutoff.timestamp()
        best: float | None = None
        for row in rows:
            if _row_ts(row) >= cutoff_ts:
                break
            if row.get("sum") is not None:
                best = row["sum"]
        return best
