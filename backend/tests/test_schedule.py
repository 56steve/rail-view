import json
import statistics
from datetime import date
from pathlib import Path

import pytest

from app.services.simulator.physics import (
    cruise_for_leg_time,
    leg_distance_at_m,
    leg_run_time_s,
    leg_time_at_s,
    profile_speed_m_s,
)
from app.services.simulator.schedule import (
    MAX_LINE_SPEED_M_S,
    build_run_plan,
    timetable_run_plan,
)
from app.services.timetable import load_timetable
from app.services.track_matching import get_route

TIMETABLE = Path(__file__).resolve().parents[1] / "app" / "data" / "generated" / "timetable.json"


def test_fast_local_halts_only_at_fast_stations() -> None:
    plan = build_run_plan(get_route("CR-KSRA"), "T", "FAST", direction_forward=True)
    assert all(stop.station.station.fast_halt for stop in plan.stops)
    assert [s.station.station.name for s in plan.stops][0] == "CSMT"
    assert [s.station.station.name for s in plan.stops][-1] == "Kasara"
    assert "Kalva" not in {s.station.station.name for s in plan.stops}


def test_slow_local_stops_everywhere() -> None:
    route = get_route("WR-VR")
    plan = build_run_plan(route, "T", "SLOW", direction_forward=True)
    assert len(plan.stops) == len(route.stations)


def test_fast_is_quicker_than_slow_end_to_end() -> None:
    route = get_route("WR-VR")
    fast = build_run_plan(route, "T", "FAST", direction_forward=True)
    slow = build_run_plan(route, "T", "SLOW", direction_forward=True)
    assert fast.total_scheduled_s < slow.total_scheduled_s


def test_slow_end_to_end_time_matches_the_official_timetable() -> None:
    # Compared with the published all-stations Churchgate - Virar trains.
    route = get_route("WR-VR")
    names = [sc.station.name for sc in route.stations]
    timetable = json.loads(TIMETABLE.read_text())
    published = [
        t["stops"][-1][1] - t["stops"][0][2]
        for t in timetable["trains"]
        if [s[0] for s in t["stops"]] == names
    ]
    assert len(published) >= 5
    plan = build_run_plan(route, "T", "SLOW", direction_forward=True)
    assert abs(plan.total_scheduled_s / 60 - statistics.median(published)) / statistics.median(published) < 0.12


def test_lines_without_fast_service_reject_fast_plans() -> None:
    with pytest.raises(ValueError):
        build_run_plan(get_route("HR-PNVL"), "T", "FAST", direction_forward=True)


def test_reverse_plan_starts_at_the_far_terminus() -> None:
    plan = build_run_plan(get_route("CR-KSRA"), "T", "SLOW", direction_forward=False)
    assert plan.origin.station.name == "Kasara"
    assert plan.destination.station.name == "CSMT"


@pytest.mark.parametrize("forward", [True, False])
def test_scheduled_elapsed_is_monotonic_along_travel(forward: bool) -> None:
    route = get_route("HR-PNVL")
    plan = build_run_plan(route, "T", "SLOW", direction_forward=forward)
    samples = [route.length_m * i / 50 for i in range(51)]
    if not forward:
        samples.reverse()
    times = [plan.scheduled_elapsed_s_at(c) for c in samples]
    assert times == sorted(times)
    assert times[0] == 0.0
    assert times[-1] == pytest.approx(plan.total_scheduled_s)


def test_scheduled_elapsed_accounts_for_dwell_before_departing() -> None:
    plan = build_run_plan(get_route("CR-KSRA"), "T", "SLOW", direction_forward=True)
    a, b = plan.stops[3], plan.stops[4]
    just_after_a = a.station.chainage_m + 0.01
    assert plan.scheduled_elapsed_s_at(just_after_a) == pytest.approx(a.scheduled_arrival_s + a.dwell_s, abs=0.1)
    assert plan.scheduled_elapsed_s_at(b.station.chainage_m) == pytest.approx(b.scheduled_arrival_s)


