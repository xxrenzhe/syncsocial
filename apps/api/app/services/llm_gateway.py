from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_json, encrypt_json
from app.models.llm_config import WorkspaceLlmConfig


def get_workspace_llm_config(db: Session, *, workspace_id) -> WorkspaceLlmConfig | None:
    return db.scalar(select(WorkspaceLlmConfig).where(WorkspaceLlmConfig.workspace_id == workspace_id))


def upsert_workspace_llm_config(
    db: Session,
    *,
    workspace_id,
    provider: str,
    api_key: str,
    base_url: str | None,
    model: str | None,
) -> WorkspaceLlmConfig:
    row = get_workspace_llm_config(db, workspace_id=workspace_id)
    encrypted = encrypt_json({"api_key": api_key})

    if row is None:
        row = WorkspaceLlmConfig(
            workspace_id=workspace_id,
            provider=provider.strip().lower(),
            api_key_encrypted=encrypted,
            base_url=(base_url.strip() if isinstance(base_url, str) and base_url.strip() else None),
            model=(model.strip() if isinstance(model, str) and model.strip() else None),
        )
    else:
        row.provider = provider.strip().lower()
        row.api_key_encrypted = encrypted
        row.base_url = base_url.strip() if isinstance(base_url, str) and base_url.strip() else None
        row.model = model.strip() if isinstance(model, str) and model.strip() else None

    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def generate_text(
    db: Session,
    *,
    workspace_id,
    prompt: str,
    system: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    row = get_workspace_llm_config(db, workspace_id=workspace_id)
    if row is None:
        raise RuntimeError("LLM config not set")

    provider = str(row.provider or "").strip().lower()
    if provider != "openai":
        raise RuntimeError(f"Unsupported LLM provider: {provider}")

    secret = decrypt_json(row.api_key_encrypted)
    api_key = str(secret.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("LLM api_key missing")

    base_url = str(row.base_url or "https://api.openai.com/v1").rstrip("/")
    model = str(row.model or "gpt-4o-mini").strip()

    messages: list[dict[str, str]] = []
    if system and system.strip():
        messages.append({"role": "system", "content": system.strip()})
    messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {"model": model, "messages": messages}
    if temperature is not None:
        payload["temperature"] = float(temperature)
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)

    url = f"{base_url}/chat/completions"
    headers = {"authorization": f"Bearer {api_key}", "content-type": "application/json"}

    with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        res = client.post(url, headers=headers, json=payload)
        res.raise_for_status()
        data = res.json()

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("LLM response missing choices")
    msg = choices[0].get("message")
    if not isinstance(msg, dict):
        raise RuntimeError("LLM response missing message")
    content = msg.get("content")
    if not isinstance(content, str):
        raise RuntimeError("LLM response missing content")
    return content.strip()

