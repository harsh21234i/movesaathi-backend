from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.rate_limit import rate_limit_dependency
from app.models.user import User, UserRole
from app.schemas.ai import (
    AIChatSuggestionRequest,
    AIChatSuggestionResponse,
    AIRideCreateAssistantRequest,
    AIRideCreateAssistantResponse,
)
from app.services.ai import AIService

router = APIRouter()


@router.post("/ride-create-assistant", response_model=AIRideCreateAssistantResponse)
def create_ride_assistant_draft(
    payload: AIRideCreateAssistantRequest,
    current_user: User = Depends(get_current_user),
    _: None = Depends(
        rate_limit_dependency(
            "ai-assistant",
            limit=lambda: settings.AI_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=lambda: settings.AI_RATE_LIMIT_WINDOW_SECONDS,
        )
    ),
) -> AIRideCreateAssistantResponse:
    if current_user.role != UserRole.driver:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only driver accounts can use the ride creation assistant",
        )
    return AIService().create_ride_draft(payload)


@router.post("/chat-suggestion", response_model=AIChatSuggestionResponse)
def suggest_chat_reply(
    payload: AIChatSuggestionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(
        rate_limit_dependency(
            "ai-assistant",
            limit=lambda: settings.AI_RATE_LIMIT_MAX_REQUESTS,
            window_seconds=lambda: settings.AI_RATE_LIMIT_WINDOW_SECONDS,
        )
    ),
) -> AIChatSuggestionResponse:
    return AIService(db).suggest_chat_reply(payload, current_user)
