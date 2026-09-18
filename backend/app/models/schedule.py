from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Schedule(Base):
    """Published timetable: one station-stop offset for a given line,
    direction, and train type template (not tied to a specific day's
    `TrainRun` - it's the reusable pattern a run is generated from).
    """

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("railway_lines.id"), index=True)
    train_type: Mapped[str] = mapped_column(String(8))
    direction_forward: Mapped[bool] = mapped_column(Boolean)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"))
    sequence: Mapped[int] = mapped_column(Integer)
    scheduled_offset_s: Mapped[float] = mapped_column(Float)
    dwell_s: Mapped[float] = mapped_column(Float, default=0.0)
