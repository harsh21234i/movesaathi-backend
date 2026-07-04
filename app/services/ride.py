from datetime import datetime, timedelta, timezone
from math import cos, radians, sqrt

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.ride import Ride, RideLocation
from app.models.booking import BookingStatus
from app.models.notification import NotificationType
from app.models.ride import RideStatus
from app.models.user import DriverVerificationStatus, User, UserRole
from app.services.audit_log import AuditLogService
from app.repositories.ride import RideRepository
from app.schemas.ride import RideCreate, RideLocationAccessResponse, RideLocationCreate, RideSearchParams, RideUpdate
from app.services.notification_jobs import enqueue_notification
from app.services.notification import NotificationService


class RideService:
    def __init__(self, db: Session) -> None:
        self.rides = RideRepository(db)
        self.notifications = NotificationService(db)
        self.audit_logs = AuditLogService(db)
        self.notification_session_factory = sessionmaker(
            bind=db.get_bind(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )

    def create_ride(self, payload: RideCreate, current_user: User) -> Ride:
        if current_user.role != UserRole.driver:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only driver accounts can publish rides",
            )
        self._ensure_verified_driver(current_user)

        try:
            ride = Ride(
                driver_id=current_user.id,
                origin=payload.origin,
                destination=payload.destination,
                origin_latitude=payload.origin_latitude,
                origin_longitude=payload.origin_longitude,
                destination_latitude=payload.destination_latitude,
                destination_longitude=payload.destination_longitude,
                departure_time=payload.departure_time,
                available_seats=payload.available_seats,
                price_per_seat=payload.price_per_seat,
                vehicle_details=payload.vehicle_details,
                notes=payload.notes,
                status=RideStatus.scheduled,
                is_active=True,
            )
            saved_ride = self.rides.create(ride)
            self.rides.db.commit()
            self.audit_logs.record(
                action="ride_created",
                actor_user_id=current_user.id,
                entity_type="ride",
                entity_id=str(saved_ride.id),
                metadata={"origin": saved_ride.origin, "destination": saved_ride.destination},
            )
            return saved_ride
        except Exception:
            self.rides.db.rollback()
            raise

    def search_rides(self, params: RideSearchParams) -> list[Ride]:
        return self.rides.search(
            origin=params.origin,
            destination=params.destination,
            departure_after=params.departure_after,
            limit=params.limit,
            offset=params.offset,
        )

    def get_ride_detail(self, ride_id: int, current_user: User | None = None) -> Ride:
        ride = self.rides.get_detail_by_id(ride_id)
        if not ride:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")

        accepted_bookings = [
            booking for booking in ride.bookings if booking.status == BookingStatus.accepted
        ]
        ride.booked_passengers = len(accepted_bookings)  # type: ignore[attr-defined]
        ride.passengers = [booking.passenger for booking in accepted_bookings]  # type: ignore[attr-defined]
        ride.booking_id = None  # type: ignore[attr-defined]

        if current_user and current_user.role == UserRole.passenger:
            current_booking = next(
                (
                    booking
                    for booking in ride.bookings
                    if booking.passenger_id == current_user.id
                ),
                None,
            )
            ride.booking_id = current_booking.id if current_booking else None  # type: ignore[attr-defined]

        return ride

    def update_ride(self, ride_id: int, payload: RideUpdate, current_user: User) -> Ride:
        if current_user.role != UserRole.driver:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only driver accounts can update rides",
            )

        try:
            ride = self.rides.get_by_id_for_update(ride_id)
            if not ride:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")
            if ride.driver_id != current_user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only driver can update this ride")
            if ride.status in {RideStatus.cancelled, RideStatus.completed}:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Completed or cancelled rides cannot be updated",
                )

            accepted_bookings = sum(1 for booking in ride.bookings if booking.status == BookingStatus.accepted)
            minimum_available_seats = accepted_bookings
            if payload.available_seats < minimum_available_seats:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Available seats cannot be lower than accepted passengers",
                )

            ride.origin = payload.origin
            ride.destination = payload.destination
            ride.origin_latitude = payload.origin_latitude
            ride.origin_longitude = payload.origin_longitude
            ride.destination_latitude = payload.destination_latitude
            ride.destination_longitude = payload.destination_longitude
            ride.departure_time = payload.departure_time
            ride.available_seats = payload.available_seats
            ride.price_per_seat = payload.price_per_seat
            ride.vehicle_details = payload.vehicle_details
            ride.notes = payload.notes
            ride.status = RideStatus.full if payload.available_seats == 0 else RideStatus.scheduled
            ride.is_active = ride.status == RideStatus.scheduled
            saved_ride = self.rides.save(ride)
            self.rides.db.commit()
            self.audit_logs.record(
                action="ride_updated",
                actor_user_id=current_user.id,
                entity_type="ride",
                entity_id=str(saved_ride.id),
            )
            return saved_ride
        except Exception:
            self.rides.db.rollback()
            raise

    def cancel_ride(self, ride_id: int, current_user: User) -> None:
        if current_user.role != UserRole.driver:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only driver accounts can cancel rides",
            )

        try:
            ride = self.rides.get_by_id_for_update(ride_id)
            if not ride:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")
            if ride.driver_id != current_user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only driver can cancel this ride")
            if ride.status == RideStatus.completed:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Completed rides cannot be cancelled")
            if ride.status == RideStatus.cancelled:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ride is already cancelled")

            ride.status = RideStatus.cancelled
            ride.is_active = False
            for booking in ride.bookings:
                if booking.status in {BookingStatus.pending, BookingStatus.accepted}:
                    booking.status = BookingStatus.cancelled_by_driver
                    enqueue_notification(
                        session_factory=self.notification_session_factory,
                        recipient_id=booking.passenger_id,
                        notification_type=NotificationType.ride_cancelled,
                        title="Ride cancelled",
                        body=f"{ride.origin} to {ride.destination} has been cancelled by the driver.",
                    )
            self.rides.save(ride)
            self.rides.db.commit()
            self.audit_logs.record(
                action="ride_cancelled",
                actor_user_id=current_user.id,
                entity_type="ride",
                entity_id=str(ride.id),
            )
        except Exception:
            self.rides.db.rollback()
            raise

    def complete_ride(self, ride_id: int, current_user: User) -> Ride:
        if current_user.role != UserRole.driver:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only driver accounts can complete rides",
            )

        try:
            ride = self.rides.get_by_id_for_update(ride_id)
            if not ride:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")
            if ride.driver_id != current_user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only driver can complete this ride")
            if ride.status == RideStatus.cancelled:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cancelled rides cannot be completed")
            if ride.status == RideStatus.completed:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ride is already completed")

            ride.status = RideStatus.completed
            ride.is_active = False
            for booking in ride.bookings:
                if booking.status == BookingStatus.accepted:
                    booking.status = BookingStatus.completed
                    enqueue_notification(
                        session_factory=self.notification_session_factory,
                        recipient_id=booking.passenger_id,
                        notification_type=NotificationType.booking_completed,
                        title="Trip completed",
                        body=f"Your trip from {ride.origin} to {ride.destination} has been marked completed.",
                    )
            saved_ride = self.rides.save(ride)
            self.rides.db.commit()
            self.audit_logs.record(
                action="ride_completed",
                actor_user_id=current_user.id,
                entity_type="ride",
                entity_id=str(saved_ride.id),
            )
            return saved_ride
        except Exception:
            self.rides.db.rollback()
            raise

    def list_driver_rides(
        self,
        current_user: User,
        *,
        ride_status: RideStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Ride]:
        if current_user.role != UserRole.driver:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only driver accounts can view published rides",
            )
        return self.rides.list_by_driver(current_user.id, status=ride_status, limit=limit, offset=offset)

    def update_location(self, ride_id: int, payload: RideLocationCreate, current_user: User) -> RideLocation:
        if current_user.role != UserRole.driver:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only driver accounts can update ride location")

        ride = self.rides.get_by_id(ride_id)
        if not ride:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")
        if ride.driver_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only driver can update this ride location")
        if ride.status in {RideStatus.cancelled, RideStatus.completed}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Location cannot be updated for completed or cancelled rides")
        if payload.speed_kmph is not None and payload.speed_kmph > settings.LOCATION_MAX_REPORTED_SPEED_KMPH:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reported speed is too high for ride tracking")
        self._validate_location_near_route(ride, payload)

        try:
            location = RideLocation(
                ride_id=ride.id,
                driver_id=current_user.id,
                latitude=payload.latitude,
                longitude=payload.longitude,
                heading=payload.heading,
                speed_kmph=payload.speed_kmph,
            )
            self.rides.db.add(location)
            self.rides.db.flush()
            self.rides.db.refresh(location)
            self.audit_logs.record(
                action="ride_location_updated",
                actor_user_id=current_user.id,
                entity_type="ride",
                entity_id=str(ride.id),
                metadata={"latitude": payload.latitude, "longitude": payload.longitude},
            )
            return self._decorate_location(location)
        except Exception:
            self.rides.db.rollback()
            raise

    def get_latest_location(self, ride_id: int, current_user: User) -> RideLocation:
        self._ensure_location_access(ride_id, current_user)

        location = self.rides.get_latest_location(ride_id)
        if not location:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride location not found")
        return self._decorate_location(location)

    def list_location_history(self, ride_id: int, current_user: User, *, limit: int = 50) -> list[RideLocation]:
        self._ensure_location_access(ride_id, current_user)
        return [self._decorate_location(location) for location in self.rides.list_locations(ride_id, limit=limit)]

    def get_location_access(self, ride_id: int, current_user: User) -> RideLocationAccessResponse:
        ride = self.rides.get_detail_by_id(ride_id)
        if not ride:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")

        tracking_starts_at: datetime | None = None
        tracking_ends_at: datetime | None = None

        if ride.departure_time:
            departure_time = self._aware_datetime(ride.departure_time)
            tracking_starts_at = departure_time - timedelta(minutes=settings.LOCATION_TRACKING_START_BEFORE_MINUTES)
            tracking_ends_at = departure_time + timedelta(minutes=settings.LOCATION_TRACKING_END_AFTER_MINUTES)

        if current_user.id == ride.driver_id:
            return RideLocationAccessResponse(
                ride_id=ride.id,
                can_track=True,
                reason=None,
                tracking_starts_at=tracking_starts_at,
                tracking_ends_at=tracking_ends_at,
            )

        has_booking = any(booking.passenger_id == current_user.id and booking.status == BookingStatus.accepted for booking in ride.bookings)
        if not has_booking:
            return RideLocationAccessResponse(
                ride_id=ride.id,
                can_track=False,
                reason="Location access denied",
                tracking_starts_at=tracking_starts_at,
                tracking_ends_at=tracking_ends_at,
            )

        now = datetime.now(timezone.utc)
        if tracking_starts_at is not None and tracking_ends_at is not None and (now < tracking_starts_at or now > tracking_ends_at):
            return RideLocationAccessResponse(
                ride_id=ride.id,
                can_track=False,
                reason="Location tracking is only available near ride time",
                tracking_starts_at=tracking_starts_at,
                tracking_ends_at=tracking_ends_at,
            )

        return RideLocationAccessResponse(
            ride_id=ride.id,
            can_track=True,
            reason=None,
            tracking_starts_at=tracking_starts_at,
            tracking_ends_at=tracking_ends_at,
        )

    def cleanup_old_locations(self, *, retention_days: int | None = None) -> int:
        days = retention_days if retention_days is not None else settings.LOCATION_RETENTION_DAYS
        if days < 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="retention_days must be greater than zero")
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        deleted = self.rides.delete_locations_older_than(cutoff)
        self.rides.db.commit()
        return deleted

    def _ensure_location_access(self, ride_id: int, current_user: User) -> Ride:
        ride = self.rides.get_detail_by_id(ride_id)
        if not ride:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")
        if current_user.id == ride.driver_id:
            return ride
        if any(
            booking.passenger_id == current_user.id and booking.status == BookingStatus.accepted
            for booking in ride.bookings
        ):
            now = datetime.now(timezone.utc)
            departure_time = self._aware_datetime(ride.departure_time)
            tracking_starts_at = departure_time - timedelta(minutes=settings.LOCATION_TRACKING_START_BEFORE_MINUTES)
            tracking_ends_at = departure_time + timedelta(minutes=settings.LOCATION_TRACKING_END_AFTER_MINUTES)
            if now < tracking_starts_at or now > tracking_ends_at:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Location tracking is only available near ride time",
                )
            return ride
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Location access denied")

    def _decorate_location(self, location: RideLocation) -> RideLocation:
        age_seconds = max(0, int((datetime.now(timezone.utc) - self._aware_datetime(location.created_at)).total_seconds()))
        location.age_seconds = age_seconds  # type: ignore[attr-defined]
        location.is_stale = age_seconds >= settings.LOCATION_STALE_AFTER_SECONDS  # type: ignore[attr-defined]
        return location

    def _validate_location_near_route(self, ride: Ride, payload: RideLocationCreate) -> None:
        route_coordinates = (
            ride.origin_latitude,
            ride.origin_longitude,
            ride.destination_latitude,
            ride.destination_longitude,
        )
        if any(value is None for value in route_coordinates):
            return

        origin_latitude = float(ride.origin_latitude)
        origin_longitude = float(ride.origin_longitude)
        destination_latitude = float(ride.destination_latitude)
        destination_longitude = float(ride.destination_longitude)
        distance_km = self._distance_to_route_segment_km(
            latitude=payload.latitude,
            longitude=payload.longitude,
            origin_latitude=origin_latitude,
            origin_longitude=origin_longitude,
            destination_latitude=destination_latitude,
            destination_longitude=destination_longitude,
        )
        if distance_km > settings.LOCATION_ROUTE_BUFFER_KM:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Location is too far from this ride route",
            )

    def _distance_to_route_segment_km(
        self,
        *,
        latitude: float,
        longitude: float,
        origin_latitude: float,
        origin_longitude: float,
        destination_latitude: float,
        destination_longitude: float,
    ) -> float:
        mean_latitude = radians((origin_latitude + destination_latitude + latitude) / 3)

        def project(point_latitude: float, point_longitude: float) -> tuple[float, float]:
            return (
                point_longitude * 111.32 * cos(mean_latitude),
                point_latitude * 110.574,
            )

        point_x, point_y = project(latitude, longitude)
        origin_x, origin_y = project(origin_latitude, origin_longitude)
        destination_x, destination_y = project(destination_latitude, destination_longitude)
        segment_x = destination_x - origin_x
        segment_y = destination_y - origin_y
        segment_length_squared = segment_x * segment_x + segment_y * segment_y
        if segment_length_squared == 0:
            return sqrt((point_x - origin_x) ** 2 + (point_y - origin_y) ** 2)

        projection = ((point_x - origin_x) * segment_x + (point_y - origin_y) * segment_y) / segment_length_squared
        clamped_projection = max(0.0, min(1.0, projection))
        closest_x = origin_x + clamped_projection * segment_x
        closest_y = origin_y + clamped_projection * segment_y
        return sqrt((point_x - closest_x) ** 2 + (point_y - closest_y) ** 2)

    def _aware_datetime(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def _ensure_verified_driver(self, current_user: User) -> None:
        if current_user.driver_verification_status != DriverVerificationStatus.verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Driver verification is required before publishing rides",
            )
