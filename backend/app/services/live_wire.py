"""Encodes the live snapshot for the WebSocket (see SnapshotTableMessage).

Every client receives the whole network every second, so the encoding
decides how much data a phone, and the host, spends watching trains:

- It's a table: field names once, station names once, positions rounded
  to what the map can show.
- A run's details that don't change (route, destination, coaches...) go
  out in a full snapshot on connect and every FULL_SNAPSHOT_EVERY_TICKS
  ticks; the ticks between carry only what moves.
- A train's lat/lon/heading stay off the wire: the app places trains by
  chainage along their track.
- Clients that ask for it get the table deflated, in binary frames. The
  host's edge (Cloudflare, in front of Render) strips WebSocket
  compression, so the app compresses it itself.

About 5.5 KB a second for ~200 trains, against 37 KB as a plain table.
Clients that connect without asking for this format (an app loaded before
it) get the original full table every tick.
"""

from __future__ import annotations

import json
import zlib
from collections.abc import Sequence
from typing import Literal

from app.schemas.station import StationRef
from app.schemas.train import TrainPositionUpdate
from app.schemas.websocket import Cell

WireFormat = Literal["legacy", "table", "deflate"]

FULL_SNAPSHOT_EVERY_TICKS = 10

SNAPSHOT_FIELDS: tuple[str, ...] = tuple(TrainPositionUpdate.model_fields)

STATION_FIELDS = frozenset({"origin", "destination", "current_station", "next_station"})

# Not read by the app, which places trains by chainage.
OFF_WIRE_FIELDS = frozenset({"lat", "lon", "heading_deg"})

# Fixed for a run: sent only in full snapshots.
RUN_FIELDS = frozenset(
    {
        "train_type",
        "service_code",
        "ac",
        "line_code",
        "line_name",
        "route_code",
        "coach_count",
        "origin",
        "destination",
        "direction_forward",
        "direction_label",
    }
)

FULL_FIELDS: tuple[str, ...] = tuple(name for name in SNAPSHOT_FIELDS if name not in OFF_WIRE_FIELDS)
MOVING_FIELDS: tuple[str, ...] = tuple(name for name in FULL_FIELDS if name not in RUN_FIELDS)

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


def encode_table(
    server_time_epoch: float, trains: Sequence[TrainPositionUpdate], fields: Sequence[str], *, full: bool
) -> str:
    """A SnapshotTableMessage holding `fields` of every train, as JSON text."""
    stations: dict[str, str] = {}
    rows: list[list[Cell]] = []
    for train in trains:
        row: list[Cell] = []
        for name in fields:
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
        "full": full,
        "fields": list(fields),
        "stations": stations,
        "trains": rows,
    }
    return json.dumps(message, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def encode_snapshot(server_time_epoch: float, trains: Sequence[TrainPositionUpdate]) -> str:
    """The original format: every field of every train."""
    return encode_table(server_time_epoch, trains, SNAPSHOT_FIELDS, full=True)


def deflate(text: str) -> bytes:
    """Raw deflate, which browsers inflate with DecompressionStream("deflate-raw")."""
    compressor = zlib.compressobj(level=6, wbits=-15)
    return compressor.compress(text.encode()) + compressor.flush()


class Snapshot:
    """One tick's trains, encoded for each wire format on first use and
    then shared by every client that wants that format."""

    def __init__(self, server_time_epoch: float, trains: Sequence[TrainPositionUpdate], *, full: bool) -> None:
        self._server_time_epoch = server_time_epoch
        self._trains = trains
        self._full = full
        self._legacy: str | None = None
        self._table: str | None = None
        self._deflated: bytes | None = None

    def payload(self, wire: WireFormat) -> str | bytes:
        if wire == "legacy":
            if self._legacy is None:
                self._legacy = encode_snapshot(self._server_time_epoch, self._trains)
            return self._legacy
        if wire == "deflate":
            if self._deflated is None:
                self._deflated = deflate(self._table_text())
            return self._deflated
        return self._table_text()

    def _table_text(self) -> str:
        if self._table is None:
            fields = FULL_FIELDS if self._full else MOVING_FIELDS
            self._table = encode_table(self._server_time_epoch, self._trains, fields, full=self._full)
        return self._table


def _station_code(station: StationRef | None, names: dict[str, str]) -> str | None:
    if station is None:
        return None
    names[station.code] = station.name
    return station.code
