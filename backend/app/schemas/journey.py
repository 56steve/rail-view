from typing import Literal

from pydantic import BaseModel

from app.schemas.station import StationIndexEntry
from app.schemas.train import PlatformOut, TrainType

JourneySort = Literal["fastest", "soonest"]


class JourneyOption(BaseModel):
    train_id: str
    train_type: TrainType
    service_code: str | None
    ac: bool
    line_code: str
    line_name: str
    route_code: str
    direction_label: str
    # Running now, so the times include its current delay; otherwise the
    # train hasn't started yet and the times are the timetable's.
    is_live: bool
    board_scheduled_epoch: float
    board_expected_epoch: float
    alight_expected_epoch: float
    duration_seconds: float
    delay_seconds: float
    intermediate_stops: int
    board_platform: PlatformOut | None = None
    alight_platform: PlatformOut | None = None


class JourneyPlan(BaseModel):
    from_station: StationIndexEntry
    to_station: StationIndexEntry
    sort: JourneySort
    options: list[JourneyOption]
    # Set when no single line serves both stations directly.
    interchange_hint: str | None
