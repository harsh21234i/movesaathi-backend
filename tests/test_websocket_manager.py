from __future__ import annotations

import asyncio

from app.websocket.manager import ConnectionManager
from starlette.websockets import WebSocketState


class DummyWebSocket:
    def __init__(self, *, connected: bool = True, fail_send: bool = False) -> None:
        self.client_state = WebSocketState.CONNECTED if connected else WebSocketState.DISCONNECTED
        self.fail_send = fail_send
        self.accepted = False
        self.sent: list[str] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, message: str) -> None:
        if self.fail_send:
            raise RuntimeError("send failed")
        self.sent.append(message)


def test_connection_manager_broadcast_removes_stale_connections() -> None:
    manager = ConnectionManager()
    healthy = DummyWebSocket()
    stale = DummyWebSocket(connected=False)

    asyncio.run(manager.connect(1, healthy))
    manager.active_connections[1].add(stale)

    asyncio.run(manager.broadcast(1, "hello"))

    assert healthy.sent == ["hello"]
    assert stale not in manager.active_connections.get(1, set())


def test_connection_manager_disconnect_clears_empty_booking_bucket() -> None:
    manager = ConnectionManager()
    websocket = DummyWebSocket()

    asyncio.run(manager.connect(2, websocket))
    manager.disconnect(2, websocket)

    assert 2 not in manager.active_connections
