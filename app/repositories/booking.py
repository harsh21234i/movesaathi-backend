from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.booking import Booking
from app.models.ride import Ride


class BookingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, booking_id: int) -> Booking | None:
        stmt = (
            select(Booking)
            .options(joinedload(Booking.ride), joinedload(Booking.passenger))
            .where(Booking.id == booking_id)
        )
        return self.db.scalar(stmt)

    def get_by_ride_and_passenger(self, ride_id: int, passenger_id: int) -> Booking | None:
        stmt = select(Booking).where(Booking.ride_id == ride_id, Booking.passenger_id == passenger_id)
        return self.db.scalar(stmt)

    def list_by_passenger(self, passenger_id: int) -> list[Booking]:
        stmt = (
            select(Booking)
            .options(joinedload(Booking.ride))
            .where(Booking.passenger_id == passenger_id)
            .order_by(Booking.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def list_for_driver(self, driver_id: int) -> list[Booking]:
        stmt = (
            select(Booking)
            .join(Ride, Booking.ride_id == Ride.id)
            .options(joinedload(Booking.ride), joinedload(Booking.passenger))
            .where(Ride.driver_id == driver_id)
            .order_by(Booking.created_at.desc())
        )
        return list(self.db.scalars(stmt).unique().all())

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
