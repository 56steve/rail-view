"""Fan-out hub for the `/ws/live` endpoint.

One backend broadcast reaches every connected client; individual clients
never poll the telemetry source or the database directly, which is what
keeps the system from doing O(clients) work against upstream data on
every tick.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket

from app.schemas.websocket import SnapshotMessage

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, message: SnapshotMessage) -> None:
        payload = message.model_dump_json()
        async with self._lock:
            targets = list(self._connections)

        dead: list[WebSocket] = []
        for connection in targets:
            try:
                await connection.send_text(payload)
            except Exception:  # noqa: BLE001 - a dead socket must not break broadcast for everyone else
                dead.append(connection)

        if dead:
            async with self._lock:
                for connection in dead:
                    self._connections.discard(connection)

    @property
    def active_connection_count(self) -> int:
        return len(self._connections)
