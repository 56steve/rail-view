import time

import pytest

from app.services.position_processor import PositionProcessor
from app.services.simulator.schedule import build_run_plan
from app.services.telemetry import ActiveRun, RawFix
from app.services.track_matching import get_all_routes, get_route


class FixedScheduleProvider:
    """Minimal ScheduleProvider: one train, one run, fixed start."""

    def __init__(self, active_run: ActiveRun) -> None:
        self.active_run = active_run

    def get_active_run(self, train_id: str) -> ActiveRun | None:
        return self.active_run if train_id == self.active_run.plan.train_id else None


def make_processor(route_code: str = "CR-KSRA", forward: bool = True, started_ago_s: float = 0.0):
    route = get_route(route_code)
    plan = build_run_plan(route, "T-1", "SLOW", forward)
    provider = FixedScheduleProvider(ActiveRun(plan=plan, started_at_epoch=time.time() - started_ago_s))
    return route, plan, provider, PositionProcessor(routes=get_all_routes(), schedule_provider=provider)


def fix_at(route, chainage: float, timestamp: float, train_id: str = "T-1") -> RawFix:
    lat, lon = route.position_at_chainage(chainage)
    return RawFix(train_id=train_id, lat=lat, lon=lon, timestamp_s=timestamp)


def test_update_is_track_matched_and_live() -> None:
    route, _, _, processor = make_processor()
    [update] = processor.process_batch([fix_at(route, 5000, time.time())])
    assert update.train_id == "T-1"
    assert update.status == "live"
    assert update.chainage_m == pytest.approx(5000, abs=1)
    assert update.line_code == "CR"
    assert update.coach_count == 12


def test_unknown_train_is_dropped_not_guessed() -> None:
    route, _, _, processor = make_processor()
    assert processor.process_batch([fix_at(route, 5000, time.time(), train_id="NOPE")]) == []


def test_fix_far_off_the_rail_is_rejected() -> None:
    _, _, _, processor = make_processor()
    # Out in the Arabian Sea off Marine Drive - nowhere near any track.
    assert processor.process_batch([RawFix("T-1", 18.93, 72.80, time.time())]) == []


def test_a_train_is_matched_against_its_own_line() -> None:
    # A Western-line position fed for a Central-line train is kilometres
    # from Central tracks near Andheri, so it must be rejected rather than
    # snapped onto the wrong line.
    wr = get_route("WR-VR")
    _, _, _, processor = make_processor("CR-KSRA")
    lat, lon = wr.position_at_chainage(wr.length_m * 0.5)
    assert processor.process_batch([RawFix("T-1", lat, lon, time.time())]) == []


def test_speed_and_direction_come_from_consecutive_fixes() -> None:
    route, _, _, processor = make_processor(forward=True)
    now = time.time()
    processor.process_batch([fix_at(route, 1000, now)])
    [update] = processor.process_batch([fix_at(route, 1150, now + 10)])
    assert update.direction_forward is True
    assert update.speed_kmh > 0


def test_first_fix_reports_stationary() -> None:
    route, _, _, processor = make_processor()
    [update] = processor.process_batch([fix_at(route, 1000, time.time())])
    assert update.speed_kmh == 0.0


def test_next_station_differs_from_current_when_just_inside_arrival_tolerance() -> None:
    route, plan, _, processor = make_processor()
    target = plan.stops[4]
    [update] = processor.process_batch([fix_at(route, target.station.chainage_m - 15, time.time())])
    assert update.current_station is not None
    assert update.current_station.code == target.station.station.code
    assert update.next_station is not None
    assert update.next_station.code != target.station.station.code


def test_on_time_train_has_near_zero_delay() -> None:
    route, plan, provider, processor = make_processor()
    chainage = (plan.stops[5].station.chainage_m + plan.stops[6].station.chainage_m) / 2
    now = provider.active_run.started_at_epoch + plan.scheduled_elapsed_s_at(chainage)
    [update] = processor.process_batch([fix_at(route, chainage, now)])
    assert abs(update.delay_seconds) <= 1


def test_late_train_reports_positive_delay() -> None:
    route, plan, provider, processor = make_processor()
    chainage = (plan.stops[5].station.chainage_m + plan.stops[6].station.chainage_m) / 2
    now = provider.active_run.started_at_epoch + plan.scheduled_elapsed_s_at(chainage) + 150
    [update] = processor.process_batch([fix_at(route, chainage, now)])
    assert update.delay_seconds == pytest.approx(150, abs=1)


def test_delay_does_not_creep_during_a_normal_dwell() -> None:
    route, plan, provider, processor = make_processor()
    stop = plan.stops[6]
    arrival = provider.active_run.started_at_epoch + stop.scheduled_arrival_s
    [on_arrival] = processor.process_batch([fix_at(route, stop.station.chainage_m, arrival)])
    [mid_dwell] = processor.process_batch([fix_at(route, stop.station.chainage_m, arrival + stop.dwell_s * 0.8)])
    assert on_arrival.delay_seconds == pytest.approx(0, abs=1)
    assert mid_dwell.delay_seconds == pytest.approx(0, abs=1)


def test_train_waiting_at_origin_is_not_early() -> None:
    route, plan, provider, processor = make_processor(started_ago_s=-120)  # departs in 2 minutes
    [update] = processor.process_batch([fix_at(route, plan.stops[0].station.chainage_m, time.time())])
    assert update.delay_seconds == 0


def test_eta_to_next_station_uses_the_timetable() -> None:
    route, plan, provider, processor = make_processor()
    a, b = plan.stops[2], plan.stops[3]
    chainage = a.station.chainage_m + (b.station.chainage_m - a.station.chainage_m) * 0.5
    now = provider.active_run.started_at_epoch + plan.scheduled_elapsed_s_at(chainage)
    [update] = processor.process_batch([fix_at(route, chainage, now)])
    expected = b.scheduled_arrival_s - plan.scheduled_elapsed_s_at(chainage)
    assert update.eta_seconds == pytest.approx(expected, abs=1.5)


def test_context_is_kept_for_timelines_and_journeys() -> None:
    route, _, _, processor = make_processor()
    processor.process_batch([fix_at(route, 3000, time.time())])
    context = processor.context("T-1")
    assert context is not None
    assert context.chainage_m == pytest.approx(3000, abs=1)
    assert "T-1" in processor.contexts()
