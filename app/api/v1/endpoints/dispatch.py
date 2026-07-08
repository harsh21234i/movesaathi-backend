import asyncio
import json

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from jose import JWTError
from redis import asyncio as redis_asyncio
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.dispatch import RideRequestStatus
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.dispatch import (
    DriverPresenceResponse,
    DriverPresenceUpsert,
    NearbyRideRequestResponse,
    RequestAcceptanceResponse,
    RideRequestCreate,
    RideRequestResponse,
)
from app.services.dispatch import DispatchService
from app.core.config import settings
from app.core.security import decode_token
from app.models.user import UserRole
from app.websocket.manager import connection_manager

router = APIRouter()


@router.post("/presence", response_model=DriverPresenceResponse, status_code=status.HTTP_201_CREATED)
def upsert_presence(
    payload: DriverPresenceUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DriverPresenceResponse:
    return DriverPresenceResponse.model_validate(
        DispatchService(db).upsert_driver_presence(payload.model_dump(), current_user)
    )


@router.get("/presence", response_model=DriverPresenceResponse)
def get_presence(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DriverPresenceResponse:
    return DriverPresenceResponse.model_validate(DispatchService(db).get_driver_presence(current_user))


@router.post("/requests", response_model=RideRequestResponse, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: RideRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RideRequestResponse:
    return RideRequestResponse.model_validate(
        DispatchService(db).create_request(payload.model_dump(), current_user)
    )


@router.get("/requests/mine", response_model=list[RideRequestResponse])
def list_my_requests(
    status_filter: RideRequestStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RideRequestResponse]:
    requests = DispatchService(db).list_my_requests(current_user)
    if status_filter:
        requests = [request for request in requests if request.status == status_filter]
    return [RideRequestResponse.model_validate(request) for request in requests]


@router.get("/requests/nearby", response_model=list[NearbyRideRequestResponse])
def list_nearby_requests(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[NearbyRideRequestResponse]:
    nearby = DispatchService(db).list_nearby_requests(current_user, limit=limit)
    return [
        NearbyRideRequestResponse.model_validate(
            {
                **RideRequestResponse.model_validate(item["request"]).model_dump(),
                "distance_km": item["distance_km"],
            }
        )
        for item in nearby
    ]


@router.post("/requests/{request_id}/cancel", response_model=RideRequestResponse)
def cancel_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RideRequestResponse:
    return RideRequestResponse.model_validate(DispatchService(db).cancel_request(request_id, current_user))


@router.post("/requests/{request_id}/decline")
def decline_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    return DispatchService(db).decline_request(request_id, current_user)


@router.post("/requests/{request_id}/accept", response_model=RequestAcceptanceResponse)
def accept_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RequestAcceptanceResponse:
    return RequestAcceptanceResponse.model_validate(DispatchService(db).accept_request(request_id, current_user))


@router.websocket("/ws")
async def dispatch_socket(websocket: WebSocket, token: str) -> None:
    db = next(get_db())
    dispatch_service = DispatchService(db)
    redis_client = redis_asyncio.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
    )
    pubsub = redis_client.pubsub()
    room_id: int | None = None
    try:
        try:
            payload = decode_token(token)
            user_id = int(payload.get("sub", "0"))
        except (JWTError, ValueError):
            await websocket.close(code=1008)
            return

        user = UserRepository(db).get_by_id(user_id)
        if not user:
            await websocket.close(code=1008)
            return

        room_id = -user.id if user.role == UserRole.driver else user.id
        channel = f"dispatch:driver:{user.id}" if user.role == UserRole.driver else f"dispatch:passenger:{user.id}"

        await connection_manager.connect(room_id, websocket)
        await pubsub.subscribe(channel)
        try:
            while True:
                event = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if event and event.get("data"):
                    await connection_manager.broadcast(room_id, event["data"])
                try:
                    message = await asyncio.wait_for(websocket.receive(), timeout=0.1)
                    if message["type"] == "websocket.disconnect":
                        break
                    if message["type"] != "websocket.receive":
                        continue

                    raw_text = message.get("text")
                    if raw_text:
                        try:
                            payload = json.loads(raw_text)
                        except json.JSONDecodeError:
                            payload = None
                        if payload and payload.get("event_type") == "ping":
                            if user.role == UserRole.driver:
                                dispatch_service.touch_driver_presence(user.id)
                            await websocket.send_text(json.dumps({"event_type": "pong"}))
                except TimeoutError:
                    continue
        except WebSocketDisconnect:
            pass
    finally:
        if room_id is not None:
            connection_manager.disconnect(room_id, websocket)
        await pubsub.close()
        await redis_client.close()
        db.close()
