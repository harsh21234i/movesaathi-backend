import asyncio

import json

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from jose import JWTError
from redis import asyncio as redis_asyncio
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.rate_limit import rate_limit_dependency
from app.core.security import decode_token
from app.models.user import User
from app.repositories.booking import BookingRepository
from app.repositories.user import UserRepository
from app.schemas.message import MessageCreate, MessageResponse, MessageSeenResponse
from app.services.chat import ChatService
from app.websocket.manager import connection_manager

router = APIRouter()


def _chat_identifier(request: Request) -> str:
    body = getattr(request.state, "json_body", None) or {}
    booking_id = body.get("booking_id", "unknown")
    client_host = request.client.host if request.client else "unknown"
    return f"{client_host}:{booking_id}"


async def cache_json_body(request: Request) -> None:
    request.state.json_body = await request.json()


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
    _: None = Depends(cache_json_body),
    __: None = Depends(
        rate_limit_dependency(
            "chat-message",
            limit=lambda: settings.CHAT_MESSAGE_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=lambda: settings.CHAT_MESSAGE_RATE_LIMIT_WINDOW_SECONDS,
            identifier_getter=_chat_identifier,
        )
    ),
) -> MessageResponse:
    return ChatService(db).save_message(payload, current_user)


@router.post("/{booking_id}/seen", response_model=MessageSeenResponse)
def mark_seen(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageSeenResponse:
    return ChatService(db).mark_messages_seen(booking_id, current_user)


@router.websocket("/ws/{booking_id}")
async def chat_socket(websocket: WebSocket, booking_id: int, token: str) -> None:
    db = next(get_db())
    chat_service = ChatService(db)
    redis_client = redis_asyncio.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
    )
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
                try:
                    message = await asyncio.wait_for(websocket.receive(), timeout=0.1)
                    if message["type"] == "websocket.disconnect":
                        break
                    if message["type"] != "websocket.receive":
                        continue

                    raw_text = message.get("text")
                    if not raw_text:
                        continue

                    try:
                        payload = json.loads(raw_text)
                    except json.JSONDecodeError:
                        continue

                    if payload.get("event_type") == "typing":
                        chat_service.publish_typing(
                            booking_id,
                            user,
                            is_typing=bool(payload.get("is_typing")),
                        )
                except TimeoutError:
                    continue
        except WebSocketDisconnect:
            pass
    finally:
        connection_manager.disconnect(booking_id, websocket)
        await pubsub.unsubscribe(f"chat:{booking_id}")
        await pubsub.close()
        await redis_client.close()
        db.close()
