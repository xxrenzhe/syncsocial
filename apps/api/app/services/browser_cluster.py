from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import settings
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
            raise RuntimeError("Playwright is not installed; run pip install -r requirements.local.txt") from exc

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
        cookies = runtime.context.cookies(adapter.get_cookie_origin())
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

    def execute_action(
        self,
        *,
        platform_key: str,
        action_type: str,
        storage_state: dict,
        target_url: str | None = None,
        target_external_id: str | None = None,
        bandwidth_mode: str | None = None,
    ) -> dict:
        raise RuntimeError("Local browser cluster does not support action execution yet; use BROWSER_CLUSTER_MODE=remote")

    def execute_actions(
        self,
        *,
        platform_key: str,
        storage_state: dict,
        actions: list[dict],
        bandwidth_mode: str | None = None,
    ) -> list[dict]:
        raise RuntimeError("Local browser cluster does not support action execution yet; use BROWSER_CLUSTER_MODE=remote")


class RemoteBrowserCluster:
    def __init__(self, *, base_url: str, internal_token: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._internal_token = internal_token.strip() if internal_token and internal_token.strip() else None

    def _request_json(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{self._base_url}{path}"
        data = None
        headers = {"accept": "application/json"}
        if self._internal_token:
            headers["x-internal-token"] = self._internal_token
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["content-type"] = "application/json"

        req = Request(url=url, method=method.upper(), data=data, headers=headers)
        try:
            with urlopen(req, timeout=30) as resp:
                body = resp.read()
        except HTTPError as exc:
            raise RuntimeError(f"Browser node error: {exc.code} {exc.reason}") from exc
        except URLError as exc:
            raise RuntimeError(f"Browser node unreachable: {exc.reason}") from exc

        if not body:
            return {}
        return json.loads(body.decode("utf-8"))

    def start_login_session(self, *, login_session_id: uuid.UUID, platform_key: str) -> str | None:
        res = self._request_json(
            "POST",
            "/login-sessions",
            {"login_session_id": str(login_session_id), "platform_key": platform_key},
        )
        remote_url = res.get("remote_url")
        return str(remote_url) if remote_url else None

    def is_logged_in(self, *, login_session_id: uuid.UUID) -> bool:
        res = self._request_json("GET", f"/login-sessions/{login_session_id}/is-logged-in")
        return bool(res.get("logged_in"))

    def export_storage_state(self, *, login_session_id: uuid.UUID) -> dict:
        return self._request_json("GET", f"/login-sessions/{login_session_id}/storage-state")

    def stop_login_session(self, *, login_session_id: uuid.UUID) -> None:
        self._request_json("POST", f"/login-sessions/{login_session_id}/stop")

    def execute_action(
        self,
        *,
        platform_key: str,
        action_type: str,
        storage_state: dict,
        target_url: str | None = None,
        target_external_id: str | None = None,
        bandwidth_mode: str | None = None,
    ) -> dict:
        return self._request_json(
            "POST",
            "/automation/actions/execute",
            {
                "platform_key": platform_key,
                "action_type": action_type,
                "storage_state": storage_state,
                "target_url": target_url,
                "target_external_id": target_external_id,
                "bandwidth_mode": bandwidth_mode,
            },
        )

    def execute_actions(
        self,
        *,
        platform_key: str,
        storage_state: dict,
        actions: list[dict],
        bandwidth_mode: str | None = None,
    ) -> list[dict]:
        res = self._request_json(
            "POST",
            "/automation/actions/execute-batch",
            {
                "platform_key": platform_key,
                "storage_state": storage_state,
                "bandwidth_mode": bandwidth_mode,
                "actions": actions,
            },
        )
        results = res.get("results")
        if not isinstance(results, list):
            raise RuntimeError("Browser node returned invalid results")
        return results


if settings.browser_cluster_mode.strip().lower() == "remote":
    base_url = settings.browser_node_api_base_url
    if base_url is None or not base_url.strip():
        raise RuntimeError("BROWSER_NODE_API_BASE_URL is required when BROWSER_CLUSTER_MODE=remote")
    browser_cluster = RemoteBrowserCluster(base_url=base_url, internal_token=settings.browser_node_internal_token)
else:
    browser_cluster = LocalPlaywrightBrowserCluster()
