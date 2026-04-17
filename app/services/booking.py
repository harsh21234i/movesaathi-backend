from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus
from app.models.user import User, UserRole
from app.repositories.booking import BookingRepository
from app.repositories.ride import RideRepository
from app.schemas.booking import BookingCreate


class BookingService:
    def __init__(self, db: Session) -> None:
        self.bookings = BookingRepository(db)
        self.rides = RideRepository(db)

    def create_booking(self, payload: BookingCreate, current_user: User) -> Booking:
        if current_user.role != UserRole.passenger:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only passenger accounts can book rides",
            )

        try:
            ride = self.rides.get_by_id_for_update(payload.ride_id)
            if not ride or not ride.is_active:
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
            self.bookings.db.commit()
            return saved_booking
        except Exception:
            self.bookings.db.rollback()
            raise

    def update_status(self, booking_id: int, status_value: BookingStatus, current_user: User) -> Booking:
        if current_user.role != UserRole.driver:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only driver accounts can manage booking requests",
            )

        try:
            booking = self.bookings.get_by_id(booking_id)
            if not booking:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
            if booking.ride.driver_id != current_user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only driver can update booking")
            if booking.status != BookingStatus.pending:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Only pending bookings can be updated",
                )

            booking.status = status_value
            if status_value == BookingStatus.accepted:
                if booking.ride.available_seats < 1:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No seats available")
                booking.ride.available_seats -= 1
                if booking.ride.available_seats == 0:
                    booking.ride.is_active = False
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
        return [
            {
                "label": "Booking requested",
                "tone": "done",
                "timestamp": created_at,
            },
            {
                "label": "Driver review",
                "tone": "current" if booking.status == BookingStatus.pending else "done",
                "timestamp": None if booking.status == BookingStatus.pending else created_at,
            },
            {
                "label": (
                    "Trip confirmed"
                    if booking.status == BookingStatus.accepted
                    else "Request declined"
                    if booking.status == BookingStatus.rejected
                    else "Awaiting decision"
                ),
                "tone": "upcoming" if booking.status == BookingStatus.pending else "current",
                "timestamp": None if booking.status == BookingStatus.pending else created_at,
            },
        ]
