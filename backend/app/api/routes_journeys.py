import time

from fastapi import APIRouter, HTTPException, Query, Request

from app.schemas.journey import JourneyPlan, JourneySort
from app.services.journey_planner import UnknownStationError, plan_journey

router = APIRouter(prefix="/api/journeys", tags=["journeys"])


@router.get("", response_model=JourneyPlan)
def get_journey(
    request: Request,
    from_station: str = Query(alias="from", min_length=1, max_length=64),
    to_station: str = Query(alias="to", min_length=1, max_length=64),
    sort: JourneySort = "fastest",
) -> JourneyPlan:
    now = time.time()
    try:
        return plan_journey(
            from_station,
            to_station,
            sort,
            request.app.state.timetable,
            request.app.state.position_processor.contexts(),
            request.app.state.live_cache.live_train_ids(now),
            now,
        )
    except UnknownStationError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown station '{exc.args[0]}'") from exc
