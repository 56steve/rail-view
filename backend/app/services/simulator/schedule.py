"""Run plans: when a train is due at every point of its run.

A `TrainRunPlan` is what the position processor compares a train's
tracked progress against - which is how delay is computed: the same way a
real system compares a live GPS-matched position against a published
timetable, not by inventing a random delay number.

Two builders:
- `timetable_run_plan` turns a train from the official timetable into a
  plan, solving each leg's cruise speed from the published times;
- `build_run_plan` derives a synthetic plan from the speed profile alone
  (every halt, or fast halts only), for tests and database seeding.

Leg times come from the same speed profile the simulator drives trains
with (`physics`), so a train that dwells and runs exactly as planned is
exactly on time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.services.platforms import PlatformAssignment
from app.services.simulator.physics import (
    cruise_for_leg_time,
    leg_run_time_s,
    leg_time_at_s,
)
from app.services.timetable import TimetabledTrain
from app.services.track_matching import RailwayRoute, StationChainage

TrainType = Literal["FAST", "SLOW"]

COACH_COUNT = 12
PLANNED_DWELL_S = 20.0
MIN_DWELL_S = 10.0
FAST_CRUISE_KMH = 70.0
SLOW_CRUISE_KMH = 55.0
# Mumbai EMUs are cleared for 100-110 km/h; plans never ask for more.
MAX_LINE_SPEED_M_S = 100.0 / 3.6
MIN_CRUISE_M_S = 2.0

# How close (along the track) a train's filtered position must be to a
# halt to count as standing at it. Trains creep the last stretch at low
# speed, so a wide tolerance would log "arrived" well before stopping.
AT_PLATFORM_TOLERANCE_M = 25.0


@dataclass(frozen=True, slots=True)
class ScheduledStop:
    station: StationChainage
    scheduled_arrival_s: float
    dwell_s: float
    # The time printed in the published timetable, where there is one: the
    # departure, or the arrival at the last stop. What commuters compare
    # against, so it's what a stop list shows. Planned arrival and dwell
    # can differ from it slightly where the plan had to absorb minute
    # rounding (see timetable_run_plan).
    published_s: float | None = None
    # Where it calls, if the station's platforms are known. Only set by
    # timetable_run_plan; synthetic plans (build_run_plan) have none.
    platform: PlatformAssignment | None = None

    @property
    def scheduled_departure_s(self) -> float:
        return self.scheduled_arrival_s + self.dwell_s

    @property
    def display_s(self) -> float:
        return self.published_s if self.published_s is not None else self.scheduled_arrival_s


@dataclass(frozen=True, slots=True)
class TrainRunPlan:
    train_id: str
    train_type: TrainType
    direction_forward: bool
    route_code: str
    line_code: str
    # Stops in travel order (already matches direction_forward), each with
    # a monotonically increasing scheduled_arrival_s; elapsed times are
    # seconds from the scheduled departure from the first stop.
    stops: tuple[ScheduledStop, ...] = field(repr=False)
    # Cruise speed for each leg: leg i runs from stops[i] to stops[i + 1].
    leg_cruise_m_s: tuple[float, ...] = field(repr=False)
    service_code: str | None = None
    ac: bool = False
    coach_count: int = COACH_COUNT

    def __post_init__(self) -> None:
        if len(self.leg_cruise_m_s) != len(self.stops) - 1:
            raise ValueError(f"{self.train_id}: {len(self.stops)} stops need {len(self.stops) - 1} leg speeds")

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

    def leg_length_m(self, leg: int) -> float:
        return abs(self.stops[leg + 1].station.chainage_m - self.stops[leg].station.chainage_m)

    def scheduled_elapsed_s_at(self, chainage_m: float) -> float:
        """Timetabled elapsed run time at an arbitrary chainage: departure
        time of the preceding halt plus the speed-profile time to cover
        the distance run since it."""
        first, last = self.stops[0], self.stops[-1]
        if not self.is_ahead(chainage_m, first.station.chainage_m):
            return first.scheduled_arrival_s
        if not self.is_ahead(last.station.chainage_m, chainage_m):
            return last.scheduled_arrival_s
        for leg, (a, b) in enumerate(zip(self.stops, self.stops[1:], strict=False)):
            if not self.is_ahead(chainage_m, b.station.chainage_m):
                run = leg_time_at_s(self.leg_length_m(leg), self.leg_cruise_m_s[leg], abs(chainage_m - a.station.chainage_m))
                return a.scheduled_departure_s + run
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


def timetable_run_plan(train: TimetabledTrain, route: RailwayRoute, service_date: date) -> TrainRunPlan:
    """A plan for one day's run of a timetabled train.

    The published times are whole minutes, so consecutive stations can be
    printed a minute apart where the train physically needs 70 seconds.
    Such a leg is given the time it needs at line speed, and the plan
    claws the overrun back from the following legs' slack, staying on the
    published times wherever it can.
    """
    if route.seed.code != train.route_code:
        raise ValueError(f"train {train.number} runs on {train.route_code}, not {route.seed.code}")
    by_name = {sc.station.name: sc for sc in route.stations}
    stations = [by_name[stop.station_name] for stop in train.stops]
    origin_departure_s = train.first_departure_min * 60.0
    last = len(train.stops) - 1

    stops = [
        ScheduledStop(
            station=stations[0],
            scheduled_arrival_s=0.0,
            dwell_s=0.0,
            published_s=0.0,
            platform=train.stops[0].platform,
        )
    ]
    cruises: list[float] = []
    for i in range(1, len(train.stops)):
        stop = train.stops[i]
        printed_arrival_s = stop.arrival_min * 60.0 - origin_departure_s
        printed_departure_s = stop.departure_min * 60.0 - origin_departure_s
        if i == last:
            dwell_s = 0.0
            target_arrival_s = published_s = printed_arrival_s
        elif printed_departure_s > printed_arrival_s:
            dwell_s = printed_departure_s - printed_arrival_s
            target_arrival_s, published_s = printed_arrival_s, printed_departure_s
        else:
            # One printed time, the departure: arrive a planned dwell before it.
            dwell_s = PLANNED_DWELL_S
            target_arrival_s, published_s = printed_departure_s - PLANNED_DWELL_S, printed_departure_s

        departed_s = stops[-1].scheduled_departure_s
        leg_m = abs(stations[i].chainage_m - stops[-1].station.chainage_m)
        run_s = min(
            max(target_arrival_s - departed_s, leg_run_time_s(leg_m, MAX_LINE_SPEED_M_S)),
            leg_run_time_s(leg_m, MIN_CRUISE_M_S),
        )
        arrival_s = departed_s + run_s
        if i != last:
            # Behind the published time: catch up by shortening the dwell,
            # down to a minimum. Early (a leg too long even at crawling
            # speed): wait at the platform for the published departure.
            behind_s = arrival_s - target_arrival_s
            dwell_s = dwell_s - min(behind_s, dwell_s - MIN_DWELL_S) if behind_s > 0 else dwell_s - behind_s
        cruises.append(cruise_for_leg_time(leg_m, run_s))
        stops.append(
            ScheduledStop(
                station=stations[i],
                scheduled_arrival_s=arrival_s,
                dwell_s=dwell_s,
                published_s=published_s,
                platform=stop.platform,
            )
        )

    return TrainRunPlan(
        train_id=train.number,
        train_type="FAST" if train.fast else "SLOW",
        direction_forward=train.direction_forward,
        route_code=train.route_code,
        line_code=train.line_code,
        stops=tuple(stops),
        leg_cruise_m_s=tuple(cruises),
        service_code=train.code,
        ac=train.ac_on(service_date),
        coach_count=train.cars,
    )


def build_run_plan(
    route: RailwayRoute,
    train_id: str,
    train_type: TrainType,
    direction_forward: bool,
) -> TrainRunPlan:
    """A synthetic plan from the speed profile alone: every halt for a
    slow train, fast halts only for a fast one, at a fixed cruise."""
    ordered = route.stations if direction_forward else list(reversed(route.stations))
    if train_type == "FAST":
        halts = [sc for sc in ordered if sc.station.fast_halt]
        cruise_kmh = FAST_CRUISE_KMH
    else:
        halts = ordered
        cruise_kmh = SLOW_CRUISE_KMH
    if len(halts) < 2:
        raise ValueError(f"{route.seed.code} has no {train_type} service with two or more halts")

    cruise_m_s = cruise_kmh / 3.6
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
        stops=tuple(stops),
        leg_cruise_m_s=tuple(cruise_m_s for _ in range(len(stops) - 1)),
    )
