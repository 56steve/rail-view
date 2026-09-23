from fastapi import APIRouter, HTTPException, Request

from app.schemas.train import TrainDetail, TrainPositionUpdate
from app.services.timeline import build_timeline

router = APIRouter(prefix="/api/trains", tags=["trains"])


@router.get("", response_model=list[TrainPositionUpdate])
def list_trains(request: Request) -> list[TrainPositionUpdate]:
    """REST fallback snapshot for a client's first paint before its
    WebSocket connects. The live-updating path is `/ws/live`.
    """
    return request.app.state.live_cache.snapshot()


@router.get("/{train_id}", response_model=TrainDetail)
def get_train(train_id: str, request: Request) -> TrainDetail:
    position = request.app.state.live_cache.get(train_id)
    context = request.app.state.position_processor.context(train_id)
    if position is None or context is None:
        raise HTTPException(status_code=404, detail=f"Unknown train_id '{train_id}'")
    return TrainDetail(position=position, stops=build_timeline(context))
