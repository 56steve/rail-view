from typing import Literal

from pydantic import BaseModel

from app.schemas.train import TrainPositionUpdate


class SnapshotMessage(BaseModel):
    """One broadcast tick: every currently-known train, live or stale.

    Clients replace their whole train set with this snapshot and
    interpolate motion between successive snapshots client-side - see
    `frontend/lib/useLiveTrains.ts`.
    """

    type: Literal["snapshot"] = "snapshot"
    server_time_epoch: float
    trains: list[TrainPositionUpdate]
