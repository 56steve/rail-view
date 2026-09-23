"""Sunday-schedule holidays."""

import json
import logging
from datetime import date
from pathlib import Path

import pytest

from app.services.holidays import HolidayDataError, load_holidays, sunday_schedule_on
from app.services.timetable import load_timetable

FIXED = [(1, 26), (4, 14), (5, 1), (8, 15), (10, 2), (12, 25)]


@pytest.mark.parametrize("year", [2026, 2027, 2030])
def test_fixed_date_holidays_apply_every_year(year: int) -> None:
    calendar = load_holidays()
    for month, day in FIXED:
        assert calendar.holiday_on(date(year, month, day)) is not None


def test_2026_movable_holidays_follow_the_maharashtra_list() -> None:
    calendar = load_holidays()
    assert calendar.holiday_on(date(2026, 9, 14)).name == "Ganesh Chaturthi"
    assert calendar.holiday_on(date(2026, 3, 3)).name == "Holi (second day)"
    # Central's list covers both Diwali days.
    assert calendar.holiday_on(date(2026, 11, 8)) is not None
    assert calendar.holiday_on(date(2026, 11, 10)) is not None
    assert len(calendar.holidays_in(2026)) == 14


def test_sundays_and_holidays_run_the_sunday_schedule_other_days_dont() -> None:
    calendar = load_holidays()
    assert sunday_schedule_on(date(2026, 9, 20), calendar)  # a Sunday
    assert sunday_schedule_on(date(2026, 9, 14), calendar)  # Ganesh Chaturthi, a Monday
    assert not sunday_schedule_on(date(2026, 9, 15), calendar)  # an ordinary Tuesday
    assert not sunday_schedule_on(date(2026, 9, 19), calendar)  # an ordinary Saturday


def test_a_year_without_movable_dates_warns_and_keeps_the_fixed_ones(caplog) -> None:
    calendar = load_holidays()
    with caplog.at_level(logging.WARNING):
        assert sunday_schedule_on(date(2031, 1, 26), calendar)
        assert not sunday_schedule_on(date(2031, 3, 4), calendar)
    assert "2031" in caplog.text


def test_misdated_holiday_data_is_rejected(tmp_path: Path) -> None:
    bad = {"fixed": [], "movable": {"2026": [{"name": "Typo", "date": "2027-03-03"}]}}
    path = tmp_path / "holidays.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(HolidayDataError):
        load_holidays.__wrapped__(path)


def test_on_a_weekday_holiday_trains_run_the_sunday_schedule() -> None:
    trains = load_timetable().trains
    ganesh_chaturthi, ordinary_monday, sunday = date(2026, 9, 14), date(2026, 9, 21), date(2026, 9, 20)
    on_holiday = {t.number for t in trains if t.runs_on(ganesh_chaturthi)}
    assert on_holiday == {t.number for t in trains if t.runs_on(sunday)}
    assert len(on_holiday) < sum(t.runs_on(ordinary_monday) for t in trains)
    assert not any(t.days in ("not_sunday", "weekdays") for t in trains if t.number in on_holiday)
