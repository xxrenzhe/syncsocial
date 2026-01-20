from __future__ import annotations

from app.platforms.base import PlatformLoginAdapter
from app.platforms.reddit import RedditLoginAdapter
from app.platforms.x import XLoginAdapter

_adapters: dict[str, PlatformLoginAdapter] = {adapter.platform_key: adapter for adapter in [XLoginAdapter(), RedditLoginAdapter()]}

_platform_meta: dict[str, dict] = {
    "x": {
        "display_name": "X（Twitter）",
        "capabilities": [
            "PUBLISH_POST",
            "PUBLISH_MEDIA",
            "ENGAGE_LIKE",
            "ENGAGE_COMMENT",
            "ENGAGE_REPOST",
            "ENGAGE_QUOTE",
            "TARGET_VERIFIED_ONLY",
            "SOURCE_KEYWORD_SEARCH",
            "SOURCE_FEED",
            "SOURCE_PROFILE",
            "SOURCE_COMMUNITY",
        ],
    },
    "reddit": {
        "display_name": "Reddit",
        "capabilities": [
            "PUBLISH_POST",
            "ENGAGE_LIKE",
            "ENGAGE_COMMENT",
            "SOURCE_COMMUNITY",
        ],
    },
}


def get_login_adapter(platform_key: str) -> PlatformLoginAdapter:
    key = platform_key.strip().lower()
    if key in _adapters:
        return _adapters[key]
    raise KeyError(f"Unsupported platform: {platform_key}")


def list_supported_platforms() -> list[dict]:
    items: list[dict] = []
    for key, adapter in _adapters.items():
        meta = _platform_meta.get(key) or {}
        items.append(
            {
                "platform_key": key,
                "display_name": str(meta.get("display_name") or key),
                "login_url": adapter.get_login_url(),
                "capabilities": list(meta.get("capabilities") or []),
            }
        )
    return items
