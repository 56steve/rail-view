import time

from app.services.position_processor import PositionProcessor
from app.services.simulator.schedule import TrainRunPlan, build_run_plan
from app.services.telemetry import ActiveRun, RawFix
from app.services.track_matching import RailwayRoute, get_route


class _FixedScheduleProvider:
    """Minimal ScheduleProvider stub: one train, one plan, fixed start."""

    def __init__(self, active_run: ActiveRun) -> None:
        self._active_run = active_run

    def get_active_run(self, train_id: str) -> ActiveRun | None:
        return self._active_run if train_id == self._active_run.plan.train_id else None


def _make_provider(direction_forward: bool = True) -> tuple[RailwayRoute, _FixedScheduleProvider]:
    route = get_route("CR")
    plan: TrainRunPlan = build_run_plan(route, "CR-TEST", "SLOW", direction_forward)
    start_chainage = 0.0 if direction_forward else route.length_m
    started_at_epoch = time.time() - plan.scheduled_elapsed_s_at(start_chainage)
    return route, _FixedScheduleProvider(ActiveRun(plan=plan, started_at_epoch=started_at_epoch))


def test_process_batch_emits_update_for_known_train() -> None:
    route, provider = _make_provider()
    processor = PositionProcessor(route=route, schedule_provider=provider)
    lat, lon = route.position_at_chainage(500.0)
    fix = RawFix(train_id="CR-TEST", lat=lat, lon=lon, timestamp_s=time.time())

    updates = processor.process_batch([fix])

    assert len(updates) == 1
    assert updates[0].train_id == "CR-TEST"
    assert updates[0].status == "live"


def test_unknown_train_id_is_dropped_not_guessed() -> None:
    route, provider = _make_provider()
    processor = PositionProcessor(route=route, schedule_provider=provider)
    lat, lon = route.position_at_chainage(500.0)
    fix = RawFix(train_id="SOME-OTHER-TRAIN", lat=lat, lon=lon, timestamp_s=time.time())

    assert processor.process_batch([fix]) == []


def test_implausible_offset_fix_is_rejected() -> None:
    route, provider = _make_provider()
    processor = PositionProcessor(route=route, schedule_provider=provider)
    lat, lon = route.position_at_chainage(500.0)
    # ~1.1km off the rail - not a plausible GPS glitch, should be dropped
    # rather than snapped and trusted.
    fix = RawFix(train_id="CR-TEST", lat=lat + 0.01, lon=lon, timestamp_s=time.time())

    assert processor.process_batch([fix]) == []


def test_direction_is_derived_from_consecutive_chainage_deltas() -> None:
    route, provider = _make_provider(direction_forward=True)
    processor = PositionProcessor(route=route, schedule_provider=provider)
    now = time.time()
    lat1, lon1 = route.position_at_chainage(1000.0)
    lat2, lon2 = route.position_at_chainage(1200.0)

    processor.process_batch([RawFix("CR-TEST", lat1, lon1, now)])
    updates = processor.process_batch([RawFix("CR-TEST", lat2, lon2, now + 10)])

    assert updates[0].direction_forward is True
    assert updates[0].speed_kmh > 0


def test_speed_is_zero_on_the_very_first_fix_for_a_train() -> None:
    route, provider = _make_provider()
    processor = PositionProcessor(route=route, schedule_provider=provider)
    lat, lon = route.position_at_chainage(500.0)

    update = processor.process_batch([RawFix("CR-TEST", lat, lon, time.time())])[0]

    assert update.speed_kmh == 0.0


def test_current_and_next_station_are_populated_near_a_stop() -> None:
    route, provider = _make_provider()
    processor = PositionProcessor(route=route, schedule_provider=provider)
    thane_chainage = route.stations[0].chainage_m
    lat, lon = route.position_at_chainage(thane_chainage)

    update = processor.process_batch([RawFix("CR-TEST", lat, lon, time.time())])[0]

    assert update.current_station is not None
    assert update.current_station.code == "TNA"
    assert update.next_station is not None


def test_next_station_is_not_the_same_as_current_when_approaching() -> None:
    # A fix within a station's arrival tolerance but not exactly at its
    # chainage must not report that station as both current AND next.
    route, provider = _make_provider()
    processor = PositionProcessor(route=route, schedule_provider=provider)
    bhandup = route.stations[3]
    approach_chainage = bhandup.chainage_m - 30.0
    lat, lon = route.position_at_chainage(approach_chainage)

    update = processor.process_batch([RawFix("CR-TEST", lat, lon, time.time())])[0]

    assert update.current_station is not None
    assert update.current_station.code == bhandup.station.code
    assert update.next_station is not None
    assert update.next_station.code != bhandup.station.code
