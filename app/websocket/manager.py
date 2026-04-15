from collections import defaultdict

from fastapi import WebSocket
from starlette.websockets import WebSocketState


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, booking_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections[booking_id].add(websocket)

    def disconnect(self, booking_id: int, websocket: WebSocket) -> None:
        if booking_id in self.active_connections and websocket in self.active_connections[booking_id]:
            self.active_connections[booking_id].discard(websocket)
            if not self.active_connections[booking_id]:
                self.active_connections.pop(booking_id, None)

    async def broadcast(self, booking_id: int, message: str) -> None:
        stale_connections: list[WebSocket] = []
        for connection in list(self.active_connections.get(booking_id, set())):
            if connection.client_state != WebSocketState.CONNECTED:
                stale_connections.append(connection)
                continue
            try:
                await connection.send_text(message)
            except Exception:
                stale_connections.append(connection)

        for connection in stale_connections:
            self.disconnect(booking_id, connection)


connection_manager = ConnectionManager()
