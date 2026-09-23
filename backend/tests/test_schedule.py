import random

import pytest

from app.services.simulator.physics import leg_run_time_s, profile_speed_m_s
from app.services.simulator.schedule import build_run_plan, random_train_type
from app.services.track_matching import get_route


def test_fast_local_halts_only_at_fast_stations() -> None:
    plan = build_run_plan(get_route("CR-KSRA"), "T", "FAST", direction_forward=True)
    assert all(stop.station.station.fast_halt for stop in plan.stops)
    assert [s.station.station.name for s in plan.stops][0] == "CSMT"
    assert [s.station.station.name for s in plan.stops][-1] == "Kasara"
    assert "Kalva" not in {s.station.station.name for s in plan.stops}


def test_slow_local_stops_everywhere() -> None:
    route = get_route("WR-BVI")
    plan = build_run_plan(route, "T", "SLOW", direction_forward=True)
    assert len(plan.stops) == len(route.stations)


def test_fast_is_quicker_than_slow_end_to_end() -> None:
    route = get_route("WR-BVI")
    fast = build_run_plan(route, "T", "FAST", direction_forward=True)
    slow = build_run_plan(route, "T", "SLOW", direction_forward=True)
    assert fast.total_scheduled_s < slow.total_scheduled_s


def test_slow_end_to_end_time_is_realistic() -> None:
    # Churchgate-Borivali slow locals take roughly an hour.
    plan = build_run_plan(get_route("WR-BVI"), "T", "SLOW", direction_forward=True)
    assert 45 * 60 < plan.total_scheduled_s < 75 * 60


def test_lines_without_fast_service_reject_fast_plans() -> None:
    with pytest.raises(ValueError):
        build_run_plan(get_route("HR-VSH"), "T", "FAST", direction_forward=True)


def test_reverse_plan_starts_at_the_far_terminus() -> None:
    plan = build_run_plan(get_route("CR-KSRA"), "T", "SLOW", direction_forward=False)
    assert plan.origin.station.name == "Kasara"
    assert plan.destination.station.name == "CSMT"


@pytest.mark.parametrize("forward", [True, False])
def test_scheduled_elapsed_is_monotonic_along_travel(forward: bool) -> None:
    route = get_route("HR-VSH")
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


def test_random_train_type_respects_line_service() -> None:
    rng = random.Random(1)
    assert {random_train_type(rng, get_route("HR-VSH")) for _ in range(50)} == {"SLOW"}
    assert {random_train_type(rng, get_route("CR-KSRA")) for _ in range(200)} == {"FAST", "SLOW"}


def test_profile_ramps_up_and_down() -> None:
    cruise = 15.0
    assert profile_speed_m_s(1000, 1000, cruise) == cruise
    assert profile_speed_m_s(10, 1000, cruise) < cruise / 2
    assert profile_speed_m_s(1000, 10, cruise) < cruise / 2


def test_leg_time_exceeds_pure_cruise_time() -> None:
    assert leg_run_time_s(2000, 15.0) > 2000 / 15.0
