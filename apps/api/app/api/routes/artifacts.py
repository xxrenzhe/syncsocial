from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.deps import get_current_user, get_db
from app.models.artifact import Artifact
from app.models.user import User

router = APIRouter()


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(
    artifact_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    row = db.get(Artifact, artifact_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    base_dir = Path(settings.artifacts_dir).resolve()
    path = (base_dir / row.storage_key).resolve()
    if not path.is_relative_to(base_dir):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid artifact storage key")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact file missing")

    media_type = "application/octet-stream"
    if row.type == "screenshot" and path.suffix.lower() == ".png":
        media_type = "image/png"
    elif row.type == "dom" and path.suffix.lower() in {".html", ".htm"}:
        media_type = "text/html; charset=utf-8"
    elif path.suffix.lower() == ".json":
        media_type = "application/json; charset=utf-8"
    elif path.suffix.lower() in {".txt", ".log"}:
        media_type = "text/plain; charset=utf-8"
    elif path.suffix.lower() == ".zip":
        media_type = "application/zip"

    return FileResponse(path=str(path), media_type=media_type, filename=path.name)
