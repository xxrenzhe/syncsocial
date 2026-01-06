from __future__ import annotations


def login_url(platform_key: str) -> str:
    key = platform_key.strip().lower()
    if key == "x":
        return "https://x.com/i/flow/login"
    raise KeyError(f"Unsupported platform: {platform_key}")


def cookie_origin(platform_key: str) -> str:
    key = platform_key.strip().lower()
    if key == "x":
        return "https://x.com"
    raise KeyError(f"Unsupported platform: {platform_key}")


def is_logged_in(platform_key: str, *, cookies: list[dict]) -> bool:
    key = platform_key.strip().lower()
    if key == "x":
        cookie_names = {str(item.get("name")) for item in cookies}
        return "auth_token" in cookie_names
    raise KeyError(f"Unsupported platform: {platform_key}")

