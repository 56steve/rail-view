"""Simulated telemetry, driven by the official timetable.

Stands in for a live railway GPS feed. This is the ONLY module that
"cheats" by knowing a train's true position: everything downstream
(`PositionProcessor`) only ever sees the noisy `RawFix` batches this
module emits via `stream()`, and re-derives position, speed and direction
the same way it would from a real feed. That is what lets a live source
replace this module without touching anything else.

Which trains run, and when, comes from the official timetable: at any
moment the trains on the map are exactly the ones Central and Western
Railway schedule to be running then, with their real numbers and rakes.
Only their exact progress is simulated:
  - each leg is run on the speed profile at the cruise speed that meets
    the timetable (`schedule.timetable_run_plan`);
  - dwell times vary around the timetabled dwell, with occasional long
    stops (crowding, door obstruction), which is what makes trains drift
    late - so delay emerges rather than being made up; a late train runs
    a little faster, within line speed, to recover;
  - each raw GPS fix gets gaussian positional jitter plus an occasional
    dropped fix, simulating consumer-grade GPS noise and signal gaps.
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from datetime import date

from app.services.simulator.physics import leg_distance_at_m, profile_speed_m_s
from app.services.simulator.schedule import MAX_LINE_SPEED_M_S, TrainRunPlan, timetable_run_plan
from app.services.telemetry import ActiveRun, RawFix
from app.services.timetable import (
    Timetable,
    TimetabledTrain,
    service_dates_near,
    service_midnight_epoch,
)
from app.services.track_matching import RailwayRoute

# A rake stands at its origin platform for a while before departure.
APPEAR_BEFORE_DEPARTURE_S = 180.0
# ...and at its destination for a moment after arriving.
LINGER_AFTER_ARRIVAL_S = 60.0
# A train this far behind its plan runs faster, within line speed.
LATE_THRESHOLD_S = 30.0
RECOVERY_SPEEDUP = 1.08

GPS_JITTER_STDDEV_M = 6.0
GPS_DROPOUT_PROBABILITY = 0.04
SPEED_NOISE_FRACTION = 0.04
DWELL_NOISE_MEAN_S = 4.0
DWELL_NOISE_STDDEV_S = 6.0
LONG_DWELL_PROBABILITY = 0.07
LONG_DWELL_EXTRA_S = (15.0, 75.0)


@dataclass(slots=True)
class _TrainState:
    route: RailwayRoute
    plan: TrainRunPlan
    service_date: date
    run_started_at_epoch: float  # scheduled departure from the first stop
    chainage_m: float
    speed_kmh: float
    dwell_remaining_s: float
    stop_index: int  # index into plan.stops of the next halt to reach
    last_halt_chainage_m: float
    arrived: bool = False


@dataclass(frozen=True, slots=True)
class _Service:
    """One day's run of a timetabled train."""

    train: TimetabledTrain
    service_date: date
    departs_at_epoch: float
    arrives_at_epoch: float


