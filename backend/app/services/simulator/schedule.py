"""Builds a scheduled run plan for a simulated train.

A `TrainRunPlan` is the MVP stand-in for what, in production, would be
rows read from the `schedules` / `train_runs` tables (see
`app/models/schedule.py`). It gives the position processor a timetable to
compare actual progress against - which is how delay is computed: the
same way a real system compares a live GPS-matched position against a
published timetable, not by inventing a random delay number.

Leg times come from integrating the same speed profile the simulator
drives trains with (`physics.leg_run_time_s`), so a train that dwells and
runs exactly as planned is exactly on time.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

from app.services.simulator.physics import leg_profile, leg_run_time_s
from app.services.track_matching import RailwayRoute, StationChainage

TrainType = Literal["FAST", "SLOW"]

COACH_COUNT = 12
PLANNED_DWELL_S = 20.0
FAST_CRUISE_KMH = 70.0
SLOW_CRUISE_KMH = 55.0
FAST_SHARE = 0.4

# How close (along the track) a train's filtered position must be to a
# halt to count as standing at it. Trains creep the last stretch at low
# speed, so a wide tolerance would log "arrived" well before stopping.
AT_PLATFORM_TOLERANCE_M = 25.0


@dataclass(frozen=True, slots=True)
class ScheduledStop:
    station: StationChainage
    scheduled_arrival_s: float
    dwell_s: float


@dataclass(frozen=True, slots=True)
class TrainRunPlan:
    train_id: str
    train_type: TrainType
    direction_forward: bool
    route_code: str
    line_code: str
    cruise_kmh: float
    # Stops in travel order (already matches direction_forward), each with
    # a monotonically increasing scheduled_arrival_s.
    stops: tuple[ScheduledStop, ...] = field(repr=False)

    @property
    def origin(self) -> StationChainage:
        return self.stops[0].station

    @property
    def destination(self) -> StationChainage:
        return self.stops[-1].station

    @property
    def total_scheduled_s(self) -> float:
        return self.stops[-1].scheduled_arrival_s

    def is_ahead(self, chainage_m: float, of_chainage_m: float) -> bool:
        """Whether `chainage_m` lies beyond `of_chainage_m` in travel direction."""
        return chainage_m > of_chainage_m if self.direction_forward else chainage_m < of_chainage_m

    def scheduled_elapsed_s_at(self, chainage_m: float) -> float:
        """Timetabled elapsed run time at an arbitrary chainage: departure
        time of the preceding halt plus the speed-profile time to cover
        the distance run since it."""
        first, last = self.stops[0], self.stops[-1]
        if not self.is_ahead(chainage_m, first.station.chainage_m):
            return first.scheduled_arrival_s
        if not self.is_ahead(last.station.chainage_m, chainage_m):
            return last.scheduled_arrival_s
        cruise_m_s = self.cruise_kmh / 3.6
        for a, b in zip(self.stops, self.stops[1:], strict=False):
            if not self.is_ahead(chainage_m, b.station.chainage_m):
                profile = leg_profile(abs(b.station.chainage_m - a.station.chainage_m), cruise_m_s)
                departed_s = a.scheduled_arrival_s + a.dwell_s
                return departed_s + profile.time_at(abs(chainage_m - a.station.chainage_m))
        return last.scheduled_arrival_s

    def next_stop(self, chainage_m: float) -> ScheduledStop | None:
        for stop in self.stops:
            gap = abs(stop.station.chainage_m - chainage_m)
            if gap > 1e-6 and self.is_ahead(stop.station.chainage_m, chainage_m):
                return stop
        return None

    def current_stop(self, chainage_m: float, tolerance_m: float = AT_PLATFORM_TOLERANCE_M) -> ScheduledStop | None:
        for stop in self.stops:
            if abs(stop.station.chainage_m - chainage_m) <= tolerance_m:
                return stop
        return None

    def stop_after(self, stop: ScheduledStop) -> ScheduledStop | None:
        """The next stop in travel order after `stop`. Used instead of a
        chainage-based `next_stop` lookup once a current stop is already
        resolved, so a train sitting just inside the arrival tolerance of
        a station can't show that same station as both current AND next.
        """
        index = self.stops.index(stop)
        return self.stops[index + 1] if index + 1 < len(self.stops) else None

    def stop_for(self, station_code: str) -> ScheduledStop | None:
        return next((s for s in self.stops if s.station.station.code == station_code), None)


def build_run_plan(
    route: RailwayRoute,
    train_id: str,
    train_type: TrainType,
    direction_forward: bool,
) -> TrainRunPlan:
    ordered = route.stations if direction_forward else list(reversed(route.stations))
    if train_type == "FAST":
        halts = [sc for sc in ordered if sc.station.fast_halt]
        cruise_kmh = FAST_CRUISE_KMH
    else:
        halts = ordered
        cruise_kmh = SLOW_CRUISE_KMH
    if len(halts) < 2:
        raise ValueError(f"{route.seed.code} has no {train_type} service with two or more halts")

    cruise_m_s = cruise_kmh * 1000 / 3600
    stops: list[ScheduledStop] = []
    elapsed_s = 0.0
    for i, sc in enumerate(halts):
        if i > 0:
            elapsed_s += leg_run_time_s(abs(sc.chainage_m - halts[i - 1].chainage_m), cruise_m_s)
        dwell_s = 0.0 if i == len(halts) - 1 else PLANNED_DWELL_S
        stops.append(ScheduledStop(station=sc, scheduled_arrival_s=elapsed_s, dwell_s=dwell_s))
        elapsed_s += dwell_s

    return TrainRunPlan(
        train_id=train_id,
        train_type=train_type,
        direction_forward=direction_forward,
        route_code=route.seed.code,
        line_code=route.seed.line.code,
        cruise_kmh=cruise_kmh,
        stops=tuple(stops),
    )


def random_train_type(rng: random.Random, route: RailwayRoute) -> TrainType:
    if not route.seed.has_fast_service:
        return "SLOW"
    return "FAST" if rng.random() < FAST_SHARE else "SLOW"
