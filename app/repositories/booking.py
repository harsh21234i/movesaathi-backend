from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.booking import Booking


class BookingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, booking_id: int) -> Booking | None:
        return self.db.get(Booking, booking_id)

    def get_by_ride_and_passenger(self, ride_id: int, passenger_id: int) -> Booking | None:
        stmt = select(Booking).where(Booking.ride_id == ride_id, Booking.passenger_id == passenger_id)
        return self.db.scalar(stmt)

    def create(self, booking: Booking) -> Booking:
        self.db.add(booking)
        self.db.flush()
        self.db.refresh(booking)
        return booking

    def save(self, booking: Booking) -> Booking:
        self.db.add(booking)
        self.db.flush()
        self.db.refresh(booking)
        return booking
