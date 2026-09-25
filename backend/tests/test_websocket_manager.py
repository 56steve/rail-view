"""Fan-out to WebSocket clients."""

import asyncio

from app.services.live_wire import WireFormat
from app.services.websocket_manager import ConnectionManager


class FakeSnapshot:
    """A tick whose payload names itself and the format it was asked for;
    binary for deflate, like the real one."""

    def __init__(self, name: str) -> None:
        self.name = name

    def payload(self, wire: WireFormat) -> str | bytes:
        text = f"{self.name}:{wire}"
        return text.encode() if wire == "deflate" else text


class FakeSocket:
    """A client whose network can be held up: sends wait on `gate`."""

    def __init__(self, *, open_gate: bool = True, fail: bool = False) -> None:
        self.accepted = False
        self.sent: list[str] = []
        self.sent_binary: list[bytes] = []
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

    async def send_bytes(self, payload: bytes) -> None:
        await self.gate.wait()
        if self.fail:
            raise ConnectionResetError("client went away")
        self.sent_binary.append(payload)


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def test_a_new_client_gets_the_current_snapshot_first() -> None:
    manager = ConnectionManager()
    socket = FakeSocket()
    await manager.connect(socket, FakeSnapshot("initial"), "table")  # type: ignore[arg-type]
    await settle()

    assert socket.accepted
    assert socket.sent == ["initial:table"]
    await manager.disconnect(socket)  # type: ignore[arg-type]


async def test_each_client_gets_the_format_it_asked_for() -> None:
    manager = ConnectionManager()
    old_app, lean, compressed = FakeSocket(), FakeSocket(), FakeSocket()
    await manager.connect(old_app, FakeSnapshot("s0"), "legacy")  # type: ignore[arg-type]
    await manager.connect(lean, FakeSnapshot("s0"), "table")  # type: ignore[arg-type]
    await manager.connect(compressed, FakeSnapshot("s0"), "deflate")  # type: ignore[arg-type]
    await settle()
    manager.broadcast(FakeSnapshot("s1"))  # type: ignore[arg-type]
    await settle()

    assert old_app.sent == ["s0:legacy", "s1:legacy"]
    assert lean.sent == ["s0:table", "s1:table"]
    assert compressed.sent == []
    assert compressed.sent_binary == [b"s0:deflate", b"s1:deflate"]
    for socket in (old_app, lean, compressed):
        await manager.disconnect(socket)  # type: ignore[arg-type]


async def test_a_slow_client_does_not_hold_up_the_others() -> None:
    manager = ConnectionManager()
    slow, fast = FakeSocket(open_gate=False), FakeSocket()
    await manager.connect(slow, FakeSnapshot("s0"), "table")  # type: ignore[arg-type]
    await manager.connect(fast, FakeSnapshot("s0"), "table")  # type: ignore[arg-type]
    await settle()

    for tick in range(1, 4):
        manager.broadcast(FakeSnapshot(f"s{tick}"))  # type: ignore[arg-type]
        await settle()

    assert fast.sent == ["s0:table", "s1:table", "s2:table", "s3:table"]
    assert slow.sent == []

    # Once its network catches up it gets what it was sending, then only
    # the newest snapshot - never a backlog of stale positions.
    slow.gate.set()
    await settle()
    assert slow.sent == ["s0:table", "s3:table"]

    for socket in (slow, fast):
        await manager.disconnect(socket)  # type: ignore[arg-type]


async def test_a_failed_send_drops_only_that_client() -> None:
    manager = ConnectionManager()
    broken, healthy = FakeSocket(fail=True), FakeSocket()
    await manager.connect(broken, FakeSnapshot("s0"), "table")  # type: ignore[arg-type]
    await manager.connect(healthy, FakeSnapshot("s0"), "table")  # type: ignore[arg-type]
    await settle()

    assert manager.active_connection_count == 1
    manager.broadcast(FakeSnapshot("s1"))  # type: ignore[arg-type]
    await settle()
    assert healthy.sent == ["s0:table", "s1:table"]

    await manager.disconnect(broken)  # type: ignore[arg-type]
    await manager.disconnect(healthy)  # type: ignore[arg-type]
    assert manager.active_connection_count == 0
