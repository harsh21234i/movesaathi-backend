from conftest import TestingSessionLocal


def verify_driver_by_email(email: str) -> None:
    from app.models.user import DriverVerificationStatus
    from app.repositories.user import UserRepository

    db = TestingSessionLocal()
    try:
        user = UserRepository(db).get_by_email(email)
        assert user is not None
        user.driver_verification_status = DriverVerificationStatus.verified
        db.commit()
    finally:
        db.close()
