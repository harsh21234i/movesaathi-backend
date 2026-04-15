from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.review import Review


class ReviewRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, review: Review) -> Review:
        self.db.add(review)
        self.db.flush()
        self.db.refresh(review)
        return review

    def get_average_rating(self, user_id: int) -> float:
        stmt = select(func.avg(Review.rating)).where(Review.reviewee_id == user_id)
        return float(self.db.scalar(stmt) or 5.0)
