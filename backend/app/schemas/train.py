from typing import Literal

from pydantic import BaseModel

from app.schemas.station import StationOut

TrainStatus = Literal["live", "stale"]


class TrainPositionUpdate(BaseModel):
    """The fully-enriched, track-matched, schedule-aware position of one
    train - what actually goes out over the WebSocket and what the 3D
    client renders. Never a raw GPS fix.
    """

    train_id: str
    train_type: Literal["FAST", "SLOW"]
    line_code: str
    line_name: str

    origin: StationOut
    destination: StationOut
    current_station: StationOut | None
    next_station: StationOut | None

    direction_forward: bool
    direction_label: str  # e.g. "Thane -> Dadar"

    lat: float
    lon: float
    heading_deg: float
    chainage_m: float

    speed_kmh: float
    delay_seconds: float
    eta_seconds: float | None

    status: TrainStatus
    last_updated_epoch: float
    last_updated_iso: str
