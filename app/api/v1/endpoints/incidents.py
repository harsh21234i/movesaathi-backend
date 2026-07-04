from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.incident import IncidentCreate, IncidentListResponse, IncidentResponse
from app.services.incident import IncidentService

router = APIRouter()


@router.post("", response_model=IncidentResponse, status_code=201)
def create_incident(
    payload: IncidentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IncidentResponse:
    return IncidentService(db).create_incident(payload, current_user)


@router.get("", response_model=IncidentListResponse)
def list_my_incidents(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IncidentListResponse:
    return IncidentListResponse(
        items=IncidentService(db).list_my_incidents(current_user, limit=limit, offset=offset)
    )


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_my_incident(
    incident_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IncidentResponse:
    return IncidentService(db).get_my_incident(incident_id, current_user)
