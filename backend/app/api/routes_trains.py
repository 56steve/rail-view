from fastapi import APIRouter, Request

from app.schemas.train import TrainPositionUpdate

router = APIRouter(prefix="/api/trains", tags=["trains"])


@router.get("", response_model=list[TrainPositionUpdate])
def list_trains(request: Request) -> list[TrainPositionUpdate]:
    """REST fallback snapshot for a client's first paint before its
    WebSocket connects. The live-updating path is `/ws/live`.
    """
    return request.app.state.live_cache.snapshot()
