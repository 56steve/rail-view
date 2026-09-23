"""Commuter-facing station index, merged across lines and routes by name.

Commuters think of "Dadar" or "Kurla" as one station even where each line
has its own platforms and station code (Dadar is DR on Central and DDR on
Western). Journey planning and search work in these merged identities;
the per-line codes stay internal to routes and schedules.
"""

import re
from functools import lru_cache

from app.data.mumbai_network import load_routes
from app.schemas.station import StationIndexEntry


def station_id_for_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@lru_cache
def station_index() -> dict[str, StationIndexEntry]:
    grouped: dict[str, list[tuple[str, float, float]]] = {}
    names: dict[str, str] = {}
    seen: set[tuple[str, str]] = set()
    for route in load_routes().values():
        line_code = route.line.code
        for station in route.stations:
            station_id = station_id_for_name(station.name)
            # Branch routes share their trunk stations (Kasara and Karjat
            # routes both call at Thane); count each line's platform once.
            if (station_id, line_code) in seen:
                continue
            seen.add((station_id, line_code))
            names[station_id] = station.name
            grouped.setdefault(station_id, []).append((line_code, station.lat, station.lon))

    index: dict[str, StationIndexEntry] = {}
    for station_id, entries in grouped.items():
        index[station_id] = StationIndexEntry(
            id=station_id,
            name=names[station_id],
            lat=sum(lat for _, lat, _ in entries) / len(entries),
            lon=sum(lon for _, _, lon in entries) / len(entries),
            lines=sorted({code for code, _, _ in entries}),
        )
    return index


@lru_cache
def route_station_ids() -> dict[str, frozenset[str]]:
    """Commuter-facing station ids each route calls at, by route code."""
    return {
        code: frozenset(station_id_for_name(station.name) for station in route.stations)
        for code, route in load_routes().items()
    }
