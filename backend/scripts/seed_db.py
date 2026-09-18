"""Seed the database with the Central Line's Thane<->Dadar static geometry:
stations, the line, its track, station-on-route ordering, per-segment
geometry, and a generated schedule per train type/direction.

The simulator does NOT need this to run (it uses the in-memory
`app.data.mumbai_network` seed data directly) - this script populates the
real PostGIS-backed schema described in the product spec, for anything
that queries the database directly (an admin UI, analytics, or a future
live-data adapter that resolves schedules from `schedules`/`train_runs`
instead of in-memory plans).

Usage (after `alembic upgrade head` against a running Postgres/PostGIS):

    uv run python scripts/seed_db.py
"""

from __future__ import annotations

from geoalchemy2.shape import from_shape
from shapely.geometry import LineString, Point
from sqlalchemy.orm import Session

from app.data.mumbai_network import RAILWAY_LINES
from app.db.session import get_session_factory
from app.models import RailwayLine, RailwayTrack, Schedule, Station, StationOnRoute, TrackSegment
from app.services.simulator.schedule import build_run_plan
from app.services.track_matching import get_route


def seed(session: Session) -> None:
    for line_code, line_seed in RAILWAY_LINES.items():
        route = get_route(line_code)

        db_line = RailwayLine(code=line_seed.code, name=line_seed.name, color_hex=line_seed.color_hex)
        session.add(db_line)
        session.flush()

        db_stations: dict[str, Station] = {}
        for sc in route.stations:
            station = Station(
                code=sc.station.code,
                name=sc.station.name,
                geom=from_shape(Point(sc.station.lon, sc.station.lat), srid=4326),
            )
            session.add(station)
            db_stations[sc.station.code] = station
        session.flush()

        origin_name = route.stations[0].station.name
        destination_name = route.stations[-1].station.name
        track_line = LineString([(sc.station.lon, sc.station.lat) for sc in route.stations])
        db_track = RailwayTrack(
            line_id=db_line.id,
            name=f"{line_seed.name} mainline ({origin_name} - {destination_name})",
            geom=from_shape(track_line, srid=4326),
            length_m=route.length_m,
        )
        session.add(db_track)
        session.flush()

        for i, sc in enumerate(route.stations):
            session.add(
                StationOnRoute(
                    track_id=db_track.id,
                    station_id=db_stations[sc.station.code].id,
                    sequence=i,
                    chainage_m=sc.chainage_m,
                )
            )
            if i > 0:
                prev = route.stations[i - 1]
                segment_line = LineString(
                    [(prev.station.lon, prev.station.lat), (sc.station.lon, sc.station.lat)]
                )
                session.add(
                    TrackSegment(
                        track_id=db_track.id,
                        from_station_id=db_stations[prev.station.code].id,
                        to_station_id=db_stations[sc.station.code].id,
                        sequence=i,
                        geom=from_shape(segment_line, srid=4326),
                        length_m=sc.chainage_m - prev.chainage_m,
                    )
                )

        for train_type in ("FAST", "SLOW"):
            for direction_forward in (True, False):
                plan = build_run_plan(route, "seed-template", train_type, direction_forward)
                for i, stop in enumerate(plan.stops):
                    session.add(
                        Schedule(
                            line_id=db_line.id,
                            train_type=train_type,
                            direction_forward=direction_forward,
                            station_id=db_stations[stop.station.station.code].id,
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
