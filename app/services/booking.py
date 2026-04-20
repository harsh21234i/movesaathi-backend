from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus
from app.models.notification import NotificationType
from app.models.ride import RideStatus
from app.models.user import User, UserRole
from app.repositories.booking import BookingRepository
from app.repositories.ride import RideRepository
from app.schemas.booking import BookingCreate
from app.services.notification import NotificationService


class BookingService:
    def __init__(self, db: Session) -> None:
        self.bookings = BookingRepository(db)
        self.rides = RideRepository(db)
        self.notifications = NotificationService(db)

    def create_booking(self, payload: BookingCreate, current_user: User) -> Booking:
        if current_user.role != UserRole.passenger:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only passenger accounts can book rides",
            )

        try:
            ride = self.rides.get_by_id_for_update(payload.ride_id)
            if not ride or ride.status != RideStatus.scheduled or not ride.is_active:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")
            if ride.driver_id == current_user.id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Driver cannot book own ride")
            if ride.available_seats < 1:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No seats available")
            if self.bookings.get_by_ride_and_passenger(payload.ride_id, current_user.id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Passenger already has a booking for this ride",
                )

            booking = Booking(ride_id=payload.ride_id, passenger_id=current_user.id, notes=payload.notes)
            saved_booking = self.bookings.create(booking)
            self.notifications.create_notification(
                recipient_id=ride.driver_id,
                notification_type=NotificationType.booking_requested,
                title="New booking request",
                body=f"{current_user.full_name} requested a seat from {ride.origin} to {ride.destination}.",
            )
            self.bookings.db.commit()
            return saved_booking
        except Exception:
            self.bookings.db.rollback()
            raise

    def update_status(self, booking_id: int, status_value: BookingStatus, current_user: User) -> Booking:
        try:
            booking = self.bookings.get_by_id(booking_id)
            if not booking:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
            ride = booking.ride

            if current_user.id == ride.driver_id:
                self._apply_driver_transition(booking, status_value)
            elif current_user.id == booking.passenger_id:
                self._apply_passenger_transition(booking, status_value)
            else:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only booking participants can update booking")

            saved_booking = self.bookings.save(booking)
            self.bookings.db.commit()
            return saved_booking
        except Exception:
            self.bookings.db.rollback()
            raise

    def list_passenger_bookings(self, current_user: User) -> list[Booking]:
        if current_user.role != UserRole.passenger:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only passenger accounts can view passenger bookings",
            )
        return self.bookings.list_by_passenger(current_user.id)

    def list_driver_bookings(self, current_user: User) -> list[Booking]:
        if current_user.role != UserRole.driver:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only driver accounts can view booking requests",
            )
        return self.bookings.list_for_driver(current_user.id)

    def get_booking_detail(self, booking_id: int, current_user: User) -> Booking:
        booking = self.bookings.get_by_id(booking_id)
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

        allowed_ids = {booking.passenger_id, booking.ride.driver_id}
        if current_user.id not in allowed_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Booking access denied")

        ride = booking.ride
        accepted_bookings = [
            ride_booking
            for ride_booking in ride.bookings
            if ride_booking.status == BookingStatus.accepted
        ]
        ride.booked_passengers = len(accepted_bookings)  # type: ignore[attr-defined]
        ride.passengers = [ride_booking.passenger for ride_booking in accepted_bookings]  # type: ignore[attr-defined]
        ride.booking_id = booking.id if current_user.id == booking.passenger_id else None  # type: ignore[attr-defined]
        booking.driver = ride.driver  # type: ignore[attr-defined]
        booking.status_events = self._build_status_events(booking)  # type: ignore[attr-defined]
        return booking

    def _build_status_events(self, booking: Booking) -> list[dict[str, object]]:
        created_at = booking.created_at
        review_timestamp = created_at if booking.status != BookingStatus.pending else None
        final_label = "Awaiting decision"
        final_tone = "upcoming"
        final_timestamp = None

        if booking.status == BookingStatus.accepted:
            final_label = "Trip confirmed"
            final_tone = "current"
            final_timestamp = created_at
        elif booking.status == BookingStatus.rejected:
            final_label = "Request declined"
            final_tone = "critical"
            final_timestamp = created_at
        elif booking.status == BookingStatus.cancelled_by_passenger:
            final_label = "Cancelled by passenger"
            final_tone = "critical"
            final_timestamp = created_at
        elif booking.status == BookingStatus.cancelled_by_driver:
            final_label = "Cancelled by driver"
            final_tone = "critical"
            final_timestamp = created_at
        elif booking.status == BookingStatus.completed:
            final_label = "Trip completed"
            final_tone = "done"
            final_timestamp = created_at

        return [
            {
                "label": "Booking requested",
                "tone": "done",
                "timestamp": created_at,
            },
            {
                "label": "Driver review",
                "tone": "current" if booking.status == BookingStatus.pending else "done",
                "timestamp": review_timestamp,
            },
            {
                "label": final_label,
                "tone": final_tone,
                "timestamp": final_timestamp,
            },
        ]

    def _apply_driver_transition(self, booking: Booking, status_value: BookingStatus) -> None:
        if status_value == BookingStatus.accepted:
            if booking.status != BookingStatus.pending:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending bookings can be accepted")
            if booking.ride.available_seats < 1:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No seats available")
            booking.status = BookingStatus.accepted
            booking.ride.available_seats -= 1
            booking.ride.status = RideStatus.full if booking.ride.available_seats == 0 else RideStatus.scheduled
            booking.ride.is_active = booking.ride.status == RideStatus.scheduled
            self.notifications.create_notification(
                recipient_id=booking.passenger_id,
                notification_type=NotificationType.booking_accepted,
                title="Booking accepted",
                body=f"Your seat request from {booking.ride.origin} to {booking.ride.destination} was accepted.",
            )
            return

        if status_value == BookingStatus.rejected:
            if booking.status != BookingStatus.pending:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending bookings can be rejected")
            booking.status = BookingStatus.rejected
            self.notifications.create_notification(
                recipient_id=booking.passenger_id,
                notification_type=NotificationType.booking_rejected,
                title="Booking rejected",
                body=f"Your seat request from {booking.ride.origin} to {booking.ride.destination} was rejected.",
            )
            return

        if status_value == BookingStatus.cancelled_by_driver:
            if booking.status not in {BookingStatus.pending, BookingStatus.accepted}:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This booking can no longer be cancelled by the driver")
            if booking.status == BookingStatus.accepted:
                booking.ride.available_seats += 1
                booking.ride.status = RideStatus.scheduled
                booking.ride.is_active = True
            booking.status = BookingStatus.cancelled_by_driver
            self.notifications.create_notification(
                recipient_id=booking.passenger_id,
                notification_type=NotificationType.booking_cancelled,
                title="Booking cancelled",
                body=f"Your booking from {booking.ride.origin} to {booking.ride.destination} was cancelled by the driver.",
            )
            return

        if status_value == BookingStatus.completed:
            if booking.status != BookingStatus.accepted:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only accepted bookings can be completed")
            booking.status = BookingStatus.completed
            self.notifications.create_notification(
                recipient_id=booking.passenger_id,
                notification_type=NotificationType.booking_completed,
                title="Trip completed",
                body=f"Your trip from {booking.ride.origin} to {booking.ride.destination} is complete.",
            )
            return

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported booking transition for driver")

    def _apply_passenger_transition(self, booking: Booking, status_value: BookingStatus) -> None:
        if status_value != BookingStatus.cancelled_by_passenger:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Passengers can only cancel their own bookings",
            )
        if booking.status not in {BookingStatus.pending, BookingStatus.accepted}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This booking can no longer be cancelled")
        if booking.status == BookingStatus.accepted:
            booking.ride.available_seats += 1
            booking.ride.status = RideStatus.scheduled
            booking.ride.is_active = True
        booking.status = BookingStatus.cancelled_by_passenger
        self.notifications.create_notification(
            recipient_id=booking.ride.driver_id,
            notification_type=NotificationType.booking_cancelled,
            title="Booking cancelled",
            body=f"{booking.passenger.full_name} cancelled the booking from {booking.ride.origin} to {booking.ride.destination}.",
        )
