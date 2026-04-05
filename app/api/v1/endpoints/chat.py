import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from jose import JWTError
from redis import asyncio as redis_asyncio
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.security import decode_token
from app.models.user import User
from app.repositories.booking import BookingRepository
from app.repositories.user import UserRepository
from app.schemas.message import MessageCreate, MessageResponse
from app.services.chat import ChatService
from app.websocket.manager import connection_manager

router = APIRouter()


@router.get("/{booking_id}/messages", response_model=list[MessageResponse])
def list_messages(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MessageResponse]:
    return ChatService(db).list_messages(booking_id, current_user)


@router.post("/messages", response_model=MessageResponse)
def send_message(
    payload: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    return ChatService(db).save_message(payload, current_user)


@router.websocket("/ws/{booking_id}")
async def chat_socket(websocket: WebSocket, booking_id: int, token: str) -> None:
    db = next(get_db())
    redis_client = redis_asyncio.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = redis_client.pubsub()
    try:
        try:
            payload = decode_token(token)
            user_id = int(payload.get("sub", "0"))
        except (JWTError, ValueError):
            await websocket.close(code=1008)
            return

        user = UserRepository(db).get_by_id(user_id)
        booking = BookingRepository(db).get_by_id(booking_id)
        if not user or not booking or user.id not in {booking.passenger_id, booking.ride.driver_id}:
            await websocket.close(code=1008)
            return

        await connection_manager.connect(booking_id, websocket)
        await pubsub.subscribe(f"chat:{booking_id}")
        try:
            while True:
                event = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if event and event.get("data"):
                    await connection_manager.broadcast(booking_id, event["data"])
                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            connection_manager.disconnect(booking_id, websocket)
    finally:
        await pubsub.unsubscribe(f"chat:{booking_id}")
        await pubsub.close()
        await redis_client.close()
        db.close()
