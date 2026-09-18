from geoalchemy2 import Geometry
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Station(Base):
    """A physical railway station, shared across any lines that call at it
    (e.g. Dadar serves both Central and Western lines).
    """

    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    geom: Mapped[str] = mapped_column(Geometry(geometry_type="POINT", srid=4326))
