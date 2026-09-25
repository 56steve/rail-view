from typing import Literal

from pydantic import BaseModel

from app.schemas.station import StationOut, StationRef

TrainStatus = Literal["live", "stale"]
TrainType = Literal["FAST", "SLOW"]
StopState = Literal["departed", "at_platform", "next", "upcoming"]
DoorSide = Literal["left", "right", "both"]


class PlatformOut(BaseModel):
    numbers: list[str]
    # Side of the train the platform is on, facing the way it travels.
    door: DoorSide | None
    # False: it varies from train to train here, so show "usually".
    certain: bool


class TrainPositionUpdate(BaseModel):
    """The fully-enriched, track-matched, schedule-aware position of one
    train - what goes out over the WebSocket and what the 3D client
    renders. Never a raw GPS fix.
    """

    train_id: str  # the train number in the official timetable
    train_type: TrainType
    # Central Railway's service code (e.g. "N 5" - the 5th Kasara local);
    # Western Railway doesn't publish them.
    service_code: str | None
    ac: bool
    line_code: str
    line_name: str
    route_code: str
    coach_count: int

    origin: StationRef
    destination: StationRef
    current_station: StationRef | None
    next_station: StationRef | None

    # The next stop's platform numbers, comma-separated ("3", "5,6,7").
    next_platform: str | None = None
    next_platform_certain: bool = False
    next_platform_door: DoorSide | None = None

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


class StopTime(BaseModel):
    station: StationOut
    state: StopState
    # The time in the published timetable: departure, or arrival at the
    # last stop.
    scheduled_epoch: float
    # Estimated time at this stop given current delay (upcoming stops), or
    # the observed arrival time (stops this train was seen at).
    expected_epoch: float
    # None for stops the train passed before this server started tracking it.
    observed_arrival_epoch: float | None
    platform: PlatformOut | None = None


class TrainDetail(BaseModel):
    position: TrainPositionUpdate
    stops: list[StopTime]
