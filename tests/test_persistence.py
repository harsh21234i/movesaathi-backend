from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.booking import Booking, BookingStatus
from app.models.review import Review
from app.models.ride import Ride, RideStatus
from app.models.user import User, UserRole


def test_ride_persistence_constraints_are_enforced(db_session) -> None:
    driver = User(
        full_name="Constraint Driver",
        email="constraint-driver@example.com",
        phone_number="9999999999",
        hashed_password="hashed",
        role=UserRole.driver,
    )
    db_session.add(driver)
    db_session.flush()

    invalid_ride = Ride(
        driver_id=driver.id,
        origin="Delhi",
        destination="Delhi",
        departure_time=datetime.now(timezone.utc),
        available_seats=-1,
        price_per_seat=-10,
        status=RideStatus.scheduled,
        is_active=True,
    )
    db_session.add(invalid_ride)

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_review_persistence_constraints_are_enforced(db_session) -> None:
    reviewer = User(
        full_name="Reviewer",
        email="reviewer@example.com",
        phone_number="9999999998",
        hashed_password="hashed",
        role=UserRole.passenger,
    )
    db_session.add(reviewer)
    driver = User(
        full_name="Review Driver",
        email="review-driver-constraint@example.com",
        phone_number="9999999997",
        hashed_password="hashed",
        role=UserRole.driver,
    )
    db_session.add(driver)
    db_session.flush()
    ride = Ride(
        driver_id=driver.id,
        origin="Pune",
        destination="Mumbai",
        departure_time=datetime.now(timezone.utc),
        available_seats=1,
        price_per_seat=300,
        status=RideStatus.completed,
        is_active=False,
    )
    db_session.add(ride)
    db_session.flush()
    booking = Booking(
        ride_id=ride.id,
        passenger_id=reviewer.id,
        status=BookingStatus.completed,
        notes=None,
    )
    db_session.add(booking)
    db_session.flush()

    invalid_review = Review(
        reviewer_id=reviewer.id,
        reviewee_id=reviewer.id,
        booking_id=booking.id,
        rating=6,
        comment="invalid review",
    )
    db_session.add(invalid_review)

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()
