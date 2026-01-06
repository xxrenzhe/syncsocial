from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import settings
from app.platforms import cookie_origin, is_logged_in, login_url


@dataclass
class LoginRuntime:
    platform_key: str
    created_at: datetime
    playwright: object
    browser: object
    context: object
    page: object


class SessionManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[uuid.UUID, LoginRuntime] = {}

    def start_login(
        self, *, login_session_id: uuid.UUID, platform_key: str, fingerprint_profile: dict | None = None
    ) -> str | None:
        with self._lock:
            if login_session_id in self._sessions:
                return settings.novnc_public_url

        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=settings.headless)
        context_kwargs = _context_kwargs_from_fingerprint(fingerprint_profile or {})
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.goto(login_url(platform_key))

        runtime = LoginRuntime(
            platform_key=platform_key.strip().lower(),
            created_at=datetime.now(timezone.utc),
            playwright=pw,
            browser=browser,
            context=context,
            page=page,
        )

        with self._lock:
            self._sessions[login_session_id] = runtime
        return settings.novnc_public_url

    def get_logged_in(self, *, login_session_id: uuid.UUID) -> bool:
        with self._lock:
            runtime = self._sessions.get(login_session_id)
        if runtime is None:
            raise KeyError("Login session not found")
        cookies = runtime.context.cookies(cookie_origin(runtime.platform_key))
        return is_logged_in(runtime.platform_key, cookies=cookies)

    def export_storage_state(self, *, login_session_id: uuid.UUID) -> dict:
        with self._lock:
            runtime = self._sessions.get(login_session_id)
        if runtime is None:
            raise KeyError("Login session not found")
        return runtime.context.storage_state()

    def stop(self, *, login_session_id: uuid.UUID) -> None:
        with self._lock:
            runtime = self._sessions.pop(login_session_id, None)
        if runtime is None:
            return
        try:
            runtime.context.close()
        finally:
            try:
                runtime.browser.close()
            finally:
                runtime.playwright.stop()


session_manager = SessionManager()


def _context_kwargs_from_fingerprint(profile: dict) -> dict:
    if not isinstance(profile, dict) or not profile:
        return {}

    kwargs: dict = {}
    user_agent = profile.get("user_agent")
    if isinstance(user_agent, str) and user_agent.strip():
        kwargs["user_agent"] = user_agent.strip()

    viewport = profile.get("viewport")
    if isinstance(viewport, dict):
        width = viewport.get("width")
        height = viewport.get("height")
        if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
            kwargs["viewport"] = {"width": width, "height": height}

    locale = profile.get("locale")
    if isinstance(locale, str) and locale.strip():
        kwargs["locale"] = locale.strip()

    timezone_id = profile.get("timezone_id")
    if isinstance(timezone_id, str) and timezone_id.strip():
        kwargs["timezone_id"] = timezone_id.strip()

    color_scheme = profile.get("color_scheme")
    if isinstance(color_scheme, str) and color_scheme.strip():
        kwargs["color_scheme"] = color_scheme.strip()

    device_scale_factor = profile.get("device_scale_factor")
    if isinstance(device_scale_factor, (int, float)) and device_scale_factor > 0:
        kwargs["device_scale_factor"] = float(device_scale_factor)

    is_mobile = profile.get("is_mobile")
    if isinstance(is_mobile, bool):
        kwargs["is_mobile"] = is_mobile

    has_touch = profile.get("has_touch")
    if isinstance(has_touch, bool):
        kwargs["has_touch"] = has_touch

    return kwargs
