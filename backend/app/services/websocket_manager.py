"""Fan-out hub for the `/ws/live` endpoint.

One backend broadcast reaches every connected client; individual clients
never poll the telemetry source or the database directly, which is what
keeps the system from doing O(clients) work against upstream data on
every tick.

Each client has its own sender task holding only the newest snapshot. A
client on a slow connection skips the snapshots it couldn't take in time
instead of delaying everyone else's, and it never builds up a backlog:
positions only matter while they're current.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class _Client:
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.latest: str | None = None
        self.ready = asyncio.Event()
        self.sender: asyncio.Task[None] | None = None

    def offer(self, payload: str) -> None:
        """Make `payload` the next thing sent, replacing any unsent one."""
        self.latest = payload
        self.ready.set()

    async def send_forever(self) -> None:
        while True:
            await self.ready.wait()
            self.ready.clear()
            payload, self.latest = self.latest, None
            if payload is not None:
                await self.websocket.send_text(payload)


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: dict[WebSocket, _Client] = {}

    async def connect(self, websocket: WebSocket, initial_payload: str) -> None:
        """Accept `websocket` and send it `initial_payload` straight away,
        so a new client sees trains without waiting for the next tick."""
        await websocket.accept()
        client = _Client(websocket)
        client.offer(initial_payload)
        client.sender = asyncio.create_task(self._run_sender(client))
        self._clients[websocket] = client

    async def disconnect(self, websocket: WebSocket) -> None:
        client = self._clients.pop(websocket, None)
        if client is None or client.sender is None:
            return
        client.sender.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await client.sender

    def broadcast(self, payload: str) -> None:
        """Queue `payload` for every client. Never waits on the network."""
        for client in self._clients.values():
            client.offer(payload)

    async def _run_sender(self, client: _Client) -> None:
        try:
            await client.send_forever()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a failed socket must only drop that client
            logger.debug("dropping /ws/live client after a failed send", exc_info=True)
            self._clients.pop(client.websocket, None)

    @property
    def active_connection_count(self) -> int:
        return len(self._clients)
