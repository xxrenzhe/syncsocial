from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.automation import execute_action
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


class ExecuteActionRequest(BaseModel):
    platform_key: str = Field(min_length=1, max_length=32)
    action_type: str = Field(min_length=1, max_length=64)
    storage_state: dict
    target_url: str | None = Field(default=None, max_length=2000)
    target_external_id: str | None = Field(default=None, max_length=200)
    bandwidth_mode: str | None = Field(default=None, max_length=16)


class ExecuteActionResponse(BaseModel):
    status: str
    error_code: str | None = None
    message: str | None = None
    current_url: str | None = None
    screenshot_base64: str | None = None
    metadata: dict = Field(default_factory=dict)


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


@app.post("/automation/actions/execute", response_model=ExecuteActionResponse)
def execute_action_endpoint(payload: ExecuteActionRequest, _: None = Depends(require_internal_token)) -> ExecuteActionResponse:
    result = execute_action(
        platform_key=payload.platform_key,
        action_type=payload.action_type,
        storage_state=payload.storage_state,
        target_url=payload.target_url,
        target_external_id=payload.target_external_id,
        bandwidth_mode=payload.bandwidth_mode if payload.bandwidth_mode else None,
        headless=settings.headless,
    )
    return ExecuteActionResponse(
        status=result.status,
        error_code=result.error_code,
        message=result.message,
        current_url=result.current_url,
        screenshot_base64=result.screenshot_base64,
        metadata=result.metadata,
    )
