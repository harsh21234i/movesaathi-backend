from datetime import datetime, timezone

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session, joinedload

from app.models.dispatch import DriverAvailability, DriverRequestDismissal, RideRequest, RideRequestStatus


class DispatchRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_driver_availability(self, driver_id: int) -> DriverAvailability | None:
        stmt = select(DriverAvailability).where(DriverAvailability.driver_id == driver_id)
        return self.db.scalar(stmt)

    def upsert_driver_availability(self, availability: DriverAvailability) -> DriverAvailability:
        self.db.add(availability)
        self.db.flush()
        self.db.refresh(availability)
        return availability

    def touch_driver_availability(self, driver_id: int) -> DriverAvailability | None:
        availability = self.get_driver_availability(driver_id)
        if not availability:
            return None
        availability.updated_at = datetime.now(timezone.utc)
        self.db.add(availability)
        self.db.flush()
        self.db.refresh(availability)
        return availability

    def create_ride_request(self, ride_request: RideRequest) -> RideRequest:
        self.db.add(ride_request)
        self.db.flush()
        self.db.refresh(ride_request)
        return ride_request

    def save_ride_request(self, ride_request: RideRequest) -> RideRequest:
        self.db.add(ride_request)
        self.db.flush()
        self.db.refresh(ride_request)
        return ride_request

    def get_ride_request(self, request_id: int) -> RideRequest | None:
        stmt = (
            select(RideRequest)
            .options(joinedload(RideRequest.passenger), joinedload(RideRequest.matched_driver))
            .where(RideRequest.id == request_id)
        )
        return self.db.scalar(stmt)

    def get_ride_request_for_update(self, request_id: int) -> RideRequest | None:
        stmt = select(RideRequest).where(RideRequest.id == request_id).with_for_update()
        return self.db.scalar(stmt)

    def get_open_request_for_passenger(self, passenger_id: int) -> RideRequest | None:
        stmt = (
            select(RideRequest)
            .where(
                RideRequest.passenger_id == passenger_id,
                RideRequest.status == RideRequestStatus.open,
            )
            .order_by(desc(RideRequest.created_at))
            .limit(1)
        )
        return self.db.scalar(stmt)

    def list_by_passenger(
        self,
        passenger_id: int,
        *,
        status: RideRequestStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[RideRequest]:
        stmt = (
            select(RideRequest)
            .options(joinedload(RideRequest.matched_driver), joinedload(RideRequest.passenger))
            .where(RideRequest.passenger_id == passenger_id)
            .order_by(desc(RideRequest.created_at))
            .offset(offset)
            .limit(limit)
        )
        if status:
            stmt = stmt.where(RideRequest.status == status)
        return list(self.db.scalars(stmt).unique().all())

    def list_open_requests(
        self,
        *,
        driver_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RideRequest]:
        stmt = (
            select(RideRequest)
            .options(joinedload(RideRequest.passenger))
            .where(RideRequest.status == RideRequestStatus.open)
            .order_by(desc(RideRequest.created_at))
            .offset(offset)
            .limit(limit)
        )
        if driver_id is not None:
            dismissed_ids_stmt = select(DriverRequestDismissal.request_id).where(DriverRequestDismissal.driver_id == driver_id)
            stmt = stmt.where(~RideRequest.id.in_(dismissed_ids_stmt))
        return list(self.db.scalars(stmt).unique().all())

    def list_expirable_open_requests(self, *, before: datetime, limit: int = 500) -> list[RideRequest]:
        stmt = (
            select(RideRequest)
            .options(joinedload(RideRequest.passenger))
            .where(
                RideRequest.status == RideRequestStatus.open,
                RideRequest.requested_departure_time < before,
            )
            .order_by(desc(RideRequest.requested_departure_time))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).unique().all())

    def create_driver_request_dismissal(self, dismissal: DriverRequestDismissal) -> DriverRequestDismissal:
        self.db.add(dismissal)
        self.db.flush()
        self.db.refresh(dismissal)
        return dismissal

    def get_driver_request_dismissal(self, driver_id: int, request_id: int) -> DriverRequestDismissal | None:
        stmt = select(DriverRequestDismissal).where(
            DriverRequestDismissal.driver_id == driver_id,
            DriverRequestDismissal.request_id == request_id,
        )
        return self.db.scalar(stmt)

    def delete_driver_request_dismissals_older_than(self, *, before: datetime) -> int:
        stmt = delete(DriverRequestDismissal).where(DriverRequestDismissal.dismissed_at < before)
        return self.db.execute(stmt).rowcount or 0

    def delete_driver_availability_older_than(self, *, before: datetime) -> int:
        stmt = delete(DriverAvailability).where(DriverAvailability.updated_at < before)
        return self.db.execute(stmt).rowcount or 0
