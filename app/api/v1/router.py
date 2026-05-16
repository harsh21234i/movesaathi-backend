from fastapi import APIRouter

from app.api.v1.endpoints import audit, auth, bookings, chat, notifications, payments, reviews, rides, support, users

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(support.router, prefix="/support", tags=["support"])
api_router.include_router(rides.router, prefix="/rides", tags=["rides"])
api_router.include_router(bookings.router, prefix="/bookings", tags=["bookings"])
api_router.include_router(payments.router, prefix="/payments", tags=["payments"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["reviews"])