def test_stop_after_and_stop_for() -> None:
    plan = build_run_plan(get_route("CR-KSRA"), "T", "SLOW", direction_forward=True)
    assert plan.stop_after(plan.stops[0]) is plan.stops[1]
    assert plan.stop_after(plan.stops[-1]) is None
    assert plan.stop_for("GC") is not None
    assert plan.stop_for("XXX") is None


def test_profile_ramps_up_and_down() -> None:
    cruise = 15.0
    assert profile_speed_m_s(1000, 1000, cruise) == cruise
    assert profile_speed_m_s(10, 1000, cruise) < cruise / 2
    assert profile_speed_m_s(1000, 10, cruise) < cruise / 2


def test_leg_time_exceeds_pure_cruise_time() -> None:
    assert leg_run_time_s(2000, 15.0) > 2000 / 15.0


def test_leg_time_scales_inversely_with_cruise() -> None:
    assert leg_run_time_s(1800, 10.0) == pytest.approx(2 * leg_run_time_s(1800, 20.0))
    assert leg_time_at_s(1800, 10.0, 600) == pytest.approx(2 * leg_time_at_s(1800, 20.0, 600))


def test_cruise_solved_for_a_leg_time_meets_it_exactly() -> None:
    cruise = cruise_for_leg_time(2400, 150.0)
    assert leg_run_time_s(2400, cruise) == pytest.approx(150.0)


def test_distance_at_time_inverts_time_at_distance() -> None:
    for distance in (0.0, 120.0, 900.0, 1799.0):
        elapsed = leg_time_at_s(1800, 14.0, distance)
        assert leg_distance_at_m(1800, 14.0, elapsed) == pytest.approx(distance, abs=0.05)


WEDNESDAY = date(2026, 9, 23)


def test_timetable_plan_keeps_the_published_times() -> None:
    train = load_timetable().by_number()["96401"]  # CSMT 00:08 -> Kasara
    plan = timetable_run_plan(train, get_route(train.route_code), WEDNESDAY)
    assert plan.train_id == "96401" and plan.service_code == "N 1"
    assert plan.origin.station.name == "CSMT" and plan.destination.station.name == "Kasara"
    origin_departure = train.first_departure_min * 60
    for scheduled, published in zip(plan.stops, train.stops, strict=True):
        assert scheduled.published_s == pytest.approx(
            (published.departure_min if scheduled is not plan.stops[-1] else published.arrival_min) * 60
            - origin_departure
        )
    # On time everywhere this train's times are physically achievable.
    assert all(s.scheduled_departure_s <= s.published_s + 1 for s in plan.stops[:-1])
    assert plan.stops[-1].scheduled_arrival_s == pytest.approx(plan.stops[-1].published_s, abs=1)


def test_timetable_plans_never_exceed_line_speed_and_stay_close_to_published() -> None:
    lags = []
    for train in load_timetable().trains:
        plan = timetable_run_plan(train, get_route(train.route_code), WEDNESDAY)
        assert max(plan.leg_cruise_m_s) <= MAX_LINE_SPEED_M_S + 1e-9, train.number
        lags.append(max(s.scheduled_departure_s - s.published_s for s in plan.stops[:-1]))
    assert statistics.median(lags) <= 1
    # Minute rounding occasionally asks for more than line speed; the plan
    # absorbs it within a couple of minutes.
    assert max(lags) < 180


def test_timetable_plan_marks_fast_trains_and_rakes() -> None:
    timetable = load_timetable()
    fast = next(t for t in timetable.trains if t.fast and t.cars == 15)
    plan = timetable_run_plan(fast, get_route(fast.route_code), WEDNESDAY)
    assert plan.train_type == "FAST"
    assert plan.coach_count == 15


def test_timetable_plan_carries_each_stops_platform_through() -> None:
    train = load_timetable().by_number()["98901"]  # Panvel -> Goregaon
    plan = timetable_run_plan(train, get_route(train.route_code), WEDNESDAY)
    assert [scheduled.platform for scheduled in plan.stops] == [stop.platform for stop in train.stops]
