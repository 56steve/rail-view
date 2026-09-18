import random

from app.services.simulator.schedule import FAST_SKIP_CODES, build_run_plan, random_train_type
from app.services.track_matching import get_route


def test_fast_local_skips_designated_stations() -> None:
    route = get_route("CR")
    plan = build_run_plan(route, "CR-TEST", "FAST", direction_forward=True)
    stop_codes = {stop.station.station.code for stop in plan.stops}
    assert stop_codes.isdisjoint(FAST_SKIP_CODES)


def test_slow_local_stops_everywhere() -> None:
    route = get_route("CR")
    plan = build_run_plan(route, "CR-TEST", "SLOW", direction_forward=True)
    assert len(plan.stops) == len(route.stations)


def test_scheduled_arrival_times_are_monotonically_increasing() -> None:
    route = get_route("CR")
    plan = build_run_plan(route, "CR-TEST", "SLOW", direction_forward=True)
    times = [stop.scheduled_arrival_s for stop in plan.stops]
    assert times == sorted(times)
    assert times[0] == 0.0


def test_reverse_direction_plan_starts_at_dadar() -> None:
    route = get_route("CR")
    plan = build_run_plan(route, "CR-TEST", "SLOW", direction_forward=False)
    assert plan.origin.station.code == "DR"
    assert plan.destination.station.code == "TNA"


def test_scheduled_elapsed_s_at_interpolates_between_stops() -> None:
    route = get_route("CR")
    plan = build_run_plan(route, "CR-TEST", "SLOW", direction_forward=True)
    first, second = plan.stops[0], plan.stops[1]
    midpoint_chainage = (first.station.chainage_m + second.station.chainage_m) / 2
    midpoint_elapsed = plan.scheduled_elapsed_s_at(midpoint_chainage)
    assert first.scheduled_arrival_s < midpoint_elapsed < second.scheduled_arrival_s


def test_random_train_type_is_deterministic_for_a_seeded_rng() -> None:
    rng_a = random.Random(42)
    rng_b = random.Random(42)
    assert random_train_type(rng_a) == random_train_type(rng_b)
