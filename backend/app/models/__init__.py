"""Import every model so `Base.metadata` is fully populated for Alembic
autogenerate and `Base.metadata.create_all`.
"""

from app.models.railway import RailwayLine, RailwayTrack, StationOnRoute, TrackSegment
from app.models.schedule import Schedule
from app.models.station import Station
from app.models.train import Train, TrainPosition, TrainRun

__all__ = [
    "RailwayLine",
    "RailwayTrack",
    "StationOnRoute",
    "TrackSegment",
    "Schedule",
    "Station",
    "Train",
    "TrainPosition",
    "TrainRun",
]
