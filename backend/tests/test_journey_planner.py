"""Journey planning over the official timetable."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.journey_planner import (
    MISSED_GRACE_S,
    PLANNING_HORIZON_S,
    UnknownStationError,
    plan_journey,
)
from app.services.position_processor import PositionProcessor
from app.services.simulator.schedule import timetable_run_plan
from app.services.telemetry import ActiveRun, RawFix
from app.services.timetable import load_timetable, service_midnight_epoch
from app.services.track_matching import get_all_routes, get_route

MUMBAI = ZoneInfo("Asia/Kolkata")


def at(day: int, hour: int, minute: int) -> float:
    return datetime(2026, 9, day, hour, minute, tzinfo=MUMBAI).timestamp()


WEDNESDAY_0830 = at(23, 8, 30)
WEDNESDAY_0445 = at(23, 4, 45)
SUNDAY_1000 = at(27, 10, 0)


def plan(from_id: str, to_id: str, now: float, sort: str = "soonest", contexts=None, live=None):
    return plan_journey(from_id, to_id, sort, load_timetable(), contexts or {}, live or set(), now)


def test_every_option_is_a_real_train_calling_at_both_stations_soon() -> None:
    result = plan("thane", "dadar", WEDNESDAY_0830)
    timetable = load_timetable().by_number()
    assert len(result.options) == 8
    for option in result.options:
        stops = [s.station_id for s in timetable[option.train_id].stops]
        assert stops.index("thane") < stops.index("dadar")
        assert WEDNESDAY_0830 - MISSED_GRACE_S <= option.board_expected_epoch <= WEDNESDAY_0830 + PLANNING_HORIZON_S
        assert option.alight_expected_epoch > option.board_expected_epoch
        assert not option.is_live and option.delay_seconds == 0
    boards = [o.board_expected_epoch for o in result.options]
    assert boards == sorted(boards)
    assert result.interchange_hint is None


def test_trains_that_have_not_started_yet_are_offered() -> None:
    # Before the first train of the morning leaves CSMT.
    result = plan("csmt", "thane", WEDNESDAY_0445)
    assert result.options
    midnight = service_midnight_epoch(datetime.fromtimestamp(WEDNESDAY_0445, MUMBAI).date())
    first = load_timetable().by_number()[result.options[0].train_id]
    assert midnight + first.first_departure_min * 60 >= WEDNESDAY_0445 - MISSED_GRACE_S


def test_fastest_puts_the_earliest_arrival_first_and_includes_fast_trains() -> None:
    result = plan("csmt", "thane", WEDNESDAY_0830, sort="fastest")
    arrivals = [o.alight_expected_epoch for o in result.options]
    assert arrivals == sorted(arrivals)
    assert any(o.train_type == "FAST" for o in result.options)
    fast = next(o for o in result.options if o.train_type == "FAST")
    slow = next(o for o in result.options if o.train_type == "SLOW")
    assert fast.intermediate_stops < slow.intermediate_stops


def test_a_fast_train_is_not_offered_for_a_station_it_skips() -> None:
    timetable = load_timetable().by_number()
    for option in plan("csmt", "chinchpokli", WEDNESDAY_0830).options:
        assert "chinchpokli" in [s.station_id for s in timetable[option.train_id].stops]


def test_sunday_runs_the_sunday_schedule() -> None:
    timetable = load_timetable().by_number()
    options = plan("churchgate", "borivali", SUNDAY_1000).options
    assert options
    assert all(timetable[o.train_id].days in ("all", "sunday_only") for o in options)


def test_a_running_trains_delay_moves_both_ends_of_the_trip() -> None:
    timetable = load_timetable()
    train = timetable.by_number()["96401"]  # CSMT 00:08 -> Kasara, Wednesday's run
    service_date = datetime.fromtimestamp(WEDNESDAY_0830, MUMBAI).date()
    run_start = service_midnight_epoch(service_date) + train.first_departure_min * 60
    route = get_route(train.route_code)
    run_plan = timetable_run_plan(train, route, service_date)

    # Put the train 3 minutes late, halfway between its 3rd and 4th stops.
    a, b = run_plan.stops[2], run_plan.stops[3]
    chainage = (a.station.chainage_m + b.station.chainage_m) / 2
    delay_s = 180.0
    now = run_start + run_plan.scheduled_elapsed_s_at(chainage) + delay_s

    class Schedules:
        def get_active_run(self, train_id: str) -> ActiveRun | None:
            return ActiveRun(run_plan, run_start) if train_id == train.number else None

    processor = PositionProcessor(routes=get_all_routes(), schedule_provider=Schedules())
    lat, lon = route.position_at_chainage(chainage)
    processor.process_batch([RawFix(train.number, lat, lon, now)])

    later_stops = [s for s in train.stops[4:] if s.station_id != train.stops[-1].station_id]
    board, alight = later_stops[0], later_stops[-1]
    result = plan(board.station_id, alight.station_id, now, contexts=processor.contexts(), live={train.number})
    option = next(o for o in result.options if o.train_id == train.number)
    midnight = service_midnight_epoch(service_date)
    assert option.is_live
    assert option.delay_seconds == pytest.approx(delay_s, abs=2)
    assert option.board_expected_epoch == pytest.approx(midnight + board.departure_min * 60 + delay_s, abs=2)
    assert option.board_scheduled_epoch == pytest.approx(midnight + board.departure_min * 60)


def test_cross_line_journey_gets_an_interchange_hint() -> None:
    result = plan("thane", "bandra", WEDNESDAY_0830)
    assert result.options == []
    # Dadar (Central to Western) or Kurla (Central to the Harbour branch
    # through Bandra) both work; the hint names the shorter detour.
    assert result.interchange_hint is not None
    assert result.interchange_hint.startswith("No direct train - change at ")
    assert any(station in result.interchange_hint for station in ("Dadar", "Kurla"))


def test_journey_across_central_branches_changes_at_kalyan() -> None:
    result = plan("titwala", "badlapur", WEDNESDAY_0830)
    assert result.options == []
    assert result.interchange_hint == "No direct train - change at Kalyan for the Khopoli branch"


def test_same_branch_journey_needs_no_interchange() -> None:
    assert plan("thane", "kasara", WEDNESDAY_0830).interchange_hint is None


def test_same_station_has_no_options() -> None:
    assert plan("dadar", "dadar", WEDNESDAY_0830).options == []


def test_unknown_station_raises() -> None:
    with pytest.raises(UnknownStationError):
        plan("atlantis", "dadar", WEDNESDAY_0830)
