from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.repositories.booking import BookingRepository
from app.schemas.ai import (
    AIChatSuggestion,
    AIChatSuggestionRequest,
    AIChatSuggestionResponse,
    AIRideCreateAssistantRequest,
    AIRideCreateAssistantResponse,
    AIRideCreateDraft,
    AIRideSearchAssistantRequest,
    AIRideSearchAssistantResponse,
    AIRideSearchFilters,
)
from app.services.ai_provider import AIProvider, AIProviderError, MockAIProvider, get_ai_provider


class AIService:
    def __init__(self, db: Session | None = None, provider: AIProvider | None = None) -> None:
        self.db = db
        self.provider = provider or get_ai_provider()

    def create_ride_draft(self, payload: AIRideCreateAssistantRequest) -> AIRideCreateAssistantResponse:
        used_fallback = False
        provider = self.provider
        try:
            draft_payload = provider.create_ride_draft(
                prompt=payload.prompt,
                locale=payload.locale,
                timezone_name=payload.timezone,
            )
            draft = AIRideCreateDraft.model_validate(draft_payload)
        except (AIProviderError, RuntimeError, ValidationError):
            if not settings.AI_FALLBACK_TO_MOCK:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="AI assistant is temporarily unavailable",
                ) from None
            provider = MockAIProvider()
            draft = AIRideCreateDraft.model_validate(
                provider.create_ride_draft(
                    prompt=payload.prompt,
                    locale=payload.locale,
                    timezone_name=payload.timezone,
                )
            )
            used_fallback = True

        return AIRideCreateAssistantResponse(
            provider=provider.provider,
            model=provider.model,
            used_fallback=used_fallback,
            draft=draft,
        )

    def create_ride_search_filters(self, payload: AIRideSearchAssistantRequest) -> AIRideSearchAssistantResponse:
        used_fallback = False
        provider = self.provider
        try:
            filters_payload = provider.create_ride_search_filters(
                prompt=payload.prompt,
                locale=payload.locale,
                timezone_name=payload.timezone,
            )
            filters = AIRideSearchFilters.model_validate(filters_payload)
        except (AIProviderError, RuntimeError, ValidationError):
            if not settings.AI_FALLBACK_TO_MOCK:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="AI assistant is temporarily unavailable",
                ) from None
            provider = MockAIProvider()
            filters = AIRideSearchFilters.model_validate(
                provider.create_ride_search_filters(
                    prompt=payload.prompt,
                    locale=payload.locale,
                    timezone_name=payload.timezone,
                )
            )
            used_fallback = True

        return AIRideSearchAssistantResponse(
            provider=provider.provider,
            model=provider.model,
            used_fallback=used_fallback,
            filters=filters,
        )

    def suggest_chat_reply(self, payload: AIChatSuggestionRequest, current_user: User) -> AIChatSuggestionResponse:
        if self.db is None:
            raise RuntimeError("Database session is required for chat suggestions")

        booking = BookingRepository(self.db).get_by_id(payload.booking_id)
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

        if current_user.id == booking.ride.driver_id:
            sender_role = "driver"
        elif current_user.id == booking.passenger_id:
            sender_role = "passenger"
        else:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chat access denied")

        booking_context = {
            "booking_status": booking.status.value,
            "origin": booking.ride.origin,
            "destination": booking.ride.destination,
            "departure_time": booking.ride.departure_time.isoformat(),
            "vehicle_details": booking.ride.vehicle_details,
            "sender_role": sender_role,
        }
        booking_summary = (
            f"{booking.ride.origin} to {booking.ride.destination} "
            f"on {booking.ride.departure_time.isoformat()} ({booking.status.value})"
        )

        used_fallback = False
        provider = self.provider
        try:
            suggestion_payload = provider.suggest_chat_reply(
                intent=payload.intent,
                draft_message=payload.draft_message,
                sender_role=sender_role,
                booking_context=booking_context,
                locale=payload.locale,
            )
            suggestion = AIChatSuggestion.model_validate(suggestion_payload)
        except (AIProviderError, RuntimeError, ValidationError):
            if not settings.AI_FALLBACK_TO_MOCK:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="AI assistant is temporarily unavailable",
                ) from None
            provider = MockAIProvider()
            suggestion = AIChatSuggestion.model_validate(
                provider.suggest_chat_reply(
                    intent=payload.intent,
                    draft_message=payload.draft_message,
                    sender_role=sender_role,
                    booking_context=booking_context,
                    locale=payload.locale,
                )
            )
            used_fallback = True

        return AIChatSuggestionResponse(
            provider=provider.provider,
            model=provider.model,
            used_fallback=used_fallback,
            booking_summary=booking_summary,
            result=suggestion,
        )
