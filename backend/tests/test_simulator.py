"""The timetable-driven simulated feed."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.simulator.engine import (
    APPEAR_BEFORE_DEPARTURE_S,
    LINGER_AFTER_ARRIVAL_S,
    TimetableTelemetrySource,
)
from app.services.timetable import load_timetable, service_midnight_epoch
from app.services.track_matching import get_all_routes

MUMBAI = ZoneInfo("Asia/Kolkata")


def at(year: int, month: int, day: int, hour: int, minute: int) -> float:
    return datetime(year, month, day, hour, minute, tzinfo=MUMBAI).timestamp()


def make_source(now: float, seed: int = 1) -> TimetableTelemetrySource:
    return TimetableTelemetrySource(get_all_routes(), load_timetable(), 1.0, seed=seed, clock=lambda: now)


WEDNESDAY_EVENING = at(2026, 9, 23, 18, 30)
SUNDAY_EVENING = at(2026, 9, 27, 18, 30)


def test_trains_on_the_map_are_exactly_the_timetabled_ones_due_now() -> None:
    source = make_source(WEDNESDAY_EVENING)
    midnight = service_midnight_epoch(datetime.fromtimestamp(WEDNESDAY_EVENING, MUMBAI).date())
    expected = {
        t.number
        for t in load_timetable().trains
        if t.runs_on(datetime.fromtimestamp(WEDNESDAY_EVENING, MUMBAI).date())
        and midnight + t.first_departure_min * 60 - APPEAR_BEFORE_DEPARTURE_S
        <= WEDNESDAY_EVENING
        <= midnight + t.last_arrival_min * 60 + LINGER_AFTER_ARRIVAL_S
    }
    assert source.running_train_ids == expected
    assert 100 < len(expected) < 400


def test_sunday_runs_the_sunday_schedule() -> None:
    timetable = load_timetable().by_number()
    sunday = make_source(SUNDAY_EVENING).running_train_ids
    assert not any(timetable[n].days in ("not_sunday", "weekdays") for n in sunday)


def test_a_train_joining_mid_run_starts_on_time() -> None:
    # Between stations, a train placed on the map mid-run is exactly where
    # its plan has it now. (At a platform, position alone can't tell the
    # scheduled arrival from the departure, so those are left out.)
    source = make_source(WEDNESDAY_EVENING)
    checked = 0
    for train_id in source.running_train_ids:
        run = source.get_active_run(train_id)
        assert run is not None
        state = source._states[train_id]
        at_platform = any(abs(stop.station.chainage_m - state.chainage_m) < 1 for stop in run.plan.stops)
        elapsed = WEDNESDAY_EVENING - run.started_at_epoch
        if 0 < elapsed < run.plan.total_scheduled_s and not at_platform:
            assert run.plan.scheduled_elapsed_s_at(state.chainage_m) == pytest.approx(elapsed, abs=2)
            checked += 1
    assert checked > 50


def test_finished_trains_leave_the_map_and_new_ones_appear() -> None:
    source = make_source(WEDNESDAY_EVENING)
    before = source.running_train_ids
    later = WEDNESDAY_EVENING + 20 * 60
    source.tick(later)
    after = source.running_train_ids
    assert before - after, "some trains should have finished within 20 minutes"
    assert after - before, "some trains should have started within 20 minutes"
    for train_id in before - after:
        assert source.get_active_run(train_id) is None


def test_fixes_stay_on_each_trains_own_route() -> None:
    source = make_source(WEDNESDAY_EVENING)
    routes = get_all_routes()
    fixes = source.tick(WEDNESDAY_EVENING + 1)
    assert len(fixes) > 0.8 * len(source.running_train_ids)
    for fix in fixes:
        run = source.get_active_run(fix.train_id)
        assert run is not None
        assert routes[run.plan.route_code].match(fix.lat, fix.lon).offset_m < 40


def test_trains_move_along_their_route_over_a_few_minutes() -> None:
    source = make_source(WEDNESDAY_EVENING)
    start = {n: s.chainage_m for n, s in source._states.items()}
    for second in range(1, 181):
        source.tick(WEDNESDAY_EVENING + second)
    moved = [n for n, s in source._states.items() if n in start and abs(s.chainage_m - start[n]) > 500]
    assert len(moved) > 0.5 * len(start)


def test_unknown_train_has_no_active_run() -> None:
    assert make_source(WEDNESDAY_EVENING).get_active_run("00000") is None
