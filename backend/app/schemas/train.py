from typing import Literal

from pydantic import BaseModel

from app.schemas.station import StationOut

TrainStatus = Literal["live", "stale"]
TrainType = Literal["FAST", "SLOW"]
StopState = Literal["departed", "at_platform", "next", "upcoming"]


class TrainPositionUpdate(BaseModel):
    """The fully-enriched, track-matched, schedule-aware position of one
    train - what goes out over the WebSocket and what the 3D client
    renders. Never a raw GPS fix.
    """

    train_id: str
    train_type: TrainType
    line_code: str
    line_name: str
    route_code: str
    coach_count: int

    origin: StationOut
    destination: StationOut
    current_station: StationOut | None
    next_station: StationOut | None

    direction_forward: bool
    direction_label: str  # e.g. "Churchgate → Borivali"

    lat: float
    lon: float
    heading_deg: float
    chainage_m: float

    speed_kmh: float
    delay_seconds: float
    # Timetable-based ETAs adjusted by current delay (not distance/speed,
    # which swings wildly when a train is crawling or dwelling).
    eta_seconds: float | None
    destination_eta_seconds: float

    status: TrainStatus
    last_updated_epoch: float
    last_updated_iso: str


class StopTime(BaseModel):
    station: StationOut
    state: StopState
    scheduled_epoch: float
    # Estimated time at this stop given current delay (upcoming stops), or
    # the observed arrival time (stops this train was seen at).
    expected_epoch: float
    # None for stops the train passed before this server started tracking it.
    observed_arrival_epoch: float | None


class TrainDetail(BaseModel):
    position: TrainPositionUpdate
    stops: list[StopTime]
