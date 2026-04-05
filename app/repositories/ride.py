from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ride import Ride


class RideRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, ride_id: int) -> Ride | None:
        return self.db.get(Ride, ride_id)

    def create(self, ride: Ride) -> Ride:
        self.db.add(ride)
        self.db.commit()
        self.db.refresh(ride)
        return ride

    def save(self, ride: Ride) -> Ride:
        self.db.add(ride)
        self.db.commit()
        self.db.refresh(ride)
        return ride

    def search(self, origin: str | None = None, destination: str | None = None, departure_after: datetime | None = None) -> list[Ride]:
        stmt = select(Ride).where(Ride.is_active.is_(True), Ride.available_seats > 0)
        if origin:
            stmt = stmt.where(Ride.origin.ilike(f"%{origin}%"))
        if destination:
            stmt = stmt.where(Ride.destination.ilike(f"%{destination}%"))
        if departure_after:
            stmt = stmt.where(Ride.departure_time >= departure_after)
        stmt = stmt.order_by(Ride.departure_time)
        return list(self.db.scalars(stmt).all())
