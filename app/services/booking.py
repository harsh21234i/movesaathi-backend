from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus
from app.models.user import User
from app.repositories.booking import BookingRepository
from app.repositories.ride import RideRepository
from app.schemas.booking import BookingCreate


class BookingService:
    def __init__(self, db: Session) -> None:
        self.bookings = BookingRepository(db)
        self.rides = RideRepository(db)

    def create_booking(self, payload: BookingCreate, current_user: User) -> Booking:
        ride = self.rides.get_by_id(payload.ride_id)
        if not ride or not ride.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")
        if ride.driver_id == current_user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Driver cannot book own ride")
        if ride.available_seats < 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No seats available")
        for existing in ride.bookings:
            if existing.passenger_id == current_user.id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passenger already has a booking for this ride")

        booking = Booking(ride_id=payload.ride_id, passenger_id=current_user.id, notes=payload.notes)
        return self.bookings.create(booking)

    def update_status(self, booking_id: int, status_value: BookingStatus, current_user: User) -> Booking:
        booking = self.bookings.get_by_id(booking_id)
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
        if booking.ride.driver_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only driver can update booking")
        if booking.status != BookingStatus.pending:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending bookings can be updated")

        booking.status = status_value
        if status_value == BookingStatus.accepted and booking.ride.available_seats > 0:
            booking.ride.available_seats -= 1
            if booking.ride.available_seats == 0:
                booking.ride.is_active = False
        return self.bookings.save(booking)
