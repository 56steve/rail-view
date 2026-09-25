import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.live_wire import Snapshot, WireFormat

logger = logging.getLogger(__name__)
router = APIRouter()


def wire_format(websocket: WebSocket) -> WireFormat:
    """The format a client asked for: `?v=2` for the lean table (full
    snapshots now and then, moving parts between), plus
    `&encoding=deflate` to have it compressed. Anything else is an app
    from before these, which gets the original table."""
    params = websocket.query_params
    if params.get("v") != "2":
        return "legacy"
    return "deflate" if params.get("encoding") == "deflate" else "table"


@router.websocket("/ws/live")
async def websocket_live(websocket: WebSocket) -> None:
    manager = websocket.app.state.connection_manager
    cache = websocket.app.state.live_cache

    initial = Snapshot(time.time(), cache.snapshot(), full=True)
    await manager.connect(websocket, initial, wire_format(websocket))
    try:
        while True:
            # Clients don't need to send anything; this blocks until they
            # disconnect, which is how we notice and clean up.
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.debug("client disconnected from /ws/live")
    finally:
        await manager.disconnect(websocket)
