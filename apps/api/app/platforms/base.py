from __future__ import annotations

from abc import ABC, abstractmethod


class PlatformLoginAdapter(ABC):
    @property
    @abstractmethod
    def platform_key(self) -> str: ...

    @abstractmethod
    def get_login_url(self) -> str: ...

    @abstractmethod
    def get_cookie_origin(self) -> str: ...

    @abstractmethod
    def is_logged_in(self, *, cookies: list[dict]) -> bool: ...
