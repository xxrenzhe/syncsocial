from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.models.user import User
from app.platforms.registry import list_supported_platforms
from app.schemas.platform import PlatformPublic

router = APIRouter()


@router.get("", response_model=list[PlatformPublic])
def list_platforms(user: User = Depends(get_current_user)) -> list[PlatformPublic]:
    return [PlatformPublic.model_validate(item) for item in list_supported_platforms()]

