from app.services.simulator.engine import SimulatedTelemetrySource
from app.services.track_matching import get_route


async def test_stream_yields_fixes_over_several_ticks() -> None:
    route = get_route("CR")
    source = SimulatedTelemetrySource(route=route, train_count=3, tick_seconds=0.01, seed=1)

    batches = []
    async for batch in source.stream():
        batches.append(batch)
        if len(batches) >= 5:
            break

    assert len(batches) == 5
    assert sum(len(b) for b in batches) > 0


def test_every_spawned_train_has_an_active_run() -> None:
    route = get_route("CR")
    source = SimulatedTelemetrySource(route=route, train_count=4, tick_seconds=1.0, seed=1)

    for i in range(4):
        assert source.get_active_run(f"CR-{i + 1:02d}") is not None


def test_unknown_train_id_has_no_active_run() -> None:
    route = get_route("CR")
    source = SimulatedTelemetrySource(route=route, train_count=2, tick_seconds=1.0, seed=1)

    assert source.get_active_run("CR-99") is None


def test_initial_spawn_alternates_direction_between_trains() -> None:
    route = get_route("CR")
    source = SimulatedTelemetrySource(route=route, train_count=4, tick_seconds=1.0, seed=7)

    directions = [source.get_active_run(f"CR-{i + 1:02d}").plan.direction_forward for i in range(4)]

    assert directions == [True, False, True, False]
