from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.ride import Ride
from app.models.user import User, UserRole
from app.repositories.ride import RideRepository
from app.schemas.ride import RideCreate, RideSearchParams


class RideService:
    def __init__(self, db: Session) -> None:
        self.rides = RideRepository(db)

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
        )

    def list_driver_rides(self, current_user: User) -> list[Ride]:
        if current_user.role != UserRole.driver:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only driver accounts can view published rides",
            )
        return self.rides.list_by_driver(current_user.id)
