from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    key = settings.credential_encryption_key
    if key is None or not key.strip():
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY is not set")
    return Fernet(key.encode("utf-8"))


def encrypt_json(value: dict) -> bytes:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _fernet().encrypt(payload)


def decrypt_json(blob: bytes) -> dict:
    try:
        payload = _fernet().decrypt(blob)
    except InvalidToken as exc:
        raise RuntimeError("Failed to decrypt credential blob") from exc
    return json.loads(payload.decode("utf-8"))
