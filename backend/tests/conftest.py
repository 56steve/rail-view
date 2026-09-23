import time

import pytest

from app.services.position_processor import PositionProcessor
from app.services.simulator.schedule import TrainType, build_run_plan
from app.services.telemetry import ActiveRun, RawFix
from app.services.track_matching import get_all_routes, get_route


class StubSchedules:
    """ScheduleProvider backed by explicitly registered runs."""

    def __init__(self) -> None:
        self.runs: dict[str, ActiveRun] = {}

    def get_active_run(self, train_id: str) -> ActiveRun | None:
        return self.runs.get(train_id)


class Network:
    """A processor plus helpers to place trains at given timetable points."""

    def __init__(self) -> None:
        self.schedules = StubSchedules()
        self.processor = PositionProcessor(routes=get_all_routes(), schedule_provider=self.schedules)
        self.now = time.time()

    def place(
        self,
        train_id: str,
        route_code: str,
        train_type: TrainType,
        forward: bool,
        at_fraction: float,
        delay_s: float = 0.0,
    ) -> None:
        """Put a train `at_fraction` of the way along its run, `delay_s` late."""
        route = get_route(route_code)
        plan = build_run_plan(route, train_id, train_type, forward)
        start = plan.origin.chainage_m
        chainage = start + at_fraction * (plan.destination.chainage_m - start)
        started_at = self.now - plan.scheduled_elapsed_s_at(chainage) - delay_s
        self.schedules.runs[train_id] = ActiveRun(plan=plan, started_at_epoch=started_at)
        lat, lon = route.position_at_chainage(chainage)
        self.processor.process_batch([RawFix(train_id, lat, lon, self.now)])


@pytest.fixture
def network() -> Network:
    return Network()
