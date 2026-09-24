import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.live_wire import encode_snapshot

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/live")
async def websocket_live(websocket: WebSocket) -> None:
    manager = websocket.app.state.connection_manager
    cache = websocket.app.state.live_cache

    await manager.connect(websocket, encode_snapshot(time.time(), cache.snapshot()))
    try:
        while True:
            # Clients don't need to send anything; this blocks until they
            # disconnect, which is how we notice and clean up.
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.debug("client disconnected from /ws/live")
    finally:
        await manager.disconnect(websocket)
