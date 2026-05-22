from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt

from fastapi import HTTPException, status
import json
import logging
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.booking import Booking, BookingStatus
from app.models.dispatch import DriverAvailability, DriverRequestDismissal, RideRequest, RideRequestStatus
from app.models.notification import NotificationType
from app.models.ride import Ride, RideStatus
from app.models.user import User, UserRole
from app.repositories.booking import BookingRepository
from app.repositories.dispatch import DispatchRepository
from app.repositories.ride import RideRepository
from app.services.audit_log import AuditLogService
from app.services.notification_jobs import enqueue_dispatch_notification


class DispatchService:
    def __init__(self, db: Session) -> None:
        self.dispatch = DispatchRepository(db)
        self.rides = RideRepository(db)
        self.bookings = BookingRepository(db)
        self.audit_logs = AuditLogService(db)
        self.redis = self._create_redis_client()
        self.logger = logging.getLogger(__name__)
        self.notification_session_factory = sessionmaker(
            bind=db.get_bind(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )

    def _create_redis_client(self) -> Redis:
        return Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
        )

    def upsert_driver_presence(self, payload: dict[str, float | bool | None], current_user: User) -> DriverAvailability:
        if current_user.role != UserRole.driver:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only driver accounts can update availability")

        existing = self.dispatch.get_driver_availability(current_user.id)
        if existing:
            existing.latitude = float(payload["latitude"])
            existing.longitude = float(payload["longitude"])
            existing.heading = payload.get("heading") if payload.get("heading") is not None else None
            existing.is_online = bool(payload.get("is_online", True))
            existing.updated_at = datetime.now(timezone.utc)
            availability = self.dispatch.upsert_driver_availability(existing)
        else:
            availability = self.dispatch.upsert_driver_availability(
                DriverAvailability(
                    driver_id=current_user.id,
                    latitude=float(payload["latitude"]),
                    longitude=float(payload["longitude"]),
                    heading=payload.get("heading") if payload.get("heading") is not None else None,
                    is_online=bool(payload.get("is_online", True)),
                )
            )
        self.dispatch.db.commit()
        return availability

    def touch_driver_presence(self, driver_id: int) -> DriverAvailability | None:
        availability = self.dispatch.touch_driver_availability(driver_id)
        if availability:
            self.dispatch.db.commit()
        return availability

    def create_request(self, payload: dict[str, object], current_user: User) -> RideRequest:
        if current_user.role != UserRole.passenger:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only passenger accounts can request rides")

        try:
            self._expire_stale_open_requests()
            existing_open_request = self.dispatch.get_open_request_for_passenger(current_user.id)
            if existing_open_request:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Passenger already has an open ride request",
                )
            request = RideRequest(
                passenger_id=current_user.id,
                origin=str(payload["origin"]),
                destination=str(payload["destination"]),
                origin_latitude=float(payload["origin_latitude"]),
                origin_longitude=float(payload["origin_longitude"]),
                destination_latitude=float(payload["destination_latitude"]),
                destination_longitude=float(payload["destination_longitude"]),
                requested_departure_time=payload["requested_departure_time"],
                notes=payload.get("notes") if payload.get("notes") else None,
            )
            saved_request = self.dispatch.create_ride_request(request)
            self.dispatch.db.commit()
            self.audit_logs.record(
                action="ride_request_created",
                actor_user_id=current_user.id,
                entity_type="ride_request",
                entity_id=str(saved_request.id),
                metadata={"origin": saved_request.origin, "destination": saved_request.destination},
            )
            self._publish_nearby_request_created(saved_request)
            return saved_request
        except Exception:
            self.dispatch.db.rollback()
            raise

    def list_my_requests(self, current_user: User) -> list[RideRequest]:
        if current_user.role != UserRole.passenger:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only passenger accounts can view requests")
        self._expire_stale_open_requests()
        return self.dispatch.list_by_passenger(current_user.id)

    def list_nearby_requests(self, current_user: User, *, limit: int = 25) -> list[dict[str, object]]:
        if current_user.role != UserRole.driver:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only driver accounts can view nearby requests")
        self._expire_stale_open_requests()
        availability = self._get_fresh_driver_availability(current_user.id)
        if not availability:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver availability not found")

        nearby: list[dict[str, object]] = []
        for request in self.dispatch.list_open_requests(driver_id=current_user.id, limit=limit * 4):
            distance_km = self._distance_km(
                availability.latitude,
                availability.longitude,
                request.origin_latitude,
                request.origin_longitude,
            )
            if distance_km <= settings.DISPATCH_NEARBY_RADIUS_KM:
                nearby.append({"request": request, "distance_km": round(distance_km, 2)})

        nearby.sort(key=lambda item: item["distance_km"])
        return nearby[:limit]

    def decline_request(self, request_id: int, current_user: User) -> dict[str, object]:
        if current_user.role != UserRole.driver:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only driver accounts can decline ride requests")

        availability = self._get_fresh_driver_availability(current_user.id)
        if not availability:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver availability not found")

        try:
            ride_request = self.dispatch.get_ride_request(request_id)
            if not ride_request or ride_request.status != RideRequestStatus.open:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride request not found")

            if not self.dispatch.get_driver_request_dismissal(current_user.id, request_id):
                self.dispatch.create_driver_request_dismissal(
                    DriverRequestDismissal(driver_id=current_user.id, request_id=request_id)
                )
                self.dispatch.db.commit()
            self._publish_driver_event(
                current_user.id,
                {
                    "event_type": "nearby_request_removed",
                    "request_id": request_id,
                    "reason": "declined",
                },
            )
            return {
                "request_id": request_id,
                "driver_id": current_user.id,
                "dismissed": True,
            }
        except Exception:
            self.dispatch.db.rollback()
            raise

    def cancel_request(self, request_id: int, current_user: User) -> RideRequest:
        if current_user.role != UserRole.passenger:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only passenger accounts can cancel ride requests")

        try:
            ride_request = self.dispatch.get_ride_request(request_id)
            if not ride_request or ride_request.passenger_id != current_user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride request not found")

            self._expire_stale_open_requests()
            if ride_request.status != RideRequestStatus.open:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only open ride requests can be cancelled")

            ride_request.status = RideRequestStatus.cancelled
            saved_request = self.dispatch.save_ride_request(ride_request)
            self.dispatch.db.commit()
            self.audit_logs.record(
                action="ride_request_cancelled",
                actor_user_id=current_user.id,
                entity_type="ride_request",
                entity_id=str(saved_request.id),
                metadata={"origin": saved_request.origin, "destination": saved_request.destination},
            )
            self._publish_nearby_request_removed(saved_request, reason="cancelled")
            self._publish_passenger_event(
                current_user.id,
                {
                    "event_type": "request_cancelled",
                    "request": self._serialize_request(saved_request),
                },
            )
            self._enqueue_dispatch_notification(
                recipient_id=current_user.id,
                notification_type=NotificationType.dispatch_cancelled,
                title="Ride request cancelled",
                body=f"Your request from {saved_request.origin} to {saved_request.destination} was cancelled.",
            )
            return saved_request
        except Exception:
            self.dispatch.db.rollback()
            raise

    def accept_request(self, request_id: int, current_user: User) -> dict[str, int | float | RideRequest]:
        if current_user.role != UserRole.driver:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only driver accounts can accept ride requests")

        self._expire_stale_open_requests()
        availability = self._get_fresh_driver_availability(current_user.id)
        if not availability:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver availability not found")

        try:
            ride_request = self.dispatch.get_ride_request_for_update(request_id)
            if not ride_request:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride request not found")
            if ride_request.status != RideRequestStatus.open:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ride request is no longer open")

            distance_km = self._distance_km(
                availability.latitude,
                availability.longitude,
                ride_request.origin_latitude,
                ride_request.origin_longitude,
            )
            if distance_km > settings.DISPATCH_NEARBY_RADIUS_KM:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ride request is too far away")

            estimated_price = round(
                max(
                    settings.DISPATCH_BASE_FARE,
                    distance_km * settings.DISPATCH_PER_KM_RATE,
                ),
                2,
            )

            ride = Ride(
                driver_id=current_user.id,
                origin=ride_request.origin,
                destination=ride_request.destination,
                origin_latitude=ride_request.origin_latitude,
                origin_longitude=ride_request.origin_longitude,
                destination_latitude=ride_request.destination_latitude,
                destination_longitude=ride_request.destination_longitude,
                departure_time=ride_request.requested_departure_time,
                available_seats=1,
                price_per_seat=estimated_price,
                vehicle_details=None,
                notes=ride_request.notes,
                status=RideStatus.full,
                is_active=False,
            )
            saved_ride = self.rides.create(ride)
            booking = Booking(
                ride_id=saved_ride.id,
                passenger_id=ride_request.passenger_id,
                status=BookingStatus.accepted,
                notes=ride_request.notes,
            )
            saved_booking = self.bookings.create(booking)
            saved_ride.available_seats = 0
            ride_request.status = RideRequestStatus.matched
            ride_request.matched_driver_id = current_user.id
            ride_request.matched_ride_id = saved_ride.id
            ride_request.matched_booking_id = saved_booking.id
            self.rides.save(saved_ride)
            self.dispatch.save_ride_request(ride_request)
            self.dispatch.db.commit()
            self.audit_logs.record(
                action="ride_request_matched",
                actor_user_id=current_user.id,
                entity_type="ride_request",
                entity_id=str(ride_request.id),
                metadata={"ride_id": saved_ride.id, "booking_id": saved_booking.id},
            )
            self._publish_nearby_request_removed(ride_request, reason="matched")
            self._publish_passenger_event(
                ride_request.passenger_id,
                {
                    "event_type": "request_matched",
                    "request": self._serialize_request(ride_request),
                    "ride_id": saved_ride.id,
                    "booking_id": saved_booking.id,
                    "estimated_price_per_seat": estimated_price,
                },
            )
            self._enqueue_dispatch_notification(
                recipient_id=ride_request.passenger_id,
                notification_type=NotificationType.dispatch_matched,
                title="Driver matched",
                body=f"{current_user.full_name} accepted your request from {ride_request.origin} to {ride_request.destination}.",
            )
            self._enqueue_dispatch_notification(
                recipient_id=current_user.id,
                notification_type=NotificationType.dispatch_matched,
                title="Request accepted",
                body=f"You matched a request from {ride_request.origin} to {ride_request.destination}.",
            )
            return {
                "request": ride_request,
                "ride_id": saved_ride.id,
                "booking_id": saved_booking.id,
                "estimated_price_per_seat": estimated_price,
            }
        except Exception:
            self.dispatch.db.rollback()
            raise

    def _distance_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        earth_radius_km = 6371.0
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        return 2 * earth_radius_km * asin(sqrt(a))

    def _get_fresh_driver_availability(self, driver_id: int) -> DriverAvailability | None:
        availability = self.dispatch.get_driver_availability(driver_id)
        if not availability or not availability.is_online:
            return None

        updated_at = availability.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)

        if (datetime.now(timezone.utc) - updated_at).total_seconds() > settings.DISPATCH_PRESENCE_STALE_AFTER_SECONDS:
            availability.is_online = False
            availability.updated_at = datetime.now(timezone.utc)
            self.dispatch.upsert_driver_availability(availability)
            self.dispatch.db.commit()
            return None

        return availability

    def _expire_stale_open_requests(self) -> None:
        now = datetime.now(timezone.utc)
        expired_any = False
        for ride_request in self.dispatch.list_open_requests(limit=500):
            departure_time = ride_request.requested_departure_time
            if departure_time.tzinfo is None:
                departure_time = departure_time.replace(tzinfo=timezone.utc)
            if departure_time < now:
                ride_request.status = RideRequestStatus.expired
                self.dispatch.save_ride_request(ride_request)
                self._publish_nearby_request_removed(ride_request, reason="expired")
                self._publish_passenger_event(
                    ride_request.passenger_id,
                    {
                        "event_type": "request_expired",
                        "request": self._serialize_request(ride_request),
                    },
                )
                self._enqueue_dispatch_notification(
                    recipient_id=ride_request.passenger_id,
                    notification_type=NotificationType.dispatch_expired,
                    title="Ride request expired",
                    body=f"Your request from {ride_request.origin} to {ride_request.destination} expired before a driver accepted it.",
                )
                expired_any = True

        if expired_any:
            self.dispatch.db.commit()

    def _serialize_request(self, ride_request: RideRequest) -> dict[str, object]:
        return {
            "id": ride_request.id,
            "passenger_id": ride_request.passenger_id,
            "origin": ride_request.origin,
            "destination": ride_request.destination,
            "origin_latitude": ride_request.origin_latitude,
            "origin_longitude": ride_request.origin_longitude,
            "destination_latitude": ride_request.destination_latitude,
            "destination_longitude": ride_request.destination_longitude,
            "requested_departure_time": ride_request.requested_departure_time.isoformat(),
            "notes": ride_request.notes,
            "status": ride_request.status.value,
            "matched_driver_id": ride_request.matched_driver_id,
            "matched_ride_id": ride_request.matched_ride_id,
            "matched_booking_id": ride_request.matched_booking_id,
            "created_at": ride_request.created_at.isoformat(),
        }

    def _publish_nearby_request_created(self, ride_request: RideRequest) -> None:
        nearby_driver_ids = self._list_nearby_online_driver_ids(ride_request)
        payload = {
            "event_type": "nearby_request_created",
            "request": self._serialize_request(ride_request),
        }
        for driver_id in nearby_driver_ids:
            availability = self.dispatch.get_driver_availability(driver_id)
            if not availability:
                continue
            payload_with_distance = {
                **payload,
                "distance_km": round(
                    self._distance_km(
                        availability.latitude,
                        availability.longitude,
                        ride_request.origin_latitude,
                        ride_request.origin_longitude,
                    ),
                    2,
                ),
            }
            self._publish_driver_event(driver_id, payload_with_distance)

    def _publish_nearby_request_removed(self, ride_request: RideRequest, *, reason: str) -> None:
        payload = {
            "event_type": "nearby_request_removed",
            "request_id": ride_request.id,
            "reason": reason,
        }
        for driver_id in self._list_nearby_online_driver_ids(ride_request):
            self._publish_driver_event(driver_id, payload)

    def _list_nearby_online_driver_ids(self, ride_request: RideRequest) -> list[int]:
        nearby_driver_ids: list[int] = []
        for availability in self.dispatch.db.query(DriverAvailability).filter(DriverAvailability.is_online.is_(True)).all():
            distance_km = self._distance_km(
                availability.latitude,
                availability.longitude,
                ride_request.origin_latitude,
                ride_request.origin_longitude,
            )
            if distance_km <= settings.DISPATCH_NEARBY_RADIUS_KM:
                nearby_driver_ids.append(availability.driver_id)
        return nearby_driver_ids

    def _publish_driver_event(self, driver_id: int, payload: dict[str, object]) -> None:
        self._publish(f"dispatch:driver:{driver_id}", payload)

    def _publish_passenger_event(self, passenger_id: int, payload: dict[str, object]) -> None:
        self._publish(f"dispatch:passenger:{passenger_id}", payload)

    def _enqueue_dispatch_notification(
        self,
        *,
        recipient_id: int,
        notification_type: NotificationType,
        title: str,
        body: str,
    ) -> None:
        enqueue_dispatch_notification(
            session_factory=self.notification_session_factory,
            recipient_id=recipient_id,
            notification_type=notification_type,
            title=title,
            body=body,
        )

    def _publish(self, channel: str, payload: dict[str, object]) -> None:
        message = json.dumps(payload)
        for attempt in range(2):
            try:
                self.redis.publish(channel, message)
                return
            except RedisError:
                self.logger.exception("Failed to publish dispatch event on channel=%s", channel)
                if attempt == 0:
                    try:
                        self.redis.close()
                    except Exception:
                        pass
                    self.redis = self._create_redis_client()
                    continue
                break
            except Exception:
                self.logger.exception("Failed to publish dispatch event on channel=%s", channel)
                break
