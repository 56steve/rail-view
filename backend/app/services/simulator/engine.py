"""Simulated telemetry source: stands in for a live railway GPS feed.

This is the ONLY module that "cheats" by knowing a train's true position.
Everything downstream (`PositionProcessor`) only ever sees the noisy
`RawFix` batches this module emits via `stream()`, and re-derives
position/speed/direction the same way it would from a real vendor feed.
That is what lets `LiveRailwayApiSource` replace this module later without
touching anything else.

Physics model (deliberately simple, not a full train-dynamics sim):
  - trapezoidal speed profile: accelerate away from a stop, cruise, brake
    into the next stop, dwell, repeat.
  - small gaussian speed noise every tick, which is what makes a train
    organically drift ahead of / behind its timetable (see
    `schedule.TrainRunPlan.scheduled_elapsed_s_at`), instead of "delay"
    being a fabricated random number.
  - each raw GPS fix gets gaussian positional jitter plus an occasional
    dropped fix, simulating consumer-grade GPS noise and signal gaps.
  - on reaching its destination, a train dwells (layover) then a new
    `TrainRunPlan` is generated in the reverse direction under the same
    train_id - the same rake forming the return working.
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.services.simulator.schedule import TrainRunPlan, build_run_plan, random_train_type
from app.services.telemetry import ActiveRun, RawFix
from app.services.track_matching import RailwayRoute

ACCEL_DISTANCE_M = 250.0
BRAKE_DISTANCE_M = 300.0
LAYOVER_S = 90.0
GPS_JITTER_STDDEV_M = 6.0
GPS_DROPOUT_PROBABILITY = 0.04
SPEED_NOISE_STDDEV_KMH = 3.5


@dataclass(slots=True)
class _TrainState:
    plan: TrainRunPlan
    chainage_m: float
    speed_kmh: float
    dwell_remaining_s: float
    stop_index: int  # index into plan.stops of the next stop to reach
    run_started_at_epoch: float


class SimulatedTelemetrySource:
    """Ticks `train_count` simulated trains on `route` and yields raw,
    noisy GPS fixes every `tick_seconds`.
    """

    def __init__(
        self,
        route: RailwayRoute,
        train_count: int,
        tick_seconds: float,
        seed: int | None = None,
    ) -> None:
        self._route = route
        self._tick_seconds = tick_seconds
        self._rng = random.Random(seed)
        self._states: dict[str, _TrainState] = {}
        self._plans: dict[str, TrainRunPlan] = {}

        for i in range(train_count):
            train_id = f"CR-{i + 1:02d}"
            direction_forward = i % 2 == 0
            plan = build_run_plan(
                route, train_id, random_train_type(self._rng), direction_forward
            )
            # Stagger initial trains along the route so the network view
            # is populated immediately instead of everything starting at
            # Thane simultaneously.
            fraction = self._rng.uniform(0.0, 0.9)
            start_chainage = fraction * route.length_m
            if not direction_forward:
                start_chainage = route.length_m - start_chainage
            # Backdate the run's start so a train spawned mid-route doesn't
            # read as instantly, fictitiously, running late.
            started_at_epoch = time.time() - plan.scheduled_elapsed_s_at(start_chainage)
            state = _TrainState(
                plan=plan,
                chainage_m=start_chainage,
                speed_kmh=plan.cruise_kmh,
                dwell_remaining_s=0.0,
                stop_index=self._first_pending_stop_index(plan, start_chainage),
                run_started_at_epoch=started_at_epoch,
            )
            self._states[train_id] = state
            self._plans[train_id] = plan

    def get_active_run(self, train_id: str) -> ActiveRun | None:
        state = self._states.get(train_id)
        if state is None:
            return None
        return ActiveRun(plan=state.plan, started_at_epoch=state.run_started_at_epoch)

    @staticmethod
    def _first_pending_stop_index(plan: TrainRunPlan, chainage_m: float) -> int:
        for i, stop in enumerate(plan.stops):
            reached = (
                stop.station.chainage_m > chainage_m + 1.0
                if plan.direction_forward
                else stop.station.chainage_m < chainage_m - 1.0
            )
            if reached:
                return i
        return len(plan.stops) - 1

    async def stream(self) -> AsyncIterator[list[RawFix]]:
        while True:
            await asyncio.sleep(self._tick_seconds)
            now_epoch = time.time()
            fixes: list[RawFix] = []
            for train_id, state in list(self._states.items()):
                self._tick_train(train_id, state)
                fix = self._maybe_emit_fix(train_id, state, now_epoch)
                if fix is not None:
                    fixes.append(fix)
            yield fixes

    def _tick_train(self, train_id: str, state: _TrainState) -> None:
        dt = self._tick_seconds
        plan = state.plan
        direction_sign = 1.0 if plan.direction_forward else -1.0

        if state.dwell_remaining_s > 0:
            state.speed_kmh = 0.0
            state.dwell_remaining_s = max(0.0, state.dwell_remaining_s - dt)
            if state.dwell_remaining_s == 0 and state.stop_index >= len(plan.stops) - 1:
                self._respawn(train_id, state)
            return

        target_stop = plan.stops[state.stop_index]
        distance_to_stop = abs(target_stop.station.chainage_m - state.chainage_m)

        target_speed_kmh = plan.cruise_kmh
        if distance_to_stop < BRAKE_DISTANCE_M:
            target_speed_kmh = plan.cruise_kmh * max(0.08, distance_to_stop / BRAKE_DISTANCE_M)
        distance_from_origin = abs(state.chainage_m - plan.origin.chainage_m)
        if distance_from_origin < ACCEL_DISTANCE_M:
            accel_cap = plan.cruise_kmh * max(0.15, distance_from_origin / ACCEL_DISTANCE_M)
            target_speed_kmh = min(target_speed_kmh, accel_cap)

        noise = self._rng.gauss(0.0, SPEED_NOISE_STDDEV_KMH)
        state.speed_kmh = max(0.0, target_speed_kmh + noise)

        speed_m_s = state.speed_kmh * 1000 / 3600
        new_chainage = state.chainage_m + direction_sign * speed_m_s * dt

        overshoot = (
            new_chainage >= target_stop.station.chainage_m
            if plan.direction_forward
            else new_chainage <= target_stop.station.chainage_m
        )
        if overshoot:
            state.chainage_m = target_stop.station.chainage_m
            state.speed_kmh = 0.0
            state.dwell_remaining_s = max(target_stop.dwell_s, dt)
            if state.stop_index < len(plan.stops) - 1:
                state.stop_index += 1
        else:
            state.chainage_m = new_chainage

    def _respawn(self, train_id: str, state: _TrainState) -> None:
        reversed_direction = not state.plan.direction_forward
        new_plan = build_run_plan(
            self._route, train_id, random_train_type(self._rng), reversed_direction
        )
        self._plans[train_id] = new_plan
        state.plan = new_plan
        state.chainage_m = new_plan.origin.chainage_m
        state.speed_kmh = 0.0
        state.dwell_remaining_s = LAYOVER_S
        state.stop_index = 1 if len(new_plan.stops) > 1 else 0
        state.run_started_at_epoch = time.time() + LAYOVER_S

    def _maybe_emit_fix(self, train_id: str, state: _TrainState, now_s: float) -> RawFix | None:
        # A dwelling train still emits fixes (stationary but live), so it
        # doesn't visually disappear from the client while stopped.
        if self._rng.random() < GPS_DROPOUT_PROBABILITY:
            return None

        true_lat, true_lon = self._route.position_at_chainage(state.chainage_m)
        jittered_lat, jittered_lon = _jitter_latlon(true_lat, true_lon, GPS_JITTER_STDDEV_M, self._rng)
        return RawFix(train_id=train_id, lat=jittered_lat, lon=jittered_lon, timestamp_s=now_s)


def _jitter_latlon(lat: float, lon: float, stddev_m: float, rng: random.Random) -> tuple[float, float]:
    dx_m = rng.gauss(0.0, stddev_m)
    dy_m = rng.gauss(0.0, stddev_m)
    meters_per_deg_lat = 111_320.0
    meters_per_deg_lon = 111_320.0 * math.cos(math.radians(lat))
    return lat + dy_m / meters_per_deg_lat, lon + dx_m / max(meters_per_deg_lon, 1.0)
