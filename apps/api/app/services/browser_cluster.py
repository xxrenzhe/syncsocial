from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.platforms.registry import get_login_adapter


@dataclass
class LoginRuntime:
    platform_key: str
    created_at: datetime
    playwright: object
    browser: object
    context: object
    page: object


class LocalPlaywrightBrowserCluster:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[uuid.UUID, LoginRuntime] = {}

    def start_login_session(self, *, login_session_id: uuid.UUID, platform_key: str) -> str | None:
        adapter = get_login_adapter(platform_key)
        login_url = adapter.get_login_url()

        with self._lock:
            if login_session_id in self._sessions:
                return None

        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("Playwright is not installed; run pip install -r requirements.txt") from exc

        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(login_url)

        runtime = LoginRuntime(
            platform_key=adapter.platform_key,
            created_at=datetime.now(timezone.utc),
            playwright=playwright,
            browser=browser,
            context=context,
            page=page,
        )

        with self._lock:
            self._sessions[login_session_id] = runtime
        return None

    def is_logged_in(self, *, login_session_id: uuid.UUID) -> bool:
        with self._lock:
            runtime = self._sessions.get(login_session_id)
        if runtime is None:
            raise KeyError("Login session runtime not found")

        adapter = get_login_adapter(runtime.platform_key)
        cookies = runtime.context.cookies("https://x.com")
        return adapter.is_logged_in(cookies=cookies)

    def export_storage_state(self, *, login_session_id: uuid.UUID) -> dict:
        with self._lock:
            runtime = self._sessions.get(login_session_id)
        if runtime is None:
            raise KeyError("Login session runtime not found")
        return runtime.context.storage_state()

    def stop_login_session(self, *, login_session_id: uuid.UUID) -> None:
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


browser_cluster = LocalPlaywrightBrowserCluster()

