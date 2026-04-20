"""add persistence constraints and composite indexes

Revision ID: 20260420_0006
Revises: 20260420_0005
Create Date: 2026-04-20 17:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260420_0006"
down_revision = "20260420_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table("rides") as batch_op:
            batch_op.create_check_constraint(
                "ck_rides_available_seats_non_negative",
                "available_seats >= 0",
            )
            batch_op.create_check_constraint(
                "ck_rides_price_per_seat_non_negative",
                "price_per_seat >= 0",
            )
            batch_op.create_check_constraint(
                "ck_rides_origin_destination_distinct",
                "origin <> destination",
            )
    else:
        op.create_check_constraint(
            "ck_rides_available_seats_non_negative",
            "rides",
            "available_seats >= 0",
        )
        op.create_check_constraint(
            "ck_rides_price_per_seat_non_negative",
            "rides",
            "price_per_seat >= 0",
        )
        op.create_check_constraint(
            "ck_rides_origin_destination_distinct",
            "rides",
            "origin <> destination",
        )

    op.create_index(
        "ix_rides_driver_status_departure",
        "rides",
        ["driver_id", "status", "departure_time"],
        unique=False,
    )

    if is_sqlite:
        with op.batch_alter_table("bookings") as batch_op:
            batch_op.create_check_constraint(
                "ck_bookings_passenger_id_positive",
                "passenger_id > 0",
            )
    else:
        op.create_check_constraint(
            "ck_bookings_passenger_id_positive",
            "bookings",
            "passenger_id > 0",
        )

    op.create_index(
        "ix_bookings_passenger_status_created",
        "bookings",
        ["passenger_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_bookings_ride_status_created",
        "bookings",
        ["ride_id", "status", "created_at"],
        unique=False,
    )

    if is_sqlite:
        with op.batch_alter_table("reviews") as batch_op:
            batch_op.create_check_constraint(
                "ck_reviews_rating_range",
                "rating >= 1 AND rating <= 5",
            )
            batch_op.create_check_constraint(
                "ck_reviews_reviewer_reviewee_distinct",
                "reviewer_id <> reviewee_id",
            )
    else:
        op.create_check_constraint(
            "ck_reviews_rating_range",
            "reviews",
            "rating >= 1 AND rating <= 5",
        )
        op.create_check_constraint(
            "ck_reviews_reviewer_reviewee_distinct",
            "reviews",
            "reviewer_id <> reviewee_id",
        )

    op.create_index(
        "ix_notifications_recipient_read_created",
        "notifications",
        ["recipient_id", "is_read", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_recipient_read_created", table_name="notifications")

    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table("reviews") as batch_op:
            batch_op.drop_constraint("ck_reviews_reviewer_reviewee_distinct", type_="check")
            batch_op.drop_constraint("ck_reviews_rating_range", type_="check")
    else:
        op.drop_constraint("ck_reviews_reviewer_reviewee_distinct", "reviews", type_="check")
        op.drop_constraint("ck_reviews_rating_range", "reviews", type_="check")

    op.drop_index("ix_bookings_ride_status_created", table_name="bookings")
    op.drop_index("ix_bookings_passenger_status_created", table_name="bookings")
    if is_sqlite:
        with op.batch_alter_table("bookings") as batch_op:
            batch_op.drop_constraint("ck_bookings_passenger_id_positive", type_="check")
    else:
        op.drop_constraint("ck_bookings_passenger_id_positive", "bookings", type_="check")

    op.drop_index("ix_rides_driver_status_departure", table_name="rides")
    if is_sqlite:
        with op.batch_alter_table("rides") as batch_op:
            batch_op.drop_constraint("ck_rides_origin_destination_distinct", type_="check")
            batch_op.drop_constraint("ck_rides_price_per_seat_non_negative", type_="check")
            batch_op.drop_constraint("ck_rides_available_seats_non_negative", type_="check")
    else:
        op.drop_constraint("ck_rides_origin_destination_distinct", "rides", type_="check")
        op.drop_constraint("ck_rides_price_per_seat_non_negative", "rides", type_="check")
        op.drop_constraint("ck_rides_available_seats_non_negative", "rides", type_="check")
