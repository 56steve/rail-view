"""Seed the database with the network's static geometry: stations, lines,
their tracks, station-on-route ordering, per-segment track geometry, and
a generated schedule per line, train type and direction.

The live pipeline does NOT need this (it runs from
`app/data/generated/network.json` in memory). This populates the
PostGIS-backed schema for anything that queries the database directly -
an admin UI, analytics, or a future live-data adapter that resolves
schedules from `schedules`/`train_runs` instead of in-memory plans.

Usage (after `alembic upgrade head` against a running Postgres/PostGIS):

    uv run python scripts/seed_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from geoalchemy2.shape import from_shape
from shapely.geometry import LineString, Point
from shapely.ops import substring
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import get_session_factory  # noqa: E402
from app.models import (  # noqa: E402
    RailwayLine,
    RailwayTrack,
    Schedule,
    Station,
    StationOnRoute,
    TrackSegment,
)
from app.services.geometry import LocalPoint, to_latlon, to_local  # noqa: E402
from app.services.simulator.schedule import build_run_plan  # noqa: E402
from app.services.track_matching import get_all_routes  # noqa: E402


def local_line_to_lonlat(line: LineString) -> LineString:
    coords = []
    for x, y in line.coords:
        lat, lon = to_latlon(LocalPoint(x, y))
        coords.append((lon, lat))
    return LineString(coords)


def seed(session: Session) -> None:
    stations_by_code: dict[str, Station] = {}
    lines_by_code: dict[str, RailwayLine] = {}

    for route in get_all_routes().values():
        seed_route = route.seed
        line = seed_route.line
        db_line = lines_by_code.get(line.code)
        if db_line is None:
            db_line = RailwayLine(code=line.code, name=line.name, color_hex=line.color_hex)
            session.add(db_line)
            lines_by_code[line.code] = db_line

        for sc in route.stations:
            if sc.station.code not in stations_by_code:
                station = Station(
                    code=sc.station.code,
                    name=sc.station.name,
                    geom=from_shape(Point(sc.station.lon, sc.station.lat), srid=4326),
                )
                session.add(station)
                stations_by_code[sc.station.code] = station
        session.flush()

        local_track = LineString([(p.x, p.y) for p in (to_local(lat, lon) for lat, lon in seed_route.track)])
        db_track = RailwayTrack(
            code=seed_route.code,
            line_id=db_line.id,
            name=f"{line.name} line ({seed_route.name})",
            geom=from_shape(LineString([(lon, lat) for lat, lon in seed_route.track]), srid=4326),
            length_m=route.length_m,
        )
        session.add(db_track)
        session.flush()

        for i, sc in enumerate(route.stations):
            session.add(
                StationOnRoute(
                    track_id=db_track.id,
                    station_id=stations_by_code[sc.station.code].id,
                    sequence=i,
                    chainage_m=sc.chainage_m,
                )
            )
            if i == 0:
                continue
            prev = route.stations[i - 1]
            segment = substring(local_track, prev.chainage_m, sc.chainage_m)
            session.add(
                TrackSegment(
                    track_id=db_track.id,
                    from_station_id=stations_by_code[prev.station.code].id,
                    to_station_id=stations_by_code[sc.station.code].id,
                    sequence=i,
                    geom=from_shape(local_line_to_lonlat(segment), srid=4326),
                    length_m=sc.chainage_m - prev.chainage_m,
                )
            )

        train_types = ("FAST", "SLOW") if seed_route.has_fast_service else ("SLOW",)
        for train_type in train_types:
            for direction_forward in (True, False):
                plan = build_run_plan(route, "seed-template", train_type, direction_forward)
                for i, stop in enumerate(plan.stops):
                    session.add(
                        Schedule(
                            line_id=db_line.id,
                            track_id=db_track.id,
                            train_type=train_type,
                            direction_forward=direction_forward,
                            station_id=stations_by_code[stop.station.station.code].id,
                            sequence=i,
                            scheduled_offset_s=stop.scheduled_arrival_s,
                            dwell_s=stop.dwell_s,
                        )
                    )

    session.commit()


def main() -> None:
    session = get_session_factory()()
    try:
        seed(session)
        print("Seed complete.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
