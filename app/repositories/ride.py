from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.booking import Booking
from app.models.ride import Ride, RideLocation, RideStatus


class RideRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, ride_id: int) -> Ride | None:
        return self.db.get(Ride, ride_id)

    def get_detail_by_id(self, ride_id: int) -> Ride | None:
        stmt = (
            select(Ride)
            .options(
                joinedload(Ride.driver),
                joinedload(Ride.bookings).joinedload(Booking.passenger),
            )
            .where(Ride.id == ride_id)
        )
        return self.db.execute(stmt).scalars().unique().first()

    def get_by_id_for_update(self, ride_id: int) -> Ride | None:
        stmt = (
            select(Ride)
            .options(selectinload(Ride.bookings))
            .where(Ride.id == ride_id)
            .with_for_update()
        )
        return self.db.scalar(stmt)

    def create(self, ride: Ride) -> Ride:
        self.db.add(ride)
        self.db.flush()
        self.db.refresh(ride)
        return ride

    def save(self, ride: Ride) -> Ride:
        self.db.add(ride)
        self.db.flush()
        self.db.refresh(ride)
        return ride

    def search(
        self,
        origin: str | None = None,
        destination: str | None = None,
        departure_after: datetime | None = None,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Ride]:
        stmt = select(Ride).where(Ride.status == RideStatus.scheduled, Ride.is_active.is_(True), Ride.available_seats > 0)
        if origin:
            stmt = stmt.where(Ride.origin.ilike(f"%{origin}%"))
        if destination:
            stmt = stmt.where(Ride.destination.ilike(f"%{destination}%"))
        if departure_after:
            stmt = stmt.where(Ride.departure_time >= departure_after)
        stmt = stmt.order_by(Ride.departure_time).offset(offset).limit(limit)
        return list(self.db.scalars(stmt).all())

    def list_by_driver(
        self,
        driver_id: int,
        *,
        status: RideStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Ride]:
        stmt = select(Ride).where(Ride.driver_id == driver_id)
        if status:
            stmt = stmt.where(Ride.status == status)
        stmt = stmt.order_by(Ride.departure_time).offset(offset).limit(limit)
        return list(self.db.scalars(stmt).all())

    def get_latest_location(self, ride_id: int) -> RideLocation | None:
        stmt = (
            select(RideLocation)
            .where(RideLocation.ride_id == ride_id)
            .order_by(desc(RideLocation.created_at), desc(RideLocation.id))
            .limit(1)
        )
        return self.db.scalar(stmt)

    def list_locations(self, ride_id: int, *, limit: int = 50) -> list[RideLocation]:
        stmt = (
            select(RideLocation)
            .where(RideLocation.ride_id == ride_id)
            .order_by(desc(RideLocation.created_at), desc(RideLocation.id))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def delete_locations_older_than(self, cutoff: datetime) -> int:
        deleted = (
            self.db.query(RideLocation)
            .filter(RideLocation.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        return int(deleted)
