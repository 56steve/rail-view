from geoalchemy2 import Geometry
from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RailwayLine(Base):
    """A suburban line: Central, Western, Harbour, Trans-Harbour."""

    __tablename__ = "railway_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    color_hex: Mapped[str] = mapped_column(String(7))


class RailwayTrack(Base):
    """One end-to-end route belonging to a line (e.g. the Central line's
    CSMT<->Kasara route). A line may have several - Central forks at Kalyan
    into Kasara and Karjat routes that share the trunk.
    """

    __tablename__ = "railway_tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("railway_lines.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    geom: Mapped[str] = mapped_column(Geometry(geometry_type="LINESTRING", srid=4326))
    length_m: Mapped[float] = mapped_column(Float)


class TrackSegment(Base):
    """A track broken into station-to-station segments - the unit that GPS
    matching snaps a raw fix onto, and that a persisted `TrainPosition`
    references.
    """

    __tablename__ = "track_segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("railway_tracks.id"), index=True)
    from_station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"))
    to_station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"))
    sequence: Mapped[int] = mapped_column(Integer)
    geom: Mapped[str] = mapped_column(Geometry(geometry_type="LINESTRING", srid=4326))
    length_m: Mapped[float] = mapped_column(Float)


class StationOnRoute(Base):
    """Ordered membership of stations on a track, so a track's full stop
    sequence can be queried without re-deriving it from segment geometry.
    """

    __tablename__ = "stations_on_routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("railway_tracks.id"), index=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    chainage_m: Mapped[float] = mapped_column(Float)
