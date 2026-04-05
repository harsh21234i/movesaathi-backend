from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[int, list[WebSocket]] = defaultdict(list)

    async def connect(self, booking_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections[booking_id].append(websocket)

    def disconnect(self, booking_id: int, websocket: WebSocket) -> None:
        if booking_id in self.active_connections and websocket in self.active_connections[booking_id]:
            self.active_connections[booking_id].remove(websocket)

    async def broadcast(self, booking_id: int, message: str) -> None:
        for connection in self.active_connections.get(booking_id, []):
            await connection.send_text(message)


connection_manager = ConnectionManager()
