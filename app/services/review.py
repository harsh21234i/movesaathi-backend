from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.review import Review
from app.models.user import User
from app.repositories.booking import BookingRepository
from app.repositories.review import ReviewRepository
from app.repositories.user import UserRepository
from app.schemas.review import ReviewCreate


class ReviewService:
    def __init__(self, db: Session) -> None:
        self.bookings = BookingRepository(db)
        self.reviews = ReviewRepository(db)
        self.users = UserRepository(db)

    def create_review(self, payload: ReviewCreate, current_user: User) -> Review:
        booking = self.bookings.get_by_id(payload.booking_id)
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

        participant_ids = {booking.passenger_id, booking.ride.driver_id}
        if current_user.id not in participant_ids or payload.reviewee_id not in participant_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Review not allowed")

        try:
            review = self.reviews.create(
                Review(
                    reviewer_id=current_user.id,
                    reviewee_id=payload.reviewee_id,
                    booking_id=payload.booking_id,
                    rating=payload.rating,
                    comment=payload.comment,
                )
            )
            reviewee = self.users.get_by_id(payload.reviewee_id)
            if reviewee:
                reviewee.rating = self.reviews.get_average_rating(payload.reviewee_id)
                self.users.save(reviewee)
            self.reviews.db.commit()
            return review
        except Exception:
            self.reviews.db.rollback()
            raise
