"""Builds a scheduled run plan for a simulated train.

A `TrainRunPlan` is the MVP stand-in for what, in production, would be
rows read from the `schedules` / `train_runs` tables (see
`app/models/schedule.py`). It gives the position processor a timetable to
compare actual progress against - which is how delay is computed: the
same way a real system compares a live GPS-matched position against a
published timetable, not by inventing a random delay number.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

from app.services.track_matching import RailwayRoute, StationChainage

TrainType = Literal["FAST", "SLOW"]

# Stations a FAST LOCAL skips on this corridor (real Central Line fast
# locals skip these two between Thane and Dadar).
FAST_SKIP_CODES = {"NHU", "CHF"}

AVERAGE_DWELL_S = 20.0
FAST_CRUISE_KMH = 62.0
SLOW_CRUISE_KMH = 45.0


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
    route_line_code: str
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

    def scheduled_elapsed_s_at(self, chainage_m: float) -> float:
        """Linearly interpolate the timetable's expected elapsed-run-time
        for an arbitrary chainage, using the two bracketing scheduled stops.
        """
        for i in range(len(self.stops) - 1):
            a, b = self.stops[i], self.stops[i + 1]
            lo, hi = sorted((a.station.chainage_m, b.station.chainage_m))
            if lo <= chainage_m <= hi:
                span = hi - lo
                if span <= 0:
                    return a.scheduled_arrival_s
                frac = (chainage_m - lo) / span if a.station.chainage_m <= b.station.chainage_m else 1 - (
                    chainage_m - lo
                ) / span
                return a.scheduled_arrival_s + frac * (b.scheduled_arrival_s - a.scheduled_arrival_s)
        first, last = self.stops[0], self.stops[-1]
        return first.scheduled_arrival_s if chainage_m <= first.station.chainage_m else last.scheduled_arrival_s

    def next_stop(self, chainage_m: float) -> ScheduledStop | None:
        for stop in self.stops:
            ahead = (
                stop.station.chainage_m > chainage_m + 1e-6
                if self.direction_forward
                else stop.station.chainage_m < chainage_m - 1e-6
            )
            if ahead:
                return stop
        return None

    def current_stop(self, chainage_m: float, tolerance_m: float = 60.0) -> ScheduledStop | None:
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


def build_run_plan(
    route: RailwayRoute,
    train_id: str,
    train_type: TrainType,
    direction_forward: bool,
) -> TrainRunPlan:
    ordered = route.stations if direction_forward else list(reversed(route.stations))
    if train_type == "FAST":
        stops_stations = [sc for sc in ordered if sc.station.code not in FAST_SKIP_CODES]
        cruise_kmh = FAST_CRUISE_KMH
    else:
        stops_stations = ordered
        cruise_kmh = SLOW_CRUISE_KMH

    cruise_m_s = cruise_kmh * 1000 / 3600
    stops: list[ScheduledStop] = []
    elapsed_s = 0.0
    prev_chainage = stops_stations[0].chainage_m
    for i, sc in enumerate(stops_stations):
        if i > 0:
            leg_m = abs(sc.chainage_m - prev_chainage)
            elapsed_s += leg_m / cruise_m_s
        dwell_s = 0.0 if i == len(stops_stations) - 1 else AVERAGE_DWELL_S
        stops.append(ScheduledStop(station=sc, scheduled_arrival_s=elapsed_s, dwell_s=dwell_s))
        elapsed_s += dwell_s
        prev_chainage = sc.chainage_m

    return TrainRunPlan(
        train_id=train_id,
        train_type=train_type,
        direction_forward=direction_forward,
        route_line_code=route.line_seed.code,
        cruise_kmh=cruise_kmh,
        stops=tuple(stops),
    )


def random_train_type(rng: random.Random) -> TrainType:
    return "FAST" if rng.random() < 0.4 else "SLOW"
