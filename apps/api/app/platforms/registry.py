from __future__ import annotations

from app.platforms.base import PlatformLoginAdapter
from app.platforms.x import XLoginAdapter

_adapters: dict[str, PlatformLoginAdapter] = {adapter.platform_key: adapter for adapter in [XLoginAdapter()]}


def get_login_adapter(platform_key: str) -> PlatformLoginAdapter:
    key = platform_key.strip().lower()
    if key in _adapters:
        return _adapters[key]
    raise KeyError(f"Unsupported platform: {platform_key}")

