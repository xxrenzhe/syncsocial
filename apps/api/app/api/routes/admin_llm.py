from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.deps import get_db, require_admin
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.llm_config import UpsertWorkspaceLlmConfigRequest, WorkspaceLlmConfigPublic
from app.services.llm_gateway import get_workspace_llm_config, upsert_workspace_llm_config

router = APIRouter()


def _require_encryption_key() -> None:
    if settings.credential_encryption_key is None or not settings.credential_encryption_key.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CREDENTIAL_ENCRYPTION_KEY is required")


@router.get("/llm-config", response_model=WorkspaceLlmConfigPublic | None)
def get_llm_config(
    admin: Annotated[User, Depends(require_admin)],
    db: Session = Depends(get_db),
) -> WorkspaceLlmConfigPublic | None:
    row = get_workspace_llm_config(db, workspace_id=admin.workspace_id)
    if row is None:
        return None
    return WorkspaceLlmConfigPublic.model_validate(
        {
            "id": row.id,
            "workspace_id": row.workspace_id,
            "provider": row.provider,
            "base_url": row.base_url,
            "model": row.model,
            "has_api_key": True,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


@router.put("/llm-config", response_model=WorkspaceLlmConfigPublic)
def upsert_llm_config(
    payload: UpsertWorkspaceLlmConfigRequest,
    admin: Annotated[User, Depends(require_admin)],
    db: Session = Depends(get_db),
) -> WorkspaceLlmConfigPublic:
    _require_encryption_key()

    provider = payload.provider.strip().lower()
    if provider != "openai":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only openai is supported currently")

    row = upsert_workspace_llm_config(
        db,
        workspace_id=admin.workspace_id,
        provider=provider,
        api_key=payload.api_key,
        base_url=payload.base_url,
        model=payload.model,
    )
    db.add(
        AuditLog(
            workspace_id=admin.workspace_id,
            actor_user_id=admin.id,
            action="admin.llm_config.upsert",
            target_type="workspace_llm_config",
            target_id=row.id,
            metadata_={
                "provider": row.provider,
                "base_url": row.base_url,
                "model": row.model,
                "has_api_key": True,
            },
        )
    )
    db.commit()
    db.refresh(row)

    return WorkspaceLlmConfigPublic.model_validate(
        {
            "id": row.id,
            "workspace_id": row.workspace_id,
            "provider": row.provider,
            "base_url": row.base_url,
            "model": row.model,
            "has_api_key": True,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )
