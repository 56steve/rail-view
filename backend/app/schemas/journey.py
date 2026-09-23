from typing import Literal

from pydantic import BaseModel

from app.schemas.station import StationIndexEntry
from app.schemas.train import TrainType

JourneySort = Literal["fastest", "soonest"]


class JourneyOption(BaseModel):
    train_id: str
    train_type: TrainType
    line_code: str
    line_name: str
    route_code: str
    direction_label: str
    board_expected_epoch: float
    alight_expected_epoch: float
    duration_seconds: float
    delay_seconds: float
    intermediate_stops: int


class JourneyPlan(BaseModel):
    from_station: StationIndexEntry
    to_station: StationIndexEntry
    sort: JourneySort
    options: list[JourneyOption]
    # Set when no single line serves both stations directly.
    interchange_hint: str | None
