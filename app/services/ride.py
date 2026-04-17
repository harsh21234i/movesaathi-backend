from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.ride import Ride
from app.models.booking import BookingStatus
from app.models.user import User, UserRole
from app.repositories.ride import RideRepository
from app.schemas.ride import RideCreate, RideSearchParams, RideUpdate


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
            ride.is_active = payload.available_seats > 0
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

            ride.is_active = False
            self.rides.save(ride)
            self.rides.db.commit()
        except Exception:
            self.rides.db.rollback()
            raise

    def list_driver_rides(self, current_user: User) -> list[Ride]:
        if current_user.role != UserRole.driver:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only driver accounts can view published rides",
            )
        return self.rides.list_by_driver(current_user.id)
