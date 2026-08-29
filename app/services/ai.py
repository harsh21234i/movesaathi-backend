from fastapi import HTTPException, status
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.ai import (
    AIRideCreateAssistantRequest,
    AIRideCreateAssistantResponse,
    AIRideCreateDraft,
    AIRideSearchAssistantRequest,
    AIRideSearchAssistantResponse,
    AIRideSearchFilters,
)
from app.services.ai_provider import AIProvider, AIProviderError, MockAIProvider, get_ai_provider


class AIService:
    def __init__(self, provider: AIProvider | None = None) -> None:
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
