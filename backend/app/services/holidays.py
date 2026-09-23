"""Days the Mumbai suburban network runs to its Sunday timetable.

Besides Sundays, Central Railway runs the Sunday schedule on a fixed list
of holidays (see data/sunday_schedule_holidays.json and the source PDF
in backend/data/timetables/). Six fall on the same date every year; the
rest move with the calendar and are dated per year from the Government
of Maharashtra's public holiday list, which is published each December
for the following year.

Western Railway's timetable marks the same trains "not on Sunday &
holiday", and both railways follow the one Mumbai suburban holiday list,
so it applies network-wide.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

HOLIDAYS_JSON = Path(__file__).resolve().parents[1] / "data" / "sunday_schedule_holidays.json"

logger = logging.getLogger(__name__)


class HolidayDataError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Holiday:
    name: str
    date: date


@dataclass(frozen=True, slots=True)
class HolidayCalendar:
    fixed: tuple[tuple[str, int, int], ...]  # name, month, day
    movable: dict[int, tuple[Holiday, ...]]

    def holidays_in(self, year: int) -> tuple[Holiday, ...]:
        """Every Sunday-schedule holiday in `year` that is known."""
        fixed = tuple(Holiday(name, date(year, month, day)) for name, month, day in self.fixed)
        return tuple(sorted(fixed + self.movable.get(year, ()), key=lambda h: h.date))

    def movable_dates_known(self, year: int) -> bool:
        return year in self.movable

    def holiday_on(self, day: date) -> Holiday | None:
        return next((h for h in self.holidays_in(day.year) if h.date == day), None)


@lru_cache
def load_holidays(path: Path = HOLIDAYS_JSON) -> HolidayCalendar:
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise HolidayDataError(f"{path} is missing") from exc
    fixed = tuple((entry["name"], entry["month"], entry["day"]) for entry in raw["fixed"])
    movable: dict[int, tuple[Holiday, ...]] = {}
    for year_text, entries in raw["movable"].items():
        year = int(year_text)
        holidays = tuple(Holiday(entry["name"], date.fromisoformat(entry["date"])) for entry in entries)
        if any(holiday.date.year != year for holiday in holidays):
            raise HolidayDataError(f"a {year} holiday is dated outside {year}")
        movable[year] = holidays
    return HolidayCalendar(fixed=fixed, movable=movable)


def sunday_schedule_on(day: date, calendar: HolidayCalendar) -> bool:
    """Whether trains run to the Sunday timetable on `day`, per `calendar`."""
    if day.weekday() == 6:
        return True
    if not calendar.movable_dates_known(day.year):
        _warn_unknown_year(day.year)
    return calendar.holiday_on(day) is not None


@lru_cache(maxsize=512)
def runs_sunday_schedule(day: date) -> bool:
    """`sunday_schedule_on` for the bundled holiday list - cached, since
    the live feed asks for every train every second."""
    return sunday_schedule_on(day, load_holidays())


@lru_cache(maxsize=64)
def _warn_unknown_year(year: int) -> None:
    logger.warning(
        "Sunday-schedule holidays that move with the calendar aren't listed for %d yet; "
        "only the fixed-date ones apply. Add them to %s.",
        year,
        HOLIDAYS_JSON.name,
    )
