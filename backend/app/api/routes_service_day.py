import time
from datetime import datetime

from fastapi import APIRouter

from app.schemas.service_day import ServiceDayOut
from app.services.holidays import load_holidays, runs_sunday_schedule
from app.services.timetable import MUMBAI

router = APIRouter(prefix="/api", tags=["timetable"])


@router.get("/service-day", response_model=ServiceDayOut)
def get_service_day() -> ServiceDayOut:
    """Today's service day in Mumbai: whether the Sunday timetable is
    running, and for which holiday."""
    today = datetime.fromtimestamp(time.time(), tz=MUMBAI).date()
    holiday = load_holidays().holiday_on(today)
    return ServiceDayOut(
        date=today,
        sunday_schedule=runs_sunday_schedule(today),
        holiday_name=holiday.name if holiday is not None else None,
    )
