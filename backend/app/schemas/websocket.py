from typing import Literal

from pydantic import BaseModel

# One value in a snapshot row. Every TrainPositionUpdate field is one of
# these once its station references are reduced to station codes.
Cell = str | int | float | bool | None


class SnapshotTableMessage(BaseModel):
    """One broadcast tick: every currently-known train, live or stale, as
    a table.

    It goes to every client every second, so it's laid out to be small:
    `fields` names the columns once, each row in `trains` holds one
    TrainPositionUpdate's values in that order, and station fields hold
    a station code whose name is in `stations`. Clients rebuild the
    positions (`frontend/lib/liveWire.ts`), replace their train set with
    them and interpolate motion between successive snapshots.
    """

    type: Literal["snapshot.table"] = "snapshot.table"
    server_time_epoch: float
    fields: list[str]
    stations: dict[str, str]
    trains: list[list[Cell]]
