"""Encodes the live snapshot for the WebSocket (see SnapshotTableMessage).

Every client gets the whole network every second, so the encoding is what
decides how much data a phone burns watching trains. As plain objects a
snapshot of ~180 trains is ~170 KB, mostly field names and station
records repeated per train. As a table with station names listed once
and positions rounded to what the map can show, it is ~33 KB.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from app.schemas.station import StationRef
from app.schemas.train import TrainPositionUpdate
from app.schemas.websocket import Cell

SNAPSHOT_FIELDS: tuple[str, ...] = tuple(TrainPositionUpdate.model_fields)

STATION_FIELDS = frozenset({"origin", "destination", "current_station", "next_station"})

# Decimal places kept on the wire: ~0.1 m for coordinates and chainage,
# which is finer than anything the map draws.
ROUNDING: dict[str, int] = {
    "lat": 6,
    "lon": 6,
    "heading_deg": 1,
    "chainage_m": 1,
    "speed_kmh": 1,
    "last_updated_epoch": 2,
}


def encode_snapshot(server_time_epoch: float, trains: Sequence[TrainPositionUpdate]) -> str:
    """The SnapshotTableMessage for `trains`, as JSON text."""
    stations: dict[str, str] = {}
    rows: list[list[Cell]] = []
    for train in trains:
        row: list[Cell] = []
        for name in SNAPSHOT_FIELDS:
            value = getattr(train, name)
            if name in STATION_FIELDS:
                row.append(_station_code(value, stations))
            elif name in ROUNDING:
                row.append(round(value, ROUNDING[name]))
            else:
                row.append(value)
        rows.append(row)
    message = {
        "type": "snapshot.table",
        "server_time_epoch": round(server_time_epoch, 3),
        "fields": SNAPSHOT_FIELDS,
        "stations": stations,
        "trains": rows,
    }
    return json.dumps(message, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _station_code(station: StationRef | None, names: dict[str, str]) -> str | None:
    if station is None:
        return None
    names[station.code] = station.name
    return station.code
