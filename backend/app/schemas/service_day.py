from datetime import date

from pydantic import BaseModel


class ServiceDayOut(BaseModel):
    """Which timetable the network is running today, in Mumbai."""

    date: date
    sunday_schedule: bool
    # Set when today runs the Sunday schedule because it's a holiday
    # rather than a Sunday.
    holiday_name: str | None
