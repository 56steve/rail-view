from datetime import date

import pytest

from app.services.position_processor import TrainContext
from app.services.simulator.schedule import timetable_run_plan
from app.services.telemetry import ActiveRun
from app.services.timeline import build_timeline
from app.services.timetable import load_timetable
from app.services.track_matching import get_route


def test_states_split_around_the_trains_position(network) -> None:
    network.place("CR-01", "CR-KSRA", "SLOW", forward=True, at_fraction=0.43)
    timeline = build_timeline(network.processor.context("CR-01"))

    states = [stop.state for stop in timeline]
    assert states.count("next") == 1
    next_index = states.index("next")
    assert all(s == "departed" for s in states[:next_index])
    assert all(s == "upcoming" for s in states[next_index + 1 :])


def test_upcoming_times_carry_the_current_delay(network) -> None:
    network.place("CR-02", "CR-KSRA", "SLOW", forward=True, at_fraction=0.43, delay_s=180)
    timeline = build_timeline(network.processor.context("CR-02"))
    for stop in timeline:
        if stop.state in ("next", "upcoming"):
            assert stop.expected_epoch - stop.scheduled_epoch == pytest.approx(180, abs=2)


def test_stops_passed_before_tracking_began_have_no_observed_time(network) -> None:
    network.place("WR-01", "WR-VR", "SLOW", forward=True, at_fraction=0.6)
    timeline = build_timeline(network.processor.context("WR-01"))
    departed = [s for s in timeline if s.state == "departed"]
    assert departed
    assert all(s.observed_arrival_epoch is None for s in departed)
    assert all(s.expected_epoch == s.scheduled_epoch for s in departed)


def test_timeline_follows_travel_order_for_reverse_runs(network) -> None:
    network.place("HR-01", "HR-PNVL", "SLOW", forward=False, at_fraction=0.3)
    timeline = build_timeline(network.processor.context("HR-01"))
    assert timeline[0].station.name == "Panvel"
    assert timeline[-1].station.name == "CSMT"
    scheduled = [s.scheduled_epoch for s in timeline]
    assert scheduled == sorted(scheduled)


def test_timeline_carries_each_stops_platform() -> None:
    # A real train (Panvel -> Goregaon) rather than a synthetic plan, so
    # its stops carry the platforms load_timetable actually resolved.
    train = load_timetable().by_number()["98901"]
    route = get_route(train.route_code)
    plan = timetable_run_plan(train, route, date(2026, 9, 23))
    context = TrainContext(
        run=ActiveRun(plan=plan, started_at_epoch=0.0),
        route=route,
        chainage_m=plan.origin.chainage_m,
        delay_s=0.0,
        current_stop=None,
        next_stop=plan.stops[0],
        updated_at_epoch=0.0,
    )
    timeline = build_timeline(context)
    for expected, actual in zip(train.stops, timeline, strict=True):
        if expected.platform is None:
            assert actual.platform is None
        else:
            assert actual.platform is not None
            assert actual.platform.numbers == list(expected.platform.numbers)
            assert actual.platform.door == expected.platform.door
            assert actual.platform.certain == expected.platform.certain
