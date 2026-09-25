"""Position processor: the middle of the live pipeline.

  raw GPS fix
    -> RailwayRoute.match          (snap onto the train's line, reject implausible fixes)
    -> TrackFilter (Kalman)        (smooth chainage, derive speed + direction)
    -> schedule enrichment         (current/next station, delay, ETAs)
    -> TrainPositionUpdate         (what reaches the client)

This is the module that turns "a lat/lon" into "a train physically on the
Central line, this far along, heading this way, this many minutes behind
schedule" - it never forwards a raw fix's coordinates directly.

It also keeps a `TrainContext` per train (latest chainage, delay, observed
arrival times), which is what per-train timelines and journey plans are
computed from.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from app.schemas.station import StationOut, StationRef
from app.schemas.train import TrainPositionUpdate
from app.services.platforms import PlatformAssignment
from app.services.simulator.schedule import ScheduledStop
from app.services.telemetry import ActiveRun, RawFix, ScheduleProvider
from app.services.track_filter import TrackFilter
from app.services.track_matching import RailwayRoute, StationChainage

# Below this filtered speed, keep the previous direction instead of
# flipping on residual noise while stopped at a signal or platform.
DIRECTION_HOLD_M_S = 0.3

# Filtered speeds below this are reported as stationary.
STATIONARY_KMH = 4.0

# A fix this far from where the filter predicts the train to be means the
# filter's state is no longer valid (e.g. a telemetry gap long enough
# for real movement), so it restarts from the fix.
FILTER_RESET_JUMP_M = 500.0

# A raw fix whose nearest point on the rail is farther than this is
# treated as unreliable (multipath, GPS glitch on bridge exit) and
# dropped rather than trusted.
MAX_PLAUSIBLE_OFFSET_M = 120.0


@dataclass(slots=True)
class _Kinematics:
    run_started_at_epoch: float
    filter: TrackFilter
    direction_forward: bool


@dataclass(slots=True)
class TrainContext:
    """Latest processed state for one train."""

    run: ActiveRun
    route: RailwayRoute
    chainage_m: float
    delay_s: float
    current_stop: ScheduledStop | None
    next_stop: ScheduledStop | None
    updated_at_epoch: float
    observed_arrivals: dict[str, float] = field(default_factory=dict)

    def scheduled_epoch(self, stop: ScheduledStop) -> float:
        return self.run.started_at_epoch + stop.scheduled_arrival_s

    def published_epoch(self, stop: ScheduledStop) -> float:
        """The time the published timetable gives for `stop`."""
        return self.run.started_at_epoch + stop.display_s

    def expected_epoch(self, stop: ScheduledStop) -> float:
        """When this train is expected at `stop`, given its current delay."""
        return self.scheduled_epoch(stop) + self.delay_s

    def has_passed(self, stop: ScheduledStop) -> bool:
        if self.current_stop is stop:
            return False
        return not self.run.plan.is_ahead(stop.station.chainage_m, self.chainage_m)


def station_out(sc: StationChainage) -> StationOut:
    return StationOut(
        code=sc.station.code,
        name=sc.station.name,
        lat=sc.station.lat,
        lon=sc.station.lon,
        sequence=sc.station.sequence,
        chainage_m=sc.chainage_m,
        fast_halt=sc.station.fast_halt,
    )


def station_ref(sc: StationChainage) -> StationRef:
    return StationRef(code=sc.station.code, name=sc.station.name)


class PositionProcessor:
    def __init__(self, routes: Mapping[str, RailwayRoute], schedule_provider: ScheduleProvider) -> None:
        self._routes = routes
        self._schedules = schedule_provider
        self._kinematics: dict[str, _Kinematics] = {}
        self._contexts: dict[str, TrainContext] = {}

    def context(self, train_id: str) -> TrainContext | None:
        return self._contexts.get(train_id)

    def forget(self, train_id: str) -> None:
        """Drop everything known about a train whose run has ended."""
        self._contexts.pop(train_id, None)
        self._kinematics.pop(train_id, None)

    def contexts(self) -> Mapping[str, TrainContext]:
        return MappingProxyType(self._contexts)

    def process_batch(self, fixes: list[RawFix]) -> list[TrainPositionUpdate]:
        updates: list[TrainPositionUpdate] = []
        for fix in fixes:
            update = self._process_one(fix)
            if update is not None:
                updates.append(update)
        return updates

    def _process_one(self, fix: RawFix) -> TrainPositionUpdate | None:
        active_run = self._schedules.get_active_run(fix.train_id)
        if active_run is None:
            return None
        plan = active_run.plan
        route = self._routes[plan.route_code]

        match = route.match(fix.lat, fix.lon)
        if match.offset_m > MAX_PLAUSIBLE_OFFSET_M:
            return None

        chainage_m, speed_kmh, direction_forward = self._update_kinematics(fix, match.chainage_m, active_run)
        chainage_m = min(max(chainage_m, 0.0), route.length_m)

        previous = self._contexts.get(fix.train_id)
        same_run = previous is not None and previous.run.started_at_epoch == active_run.started_at_epoch
        observed = previous.observed_arrivals if same_run and previous is not None else {}

        current_stop = plan.current_stop(chainage_m)
        next_stop = plan.stop_after(current_stop) if current_stop is not None else plan.next_stop(chainage_m)
        delay_s = self._delay_s(fix, chainage_m, active_run, current_stop, observed)

        context = TrainContext(
            run=active_run,
            route=route,
            chainage_m=chainage_m,
            delay_s=delay_s,
            current_stop=current_stop,
            next_stop=next_stop,
            updated_at_epoch=fix.timestamp_s,
            observed_arrivals=observed,
        )
        self._contexts[fix.train_id] = context

        lat, lon = route.position_at_chainage(chainage_m)
        heading_deg = route.heading_deg_at_chainage(chainage_m)
        if not direction_forward:
            heading_deg = (heading_deg + 180) % 360

        eta_seconds = (
            max(0.0, context.expected_epoch(next_stop) - fix.timestamp_s) if next_stop is not None else None
        )
        next_platform: PlatformAssignment | None = next_stop.platform if next_stop is not None else None
        return TrainPositionUpdate(
            train_id=fix.train_id,
            train_type=plan.train_type,
            line_code=plan.line_code,
            line_name=route.seed.line.name,
            route_code=plan.route_code,
            service_code=plan.service_code,
            ac=plan.ac,
            coach_count=plan.coach_count,
            origin=station_ref(plan.origin),
            destination=station_ref(plan.destination),
            current_station=station_ref(current_stop.station) if current_stop is not None else None,
            next_station=station_ref(next_stop.station) if next_stop is not None else None,
            next_platform=",".join(next_platform.numbers) if next_platform is not None else None,
            next_platform_certain=next_platform.certain if next_platform is not None else False,
            next_platform_door=next_platform.door if next_platform is not None else None,
            direction_forward=direction_forward,
            direction_label=f"{plan.origin.station.name} → {plan.destination.station.name}",
            lat=lat,
            lon=lon,
            heading_deg=heading_deg,
            chainage_m=chainage_m,
            speed_kmh=round(speed_kmh, 1),
            delay_seconds=round(delay_s),
            eta_seconds=round(eta_seconds) if eta_seconds is not None else None,
            destination_eta_seconds=round(max(0.0, context.expected_epoch(plan.stops[-1]) - fix.timestamp_s)),
            status="live",
            last_updated_epoch=fix.timestamp_s,
        )

    @staticmethod
    def _delay_s(
        fix: RawFix,
        chainage_m: float,
        run: ActiveRun,
        current_stop: ScheduledStop | None,
        observed: dict[str, float],
    ) -> float:
        plan = run.plan
        actual_elapsed_s = fix.timestamp_s - run.started_at_epoch
        if current_stop is None:
            return actual_elapsed_s - plan.scheduled_elapsed_s_at(chainage_m)

        # At a halt: hold the lateness observed on arrival rather than
        # letting it creep up through a normal dwell, and only add to it
        # once the train overstays its timetabled departure.
        departure_delay_s = actual_elapsed_s - (current_stop.scheduled_arrival_s + current_stop.dwell_s)
        if current_stop is plan.stops[0]:
            # Waiting to depart its origin: can't be "early" before it has
            # started, only late once it overstays departure time.
            return max(0.0, departure_delay_s)
        arrived_at = observed.setdefault(current_stop.station.station.code, fix.timestamp_s)
        arrival_delay_s = (arrived_at - run.started_at_epoch) - current_stop.scheduled_arrival_s
        return max(arrival_delay_s, departure_delay_s)

    def _update_kinematics(
        self, fix: RawFix, measured_chainage_m: float, run: ActiveRun
    ) -> tuple[float, float, bool]:
        """Returns (filtered chainage, speed km/h, direction_forward)."""
        state = self._kinematics.get(fix.train_id)
        restart = state is None or state.run_started_at_epoch != run.started_at_epoch
        if state is not None and not restart:
            dt = fix.timestamp_s - state.filter.timestamp_s
            predicted = state.filter.chainage_m + state.filter.velocity_m_s * dt
            restart = abs(measured_chainage_m - predicted) > FILTER_RESET_JUMP_M

        if restart or state is None:
            # First fix of a run: no velocity information yet, so trust the
            # timetable's direction and report stationary.
            state = _Kinematics(
                run_started_at_epoch=run.started_at_epoch,
                filter=TrackFilter.start(measured_chainage_m, fix.timestamp_s),
                direction_forward=run.plan.direction_forward,
            )
            self._kinematics[fix.train_id] = state
            return measured_chainage_m, 0.0, state.direction_forward

        state.filter.update(measured_chainage_m, fix.timestamp_s)
        velocity = state.filter.velocity_m_s
        if abs(velocity) > DIRECTION_HOLD_M_S:
            state.direction_forward = velocity > 0
        speed_kmh = abs(velocity) * 3.6
        return state.filter.chainage_m, (0.0 if speed_kmh < STATIONARY_KMH else speed_kmh), state.direction_forward
