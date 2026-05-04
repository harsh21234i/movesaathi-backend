from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_user_id: int | None
    action: str
    entity_type: str | None
    entity_id: str | None
    severity: str
    request_id: str | None
    metadata_json: str | None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]


class AuditLogSummaryResponse(BaseModel):
    total: int
    by_action: dict[str, int]
    by_severity: dict[str, int]
    recent_items: list[AuditLogResponse]
