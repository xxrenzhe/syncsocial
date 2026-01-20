from __future__ import annotations

from app.platforms.base import PlatformLoginAdapter


class RedditLoginAdapter(PlatformLoginAdapter):
    @property
    def platform_key(self) -> str:
        return "reddit"

    def get_login_url(self) -> str:
        return "https://www.reddit.com/login/"

    def get_cookie_origin(self) -> str:
        return "https://www.reddit.com"

    def is_logged_in(self, *, cookies: list[dict]) -> bool:
        cookie_names = {str(item.get("name")) for item in cookies}
        return "reddit_session" in cookie_names or "token_v2" in cookie_names

