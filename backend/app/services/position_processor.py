"""Position processor: the middle of the live pipeline.

  raw GPS fix
    -> RailwayRoute.match          (snap onto the rail, reject implausible fixes)
    -> chainage-delta smoothing    (derive speed + direction, not trust a single fix)
    -> schedule enrichment         (current/next station, ETA, delay)
    -> TrainPositionUpdate         (what actually reaches the client)

This is the module that turns "a lat/lon" into "a train physically on the
Thane-Dadar line, this far along, heading this way, this many minutes
behind schedule" - it never forwards a raw fix's coordinates directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.schemas.station import StationOut
from app.schemas.train import TrainPositionUpdate
from app.services import eta as eta_calc
from app.services.telemetry import ActiveRun, RawFix, ScheduleProvider
from app.services.track_matching import RailwayRoute, StationChainage

# Below this chainage delta (metres) between ticks, treat the train as not
# meaningfully moving and keep its previous direction instead of flipping
# on GPS-matching noise while stopped at a signal or platform.
DIRECTION_HOLD_THRESHOLD_M = 1.5

# Exponential-moving-average weight applied to each new instantaneous
# speed sample, smoothing out GPS-jitter-induced speed spikes.
SPEED_EMA_ALPHA = 0.4

# A raw fix whose nearest point on the rail is farther than this is
# treated as unreliable (multipath, GPS glitch on tunnel/bridge exit) and
# dropped rather than trusted.
MAX_PLAUSIBLE_OFFSET_M = 120.0


@dataclass(slots=True)
class _TrackedState:
    last_chainage_m: float
    last_timestamp_s: float
    direction_forward: bool
    smoothed_speed_kmh: float = 0.0


def _station_out(sc: StationChainage) -> StationOut:
    return StationOut(
        code=sc.station.code,
        name=sc.station.name,
        lat=sc.station.lat,
        lon=sc.station.lon,
        sequence=sc.station.sequence,
        chainage_m=sc.chainage_m,
    )


class PositionProcessor:
    def __init__(self, route: RailwayRoute, schedule_provider: ScheduleProvider) -> None:
        self._route = route
        self._schedules = schedule_provider
        self._tracked: dict[str, _TrackedState] = {}

    def process_batch(self, fixes: list[RawFix]) -> list[TrainPositionUpdate]:
        updates: list[TrainPositionUpdate] = []
        for fix in fixes:
            update = self._process_one(fix)
            if update is not None:
                updates.append(update)
        return updates

    def _process_one(self, fix: RawFix) -> TrainPositionUpdate | None:
        match = self._route.match(fix.lat, fix.lon)
        if match.offset_m > MAX_PLAUSIBLE_OFFSET_M:
            return None

        active_run = self._schedules.get_active_run(fix.train_id)
        if active_run is None:
            return None
        plan = active_run.plan

        speed_kmh, direction_forward = self._update_kinematics(fix, match.chainage_m, active_run)

        current_stop = plan.current_stop(match.chainage_m)
        next_stop = plan.next_stop(match.chainage_m)

        scheduled_elapsed_s = plan.scheduled_elapsed_s_at(match.chainage_m)
        actual_elapsed_s = fix.timestamp_s - active_run.started_at_epoch
        delay_seconds = eta_calc.compute_delay_seconds(actual_elapsed_s, scheduled_elapsed_s)

        eta_seconds = None
        if next_stop is not None:
            distance_m = abs(next_stop.station.chainage_m - match.chainage_m)
            eta_seconds = eta_calc.compute_eta_seconds(distance_m, speed_kmh)

        heading_deg = self._route.heading_deg_at_chainage(match.chainage_m)
        if not plan.direction_forward:
            heading_deg = (heading_deg + 180) % 360

        return TrainPositionUpdate(
            train_id=fix.train_id,
            train_type=plan.train_type,
            line_code=plan.route_line_code,
            line_name=self._route.line_seed.name,
            origin=_station_out(plan.origin),
            destination=_station_out(plan.destination),
            current_station=_station_out(current_stop.station) if current_stop else None,
            next_station=_station_out(next_stop.station) if next_stop else None,
            direction_forward=direction_forward,
            direction_label=f"{plan.origin.station.name} → {plan.destination.station.name}",
            lat=match.snapped_lat,
            lon=match.snapped_lon,
            heading_deg=heading_deg,
            chainage_m=match.chainage_m,
            speed_kmh=round(speed_kmh, 1),
            delay_seconds=round(delay_seconds, 0),
            eta_seconds=round(eta_seconds, 0) if eta_seconds is not None else None,
            status="live",
            last_updated_epoch=fix.timestamp_s,
            last_updated_iso=datetime.fromtimestamp(fix.timestamp_s, tz=UTC).isoformat(),
        )

    def _update_kinematics(
        self, fix: RawFix, chainage_m: float, active_run: ActiveRun
    ) -> tuple[float, bool]:
        prev = self._tracked.get(fix.train_id)
        default_direction = active_run.plan.direction_forward

        if prev is None:
            direction_forward = default_direction
            speed_kmh = 0.0
        else:
            delta_chainage = chainage_m - prev.last_chainage_m
            delta_t = max(fix.timestamp_s - prev.last_timestamp_s, 1e-6)
            direction_forward = (
                delta_chainage > 0
                if abs(delta_chainage) > DIRECTION_HOLD_THRESHOLD_M
                else prev.direction_forward
            )
            instantaneous_kmh = abs(delta_chainage) / delta_t * 3.6
            speed_kmh = (
                SPEED_EMA_ALPHA * instantaneous_kmh + (1 - SPEED_EMA_ALPHA) * prev.smoothed_speed_kmh
            )

        self._tracked[fix.train_id] = _TrackedState(
            last_chainage_m=chainage_m,
            last_timestamp_s=fix.timestamp_s,
            direction_forward=direction_forward,
            smoothed_speed_kmh=speed_kmh,
        )
        return speed_kmh, direction_forward