class TimetableTelemetrySource:
    """Runs every timetabled train that is due now and yields raw, noisy
    GPS fixes for them every `tick_seconds`."""

    def __init__(
        self,
        routes: Mapping[str, RailwayRoute],
        timetable: Timetable,
        tick_seconds: float,
        seed: int | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._routes = routes
        self._timetable = timetable
        self._tick_seconds = tick_seconds
        self._clock = clock
        self._rng = random.Random(seed)
        self._states: dict[str, _TrainState] = {}
        self.sync(clock())

    # -- which trains are running --------------------------------------

    def services_due(self, now_epoch: float) -> dict[str, _Service]:
        """Every timetabled run whose time on the map covers `now_epoch`,
        by train number (a number runs once per service day)."""
        due: dict[str, _Service] = {}
        for service_date in service_dates_near(now_epoch)[:2]:  # yesterday's late trains, today's
            midnight = service_midnight_epoch(service_date)
            for train in self._timetable.trains:
                departs = midnight + train.first_departure_min * 60.0
                arrives = midnight + train.last_arrival_min * 60.0
                on_map = departs - APPEAR_BEFORE_DEPARTURE_S <= now_epoch <= arrives + LINGER_AFTER_ARRIVAL_S
                if on_map and train.runs_on(service_date):
                    due[train.number] = _Service(train, service_date, departs, arrives)
        return due

    def sync(self, now_epoch: float) -> None:
        """Put trains that have become due on the map, at the point of
        their run the timetable has them at, and take finished ones off."""
        due = self.services_due(now_epoch)
        for number in [n for n, state in self._states.items() if n not in due]:
            del self._states[number]
        for number, service in due.items():
            state = self._states.get(number)
            if state is None or state.service_date != service.service_date:
                self._states[number] = self._spawn(service, now_epoch)

    def _spawn(self, service: _Service, now_epoch: float) -> _TrainState:
        route = self._routes[service.train.route_code]
        plan = timetable_run_plan(service.train, route, service.service_date)
        elapsed = now_epoch - service.departs_at_epoch
        state = _TrainState(
            route=route,
            plan=plan,
            service_date=service.service_date,
            run_started_at_epoch=service.departs_at_epoch,
            chainage_m=plan.origin.chainage_m,
            speed_kmh=0.0,
            dwell_remaining_s=max(0.0, -elapsed),
            stop_index=1,
            last_halt_chainage_m=plan.origin.chainage_m,
        )
        if elapsed <= 0:
            return state  # standing at the origin, waiting to depart

        last = plan.stops[-1]
        if elapsed >= last.scheduled_arrival_s:
            state.chainage_m = state.last_halt_chainage_m = last.station.chainage_m
            state.stop_index = len(plan.stops) - 1
            state.arrived = True
            return state

        # Mid-run: exactly where the plan has it, so it starts on time.
        for i in range(1, len(plan.stops)):
            previous, stop = plan.stops[i - 1], plan.stops[i]
            if elapsed < previous.scheduled_departure_s:
                # Dwelling at the previous stop.
                state.chainage_m = state.last_halt_chainage_m = previous.station.chainage_m
                state.dwell_remaining_s = previous.scheduled_departure_s - elapsed
                state.stop_index = i
                return state
            if elapsed < stop.scheduled_arrival_s:
                into_leg = leg_distance_at_m(
                    plan.leg_length_m(i - 1), plan.leg_cruise_m_s[i - 1], elapsed - previous.scheduled_departure_s
                )
                step = into_leg if plan.direction_forward else -into_leg
                state.chainage_m = previous.station.chainage_m + step
                state.last_halt_chainage_m = previous.station.chainage_m
                state.speed_kmh = plan.leg_cruise_m_s[i - 1] * 3.6
                state.stop_index = i
                return state
        return state

    def get_active_run(self, train_id: str) -> ActiveRun | None:
        state = self._states.get(train_id)
        if state is None:
            return None
        return ActiveRun(plan=state.plan, started_at_epoch=state.run_started_at_epoch)

    @property
    def running_train_ids(self) -> set[str]:
        return set(self._states)

    # -- motion ------------------------------------------------------------

    async def stream(self) -> AsyncIterator[list[RawFix]]:
        """One batch of fixes every `tick_seconds`, on a fixed beat: the
        time spent simulating (and by whoever consumes each batch) comes out
        of the wait, rather than adding to it. A tick that overruns is
        followed straight away by the next one, and the beat restarts from
        there instead of bursting to catch up."""
        loop = asyncio.get_running_loop()
        deadline = loop.time()
        while True:
            deadline += self._tick_seconds
            delay = deadline - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                deadline = loop.time()
            yield self.tick(self._clock())

    def tick(self, now_epoch: float) -> list[RawFix]:
        """Advance every running train by one tick and return its fixes."""
        self.sync(now_epoch)
        fixes: list[RawFix] = []
        for train_id, state in self._states.items():
            self._advance(state, now_epoch)
            fix = self._maybe_emit_fix(train_id, state, now_epoch)
            if fix is not None:
                fixes.append(fix)
        return fixes

    def _advance(self, state: _TrainState, now_epoch: float) -> None:
        dt = self._tick_seconds
        if state.arrived:
            state.speed_kmh = 0.0
            return
        if state.dwell_remaining_s > 0:
            state.speed_kmh = 0.0
            state.dwell_remaining_s = max(0.0, state.dwell_remaining_s - dt)
            return

        plan = state.plan
        leg = state.stop_index - 1
        target = plan.stops[state.stop_index]
        to_next = abs(target.station.chainage_m - state.chainage_m)
        since_last = abs(state.chainage_m - state.last_halt_chainage_m)
        cruise_m_s = plan.leg_cruise_m_s[leg]
        lateness_s = (now_epoch - state.run_started_at_epoch) - plan.scheduled_elapsed_s_at(state.chainage_m)
        if lateness_s > LATE_THRESHOLD_S and cruise_m_s < MAX_LINE_SPEED_M_S:
            cruise_m_s = min(cruise_m_s * RECOVERY_SPEEDUP, MAX_LINE_SPEED_M_S)
        speed_m_s = profile_speed_m_s(since_last, to_next, cruise_m_s)
        speed_m_s = max(0.5, speed_m_s * (1 + self._rng.gauss(0.0, SPEED_NOISE_FRACTION)))
        state.speed_kmh = speed_m_s * 3.6

        step = speed_m_s * dt
        if step < to_next:
            state.chainage_m += step if plan.direction_forward else -step
            return

        state.chainage_m = state.last_halt_chainage_m = target.station.chainage_m
        state.speed_kmh = 0.0
        if state.stop_index == len(plan.stops) - 1:
            state.arrived = True
        else:
            state.dwell_remaining_s = self._actual_dwell_s(target.dwell_s)
            state.stop_index += 1

    def _actual_dwell_s(self, planned_s: float) -> float:
        extra = max(-planned_s * 0.3, self._rng.gauss(DWELL_NOISE_MEAN_S, DWELL_NOISE_STDDEV_S))
        if self._rng.random() < LONG_DWELL_PROBABILITY:
            extra += self._rng.uniform(*LONG_DWELL_EXTRA_S)
        return planned_s + extra

    def _maybe_emit_fix(self, train_id: str, state: _TrainState, now_s: float) -> RawFix | None:
        # A dwelling train still emits fixes (stationary but live), so it
        # doesn't visually disappear from the client while stopped.
        if self._rng.random() < GPS_DROPOUT_PROBABILITY:
            return None
        true_lat, true_lon = state.route.position_at_chainage(state.chainage_m)
        lat, lon = _jitter_latlon(true_lat, true_lon, GPS_JITTER_STDDEV_M, self._rng)
        return RawFix(train_id=train_id, lat=lat, lon=lon, timestamp_s=now_s)


def _jitter_latlon(lat: float, lon: float, stddev_m: float, rng: random.Random) -> tuple[float, float]:
    dx_m = rng.gauss(0.0, stddev_m)
    dy_m = rng.gauss(0.0, stddev_m)
    meters_per_deg_lat = 111_320.0
    meters_per_deg_lon = 111_320.0 * math.cos(math.radians(lat))
    return lat + dy_m / meters_per_deg_lat, lon + dx_m / max(meters_per_deg_lon, 1.0)
