from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Train(Base):
    """A physical rake/unit, identified by the same `identifier` the
    telemetry pipeline uses as `train_id` (e.g. "CR-01").
    """

    __tablename__ = "trains"

    id: Mapped[int] = mapped_column(primary_key=True)
    identifier: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    train_type: Mapped[str] = mapped_column(String(8))  # FAST | SLOW
    rake_length: Mapped[int] = mapped_column(Integer, default=12)


class TrainRun(Base):
    """One scheduled working of a train along a line/direction - the
    persisted counterpart of `app.services.simulator.schedule.TrainRunPlan`.
    """

    __tablename__ = "train_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    train_id: Mapped[int] = mapped_column(ForeignKey("trains.id"), index=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("railway_lines.id"))
    direction_forward: Mapped[bool] = mapped_column(Boolean)
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="scheduled")


class TrainPosition(Base):
    """Periodic persisted position samples for history/analytics/replay.

    NOT the real-time hot path - live positions travel in-memory from the
    position processor straight to the WebSocket hub (see
    `app/services/websocket_manager.py`) to avoid a DB round trip on every
    tick for every train. This table exists for trip history, delay
    analytics, and seeding future ETA models.
    """

    __tablename__ = "train_positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    train_run_id: Mapped[int] = mapped_column(ForeignKey("train_runs.id"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    chainage_m: Mapped[float] = mapped_column(Float)
    speed_kmh: Mapped[float] = mapped_column(Float)
    geom: Mapped[str] = mapped_column(Geometry(geometry_type="POINT", srid=4326))
