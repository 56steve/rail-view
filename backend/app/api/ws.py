import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.schemas.websocket import SnapshotMessage

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/live")
async def websocket_live(websocket: WebSocket) -> None:
    manager = websocket.app.state.connection_manager
    cache = websocket.app.state.live_cache

    await manager.connect(websocket)
    try:
        # Send an immediate snapshot so a just-connected client sees
        # trains right away instead of waiting for the next tick.
        initial = SnapshotMessage(server_time_epoch=time.time(), trains=cache.snapshot())
        await websocket.send_text(initial.model_dump_json())

        while True:
            # Clients don't need to send anything; this blocks until they
            # disconnect, which is how we notice and clean up.
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.debug("client disconnected from /ws/live")
    finally:
        await manager.disconnect(websocket)
