"""Simulated telemetry source: stands in for a live railway GPS feed.

This is the ONLY module that "cheats" by knowing a train's true position.
Everything downstream (`PositionProcessor`) only ever sees the noisy
`RawFix` batches this module emits via `stream()`, and re-derives
position/speed/direction the same way it would from a real vendor feed.
That is what lets a `LiveRailwayApiSource` replace this module later
without touching anything else.

Model (deliberately simple, not full train dynamics):
  - speed follows `physics.profile_speed_m_s` (ramp up after a halt,
    cruise, ramp down into the next halt) with small multiplicative noise.
  - dwell times vary around the timetabled dwell, with occasional long
    stops (crowding, door obstruction). This is what makes trains drift
    behind their timetable, so "delay" is an emergent property of the
    simulation rather than a number fabricated for display.
  - each raw GPS fix gets gaussian positional jitter plus an occasional
    dropped fix, simulating consumer-grade GPS noise and signal gaps.
  - on reaching its destination, the same rake forms the return working
    in the opposite direction after a layover.
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass

from app.services.simulator.physics import profile_speed_m_s
from app.services.simulator.schedule import TrainRunPlan, build_run_plan, random_train_type
from app.services.telemetry import ActiveRun, RawFix
from app.services.track_matching import RailwayRoute

LAYOVER_S = 120.0
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
    chainage_m: float
    speed_kmh: float
    dwell_remaining_s: float
    stop_index: int  # index into plan.stops of the next halt to reach
    last_halt_chainage_m: float
    run_started_at_epoch: float
    terminated: bool = False


class SimulatedTelemetrySource:
    """Ticks `trains_per_route` simulated trains on every route and yields
    raw, noisy GPS fixes every `tick_seconds`.

    Train ids are numbered per line (CR-01, CR-02...) rather than per
    route, since commuters know a rake by its line, not by which branch
    it happens to be working.
    """

    def __init__(
        self,
        routes: Mapping[str, RailwayRoute],
        trains_per_route: int,
        tick_seconds: float,
        seed: int | None = None,
    ) -> None:
        self._tick_seconds = tick_seconds
        self._rng = random.Random(seed)
        self._states: dict[str, _TrainState] = {}

        now = time.time()
        numbered_per_line: dict[str, int] = {}
        for route in routes.values():
            line_code = route.seed.line.code
            for i in range(trains_per_route):
                number = numbered_per_line.get(line_code, 0) + 1
                numbered_per_line[line_code] = number
                train_id = f"{line_code}-{number:02d}"
                self._states[train_id] = self._spawn_mid_route(train_id, route, i % 2 == 0, now)

    def _spawn_mid_route(
        self, train_id: str, route: RailwayRoute, direction_forward: bool, now: float
    ) -> _TrainState:
        plan = build_run_plan(route, train_id, random_train_type(self._rng, route), direction_forward)
        # Stagger trains along the line so the network view is populated
        # immediately instead of everything starting at a terminus.
        fraction = self._rng.uniform(0.05, 0.9)
        start = plan.origin.chainage_m + fraction * (plan.destination.chainage_m - plan.origin.chainage_m)
        next_index = next(i for i, s in enumerate(plan.stops) if plan.is_ahead(s.station.chainage_m, start))
        # Backdate the run's start so a train spawned mid-route begins on
        # time rather than reading as fictitiously late or early.
        started_at = now - plan.scheduled_elapsed_s_at(start)
        return _TrainState(
            route=route,
            plan=plan,
            chainage_m=start,
            speed_kmh=plan.cruise_kmh,
            dwell_remaining_s=0.0,
            stop_index=next_index,
            last_halt_chainage_m=plan.stops[next_index - 1].station.chainage_m,
            run_started_at_epoch=started_at,
        )

    def get_active_run(self, train_id: str) -> ActiveRun | None:
        state = self._states.get(train_id)
        if state is None:
            return None
        return ActiveRun(plan=state.plan, started_at_epoch=state.run_started_at_epoch)

    async def stream(self) -> AsyncIterator[list[RawFix]]:
        while True:
            await asyncio.sleep(self._tick_seconds)
            now_epoch = time.time()
            fixes: list[RawFix] = []
            for train_id, state in self._states.items():
                self._tick_train(train_id, state, now_epoch)
                fix = self._maybe_emit_fix(train_id, state, now_epoch)
                if fix is not None:
                    fixes.append(fix)
            yield fixes

    def _tick_train(self, train_id: str, state: _TrainState, now: float) -> None:
        dt = self._tick_seconds
        if state.dwell_remaining_s > 0:
            state.speed_kmh = 0.0
            state.dwell_remaining_s = max(0.0, state.dwell_remaining_s - dt)
            return
        if state.terminated:
            self._form_return_working(train_id, state, now)
            return

        plan = state.plan
        target = plan.stops[state.stop_index]
        to_next = abs(target.station.chainage_m - state.chainage_m)
        since_last = abs(state.chainage_m - state.last_halt_chainage_m)
        cruise_m_s = plan.cruise_kmh / 3.6
        speed_m_s = profile_speed_m_s(since_last, to_next, cruise_m_s)
        speed_m_s = max(0.5, speed_m_s * (1 + self._rng.gauss(0.0, SPEED_NOISE_FRACTION)))
        state.speed_kmh = speed_m_s * 3.6

        step = speed_m_s * dt
        if step < to_next:
            state.chainage_m += step if plan.direction_forward else -step
            return

        state.chainage_m = target.station.chainage_m
        state.last_halt_chainage_m = target.station.chainage_m
        state.speed_kmh = 0.0
        if state.stop_index == len(plan.stops) - 1:
            state.terminated = True
            state.dwell_remaining_s = dt
        else:
            state.dwell_remaining_s = self._actual_dwell_s(target.dwell_s)
            state.stop_index += 1

    def _actual_dwell_s(self, planned_s: float) -> float:
        extra = max(-planned_s * 0.3, self._rng.gauss(DWELL_NOISE_MEAN_S, DWELL_NOISE_STDDEV_S))
        if self._rng.random() < LONG_DWELL_PROBABILITY:
            extra += self._rng.uniform(*LONG_DWELL_EXTRA_S)
        return planned_s + extra

    def _form_return_working(self, train_id: str, state: _TrainState, now: float) -> None:
        route = state.route
        plan = build_run_plan(route, train_id, random_train_type(self._rng, route), not state.plan.direction_forward)
        state.plan = plan
        state.chainage_m = plan.origin.chainage_m
        state.last_halt_chainage_m = plan.origin.chainage_m
        state.speed_kmh = 0.0
        state.stop_index = 1
        state.terminated = False
        state.dwell_remaining_s = LAYOVER_S
        # Timetabled departure is the end of the layover.
        state.run_started_at_epoch = now + LAYOVER_S

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
