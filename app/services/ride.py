from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.ride import Ride
from app.models.booking import BookingStatus
from app.models.notification import NotificationType
from app.models.ride import RideStatus
from app.models.user import User, UserRole
from app.repositories.ride import RideRepository
from app.schemas.ride import RideCreate, RideSearchParams, RideUpdate
from app.services.notification import NotificationService


class RideService:
    def __init__(self, db: Session) -> None:
        self.rides = RideRepository(db)
        self.notifications = NotificationService(db)

    def create_ride(self, payload: RideCreate, current_user: User) -> Ride:
        if current_user.role != UserRole.driver:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only driver accounts can publish rides",
            )

        try:
            ride = Ride(
                driver_id=current_user.id,
                origin=payload.origin,
                destination=payload.destination,
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
            ride.departure_time = payload.departure_time
            ride.available_seats = payload.available_seats
            ride.price_per_seat = payload.price_per_seat
            ride.vehicle_details = payload.vehicle_details
            ride.notes = payload.notes
            ride.status = RideStatus.full if payload.available_seats == 0 else RideStatus.scheduled
            ride.is_active = ride.status == RideStatus.scheduled
            saved_ride = self.rides.save(ride)
            self.rides.db.commit()
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
                    self.notifications.create_notification(
                        recipient_id=booking.passenger_id,
                        notification_type=NotificationType.ride_cancelled,
                        title="Ride cancelled",
                        body=f"{ride.origin} to {ride.destination} has been cancelled by the driver.",
                    )
            self.rides.save(ride)
            self.rides.db.commit()
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
                    self.notifications.create_notification(
                        recipient_id=booking.passenger_id,
                        notification_type=NotificationType.booking_completed,
                        title="Trip completed",
                        body=f"Your trip from {ride.origin} to {ride.destination} has been marked completed.",
                    )
            saved_ride = self.rides.save(ride)
            self.rides.db.commit()
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
