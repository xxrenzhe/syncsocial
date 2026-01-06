from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.session_manager import session_manager

app = FastAPI(title="SyncSocial Browser Node", version="0.1.0")


def require_internal_token(x_internal_token: Annotated[str | None, Header()] = None) -> None:
    if x_internal_token != settings.internal_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


class CreateLoginSessionRequest(BaseModel):
    login_session_id: uuid.UUID
    platform_key: str = Field(min_length=1, max_length=32)


class CreateLoginSessionResponse(BaseModel):
    remote_url: str | None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/login-sessions", response_model=CreateLoginSessionResponse)
def create_login_session(payload: CreateLoginSessionRequest, _: None = Depends(require_internal_token)) -> CreateLoginSessionResponse:
    try:
        remote_url = session_manager.start_login(login_session_id=payload.login_session_id, platform_key=payload.platform_key)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return CreateLoginSessionResponse(remote_url=remote_url)


@app.get("/login-sessions/{login_session_id}/is-logged-in")
def is_logged_in_endpoint(login_session_id: uuid.UUID, _: None = Depends(require_internal_token)) -> dict:
    try:
        logged_in = session_manager.get_logged_in(login_session_id=login_session_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Login session not found") from None
    return {"logged_in": logged_in}


@app.get("/login-sessions/{login_session_id}/storage-state")
def storage_state_endpoint(login_session_id: uuid.UUID, _: None = Depends(require_internal_token)) -> dict:
    try:
        return session_manager.export_storage_state(login_session_id=login_session_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Login session not found") from None


@app.post("/login-sessions/{login_session_id}/stop")
def stop_session_endpoint(login_session_id: uuid.UUID, _: None = Depends(require_internal_token)) -> dict:
    session_manager.stop(login_session_id=login_session_id)
    return {"ok": True}

