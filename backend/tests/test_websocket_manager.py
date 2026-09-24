"""Fan-out to WebSocket clients."""

import asyncio

from app.services.websocket_manager import ConnectionManager


class FakeSocket:
    """A client whose network can be held up: sends wait on `gate`."""

    def __init__(self, *, open_gate: bool = True, fail: bool = False) -> None:
        self.accepted = False
        self.sent: list[str] = []
        self.gate = asyncio.Event()
        self.fail = fail
        if open_gate:
            self.gate.set()

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, payload: str) -> None:
        await self.gate.wait()
        if self.fail:
            raise ConnectionResetError("client went away")
        self.sent.append(payload)


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def test_a_new_client_gets_the_current_snapshot_first() -> None:
    manager = ConnectionManager()
    socket = FakeSocket()
    await manager.connect(socket, "initial")  # type: ignore[arg-type]
    await settle()

    assert socket.accepted
    assert socket.sent == ["initial"]
    await manager.disconnect(socket)  # type: ignore[arg-type]


async def test_a_slow_client_does_not_hold_up_the_others() -> None:
    manager = ConnectionManager()
    slow, fast = FakeSocket(open_gate=False), FakeSocket()
    await manager.connect(slow, "s0")  # type: ignore[arg-type]
    await manager.connect(fast, "s0")  # type: ignore[arg-type]
    await settle()

    for tick in range(1, 4):
        manager.broadcast(f"s{tick}")
        await settle()

    assert fast.sent == ["s0", "s1", "s2", "s3"]
    assert slow.sent == []

    # Once its network catches up it gets what it was sending, then only
    # the newest snapshot - never a backlog of stale positions.
    slow.gate.set()
    await settle()
    assert slow.sent == ["s0", "s3"]

    for socket in (slow, fast):
        await manager.disconnect(socket)  # type: ignore[arg-type]


async def test_a_failed_send_drops_only_that_client() -> None:
    manager = ConnectionManager()
    broken, healthy = FakeSocket(fail=True), FakeSocket()
    await manager.connect(broken, "s0")  # type: ignore[arg-type]
    await manager.connect(healthy, "s0")  # type: ignore[arg-type]
    await settle()

    assert manager.active_connection_count == 1
    manager.broadcast("s1")
    await settle()
    assert healthy.sent == ["s0", "s1"]

    await manager.disconnect(broken)  # type: ignore[arg-type]
    await manager.disconnect(healthy)  # type: ignore[arg-type]
    assert manager.active_connection_count == 0
