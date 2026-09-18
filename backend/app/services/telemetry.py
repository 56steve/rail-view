"""Adapter boundary between "wherever position data comes from" and the
rest of the pipeline (track matching, ETA, WebSocket broadcast).

`TelemetrySource` is the seam described in the product spec: swap
`SimulatedTelemetrySource` (see `app.services.simulator.engine`) for a
`LiveRailwayApiSource` later, and nothing downstream of `PositionProcessor`
needs to change, because both speak the same `RawFix` / `ScheduleProvider`
contract.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from app.services.simulator.schedule import TrainRunPlan


@dataclass(frozen=True, slots=True)
class RawFix:
    """One unprocessed GPS reading for one train, exactly as a telemetry
    provider would hand it over - no track-matching or smoothing applied
    yet.
    """

    train_id: str
    lat: float
    lon: float
    timestamp_s: float  # unix epoch seconds


class TelemetrySource(Protocol):
    """A source of raw GPS fixes, batched per tick.

    A live implementation would poll/subscribe to an authorized railway
    API and normalize its payloads into `RawFix` batches; the rest of the
    system does not know or care which implementation is in use.
    """

    def stream(self) -> AsyncIterator[list[RawFix]]: ...


@dataclass(frozen=True, slots=True)
class ActiveRun:
    """A `TrainRunPlan` (the timetable) plus when that specific run
    actually started, so delay can be computed as
    (now - started_at_epoch) vs. the plan's scheduled elapsed time.
    """

    plan: TrainRunPlan
    started_at_epoch: float


class ScheduleProvider(Protocol):
    """Resolves which scheduled run a train_id belongs to, so the position
    processor can compute delay/ETA against a timetable.

    In production this would query the `train_runs` / `schedules` tables
    (joined on the run currently in progress); the simulator satisfies it
    from its own in-memory run state.
    """

    def get_active_run(self, train_id: str) -> ActiveRun | None: ...
