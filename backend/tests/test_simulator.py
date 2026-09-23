from collections import Counter

from app.services.simulator.engine import SimulatedTelemetrySource
from app.services.track_matching import get_all_routes


def make_source(trains_per_route: int = 4, tick: float = 1.0, seed: int = 1) -> SimulatedTelemetrySource:
    return SimulatedTelemetrySource(
        routes=get_all_routes(), trains_per_route=trains_per_route, tick_seconds=tick, seed=seed
    )


async def test_stream_yields_fixes_over_several_ticks() -> None:
    source = make_source(tick=0.01)
    batches = []
    async for batch in source.stream():
        batches.append(batch)
        if len(batches) >= 5:
            break
    assert len(batches) == 5
    assert sum(len(b) for b in batches) > 0


def test_every_route_gets_its_trains_numbered_per_line() -> None:
    source = make_source(trains_per_route=3)
    routes_per_line = Counter(route.seed.line.code for route in get_all_routes().values())
    for line_code, route_count in routes_per_line.items():
        runs = [source.get_active_run(f"{line_code}-{i + 1:02d}") for i in range(3 * route_count)]
        assert all(run is not None and run.plan.line_code == line_code for run in runs)
        assert source.get_active_run(f"{line_code}-{3 * route_count + 1:02d}") is None


def test_central_trains_run_both_branches() -> None:
    source = make_source(trains_per_route=3)
    route_codes = {source.get_active_run(f"CR-{i + 1:02d}").plan.route_code for i in range(6)}
    assert route_codes == {"CR-KSRA", "CR-KP"}


def test_directions_alternate_within_a_route() -> None:
    source = make_source(trains_per_route=4)
    directions = [source.get_active_run(f"CR-{i + 1:02d}").plan.direction_forward for i in range(4)]
    assert directions == [True, False, True, False]


def test_harbour_and_trans_harbour_run_slow_only() -> None:
    source = make_source(trains_per_route=10)
    for code in ("HR", "THR"):
        types = {source.get_active_run(f"{code}-{i + 1:02d}").plan.train_type for i in range(10)}
        assert types == {"SLOW"}


def test_unknown_train_has_no_active_run() -> None:
    assert make_source().get_active_run("CR-99") is None


async def test_emitted_fixes_stay_near_the_trains_own_route() -> None:
    source = make_source(tick=0.01)
    routes = get_all_routes()
    async for batch in source.stream():
        for fix in batch:
            run = source.get_active_run(fix.train_id)
            assert routes[run.plan.route_code].match(fix.lat, fix.lon).offset_m < 40
        break
