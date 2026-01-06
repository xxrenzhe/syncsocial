from __future__ import annotations

from app.platforms.base import PlatformLoginAdapter


class XLoginAdapter(PlatformLoginAdapter):
    @property
    def platform_key(self) -> str:
        return "x"

    def get_login_url(self) -> str:
        return "https://x.com/i/flow/login"

    def get_cookie_origin(self) -> str:
        return "https://x.com"

    def is_logged_in(self, *, cookies: list[dict]) -> bool:
        cookie_names = {str(item.get("name")) for item in cookies}
        return "auth_token" in cookie_names
