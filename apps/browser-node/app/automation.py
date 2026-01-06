from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Literal

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ActionStatus = Literal["succeeded", "failed", "skipped"]
BandwidthMode = Literal["eco", "balanced", "full"]


@dataclass(frozen=True)
class ExecuteActionResult:
    status: ActionStatus
    error_code: str | None
    message: str | None
    current_url: str | None
    screenshot_base64: str | None
    metadata: dict[str, Any]


def execute_action(
    *,
    platform_key: str,
    action_type: str,
    storage_state: dict[str, Any],
    target_url: str | None,
    target_external_id: str | None,
    bandwidth_mode: BandwidthMode | None,
    headless: bool,
) -> ExecuteActionResult:
    platform = platform_key.strip().lower()
    action = action_type.strip().lower()

    if platform != "x":
        return ExecuteActionResult(
            status="failed",
            error_code="UNSUPPORTED_PLATFORM",
            message=f"Unsupported platform: {platform_key}",
            current_url=None,
            screenshot_base64=None,
            metadata={},
        )

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=storage_state)
            _install_bandwidth_mode(context, bandwidth_mode)
            page = context.new_page()
            page.set_default_timeout(15_000)
            page.set_default_navigation_timeout(30_000)

            try:
                if action in {"health_check", "x_health_check"}:
                    return _x_health_check(page)
                if action in {"x_like", "like"}:
                    return _x_like(page, target_url=target_url, tweet_id=target_external_id)
                if action in {"x_repost", "x_retweet", "retweet", "repost"}:
                    return _x_repost(page, target_url=target_url, tweet_id=target_external_id)
                return ExecuteActionResult(
                    status="failed",
                    error_code="UNSUPPORTED_ACTION",
                    message=f"Unsupported action_type: {action_type}",
                    current_url=None,
                    screenshot_base64=None,
                    metadata={},
                )
            finally:
                try:
                    context.close()
                finally:
                    browser.close()
    except PlaywrightTimeoutError:
        return ExecuteActionResult(
            status="failed",
            error_code="NETWORK_TIMEOUT",
            message="Playwright timeout",
            current_url=None,
            screenshot_base64=None,
            metadata={},
        )
    except PlaywrightError as exc:
        return ExecuteActionResult(
            status="failed",
            error_code="BROWSER_ERROR",
            message=str(exc),
            current_url=None,
            screenshot_base64=None,
            metadata={},
        )
    except Exception as exc:
        return ExecuteActionResult(
            status="failed",
            error_code="INTERNAL_ERROR",
            message=str(exc),
            current_url=None,
            screenshot_base64=None,
            metadata={},
        )


def execute_actions_batch(
    *,
    platform_key: str,
    actions: list[dict[str, Any]],
    storage_state: dict[str, Any],
    bandwidth_mode: BandwidthMode | None,
    headless: bool,
) -> list[ExecuteActionResult]:
    platform = platform_key.strip().lower()
    if platform != "x":
        return [
            ExecuteActionResult(
                status="failed",
                error_code="UNSUPPORTED_PLATFORM",
                message=f"Unsupported platform: {platform_key}",
                current_url=None,
                screenshot_base64=None,
                metadata={},
            )
            for _ in actions
        ]

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=storage_state)
            _install_bandwidth_mode(context, bandwidth_mode)
            page = context.new_page()
            page.set_default_timeout(15_000)
            page.set_default_navigation_timeout(30_000)

            results: list[ExecuteActionResult] = []
            aborted = False
            for item in actions:
                if aborted:
                    results.append(
                        ExecuteActionResult(
                            status="failed",
                            error_code="ABORTED",
                            message="Previous action failed",
                            current_url=str(getattr(page, "url", "")) or None,
                            screenshot_base64=None,
                            metadata={},
                        )
                    )
                    continue

                action_type = str(item.get("action_type") or "")
                target_url = str(item.get("target_url")) if item.get("target_url") else None
                target_external_id = str(item.get("target_external_id")) if item.get("target_external_id") else None
                try:
                    res = _execute_action_on_page(
                        page,
                        action_type=action_type,
                        target_url=target_url,
                        target_external_id=target_external_id,
                    )
                except PlaywrightTimeoutError:
                    res = ExecuteActionResult(
                        status="failed",
                        error_code="NETWORK_TIMEOUT",
                        message="Playwright timeout",
                        current_url=str(getattr(page, "url", "")) or None,
                        screenshot_base64=_safe_screenshot(page),
                        metadata={},
                    )
                except PlaywrightError as exc:
                    res = ExecuteActionResult(
                        status="failed",
                        error_code="BROWSER_ERROR",
                        message=str(exc),
                        current_url=str(getattr(page, "url", "")) or None,
                        screenshot_base64=_safe_screenshot(page),
                        metadata={},
                    )
                except Exception as exc:
                    res = ExecuteActionResult(
                        status="failed",
                        error_code="INTERNAL_ERROR",
                        message=str(exc),
                        current_url=str(getattr(page, "url", "")) or None,
                        screenshot_base64=_safe_screenshot(page),
                        metadata={},
                    )

                results.append(res)
                if res.status == "failed":
                    aborted = True

            try:
                context.close()
            finally:
                browser.close()

            return results
    except Exception as exc:
        return [
            ExecuteActionResult(
                status="failed",
                error_code="BROWSER_ERROR",
                message=str(exc),
                current_url=None,
                screenshot_base64=None,
                metadata={},
            )
            for _ in actions
        ]


def _install_bandwidth_mode(context: Any, mode: BandwidthMode | None) -> None:
    if mode is None:
        return
    normalized = str(mode).strip().lower()
    if normalized not in {"eco", "balanced"}:
        return

    def handle_route(route: Any, request: Any) -> None:  # Playwright types are runtime-heavy to import.
        resource_type = getattr(request, "resource_type", "")
        url = str(getattr(request, "url", ""))

        if normalized == "eco":
            if resource_type in {"image", "media"}:
                route.abort()
                return
        if normalized == "balanced":
            if resource_type == "media":
                route.abort()
                return

        if "doubleclick.net" in url or "google-analytics.com" in url:
            route.abort()
            return

        route.continue_()

    context.route("**/*", handle_route)


def _execute_action_on_page(
    page: Any,
    *,
    action_type: str,
    target_url: str | None,
    target_external_id: str | None,
) -> ExecuteActionResult:
    action = str(action_type).strip().lower()
    if action in {"health_check", "x_health_check"}:
        return _x_health_check(page)
    if action in {"x_like", "like"}:
        return _x_like(page, target_url=target_url, tweet_id=target_external_id)
    if action in {"x_repost", "x_retweet", "retweet", "repost"}:
        return _x_repost(page, target_url=target_url, tweet_id=target_external_id)
    return ExecuteActionResult(
        status="failed",
        error_code="UNSUPPORTED_ACTION",
        message=f"Unsupported action_type: {action_type}",
        current_url=str(getattr(page, "url", "")) or None,
        screenshot_base64=_safe_screenshot(page),
        metadata={},
    )


def _x_health_check(page: Any) -> ExecuteActionResult:
    page.goto("https://x.com/home", wait_until="domcontentloaded")
    logged_in = _x_is_logged_in(page)
    if logged_in:
        return ExecuteActionResult(
            status="succeeded",
            error_code=None,
            message=None,
            current_url=str(page.url),
            screenshot_base64=None,
            metadata={"logged_in": True},
        )

    screenshot = _safe_screenshot(page)
    return ExecuteActionResult(
        status="failed",
        error_code="AUTH_REQUIRED",
        message="Not logged in",
        current_url=str(page.url),
        screenshot_base64=screenshot,
        metadata={"logged_in": False},
    )


def _x_is_logged_in(page: Any) -> bool:
    url = str(getattr(page, "url", ""))
    if "/i/flow/login" in url or "/login" in url:
        return False

    try:
        if page.locator("[data-testid='loginButton']").count() > 0:
            return False
        if page.locator("a[href='/login'], a[href*='/i/flow/login']").count() > 0:
            return False
    except Exception:
        pass

    for selector in [
        "[data-testid='SideNav_NewTweet_Button']",
        "[data-testid='AppTabBar_Profile_Link']",
    ]:
        try:
            page.wait_for_selector(selector, timeout=2_500)
            return True
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue
    return False


def _x_like(page: Any, *, target_url: str | None, tweet_id: str | None) -> ExecuteActionResult:
    if target_url is None or not str(target_url).strip():
        return ExecuteActionResult(
            status="failed",
            error_code="INVALID_TARGET",
            message="target_url is required for x_like",
            current_url=None,
            screenshot_base64=None,
            metadata={},
        )

    page.goto(str(target_url), wait_until="domcontentloaded")

    if not _x_is_logged_in(page):
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="AUTH_REQUIRED",
            message="Not logged in",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={"logged_in": False},
        )

    try:
        if tweet_id and str(tweet_id).strip():
            article = page.locator("article").filter(has=page.locator(f'a[href*=\"/status/{tweet_id}\"]')).first
        else:
            article = page.locator("article").first
        article.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_SELECTOR_CHANGED",
            message="Tweet article not found",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )

    if article.locator('button[data-testid="unlike"]').count() > 0:
        return ExecuteActionResult(
            status="skipped",
            error_code=None,
            message="Already liked",
            current_url=str(page.url),
            screenshot_base64=None,
            metadata={"already_liked": True},
        )

    try:
        like_button = article.locator('button[data-testid="like"]').first
        like_button.wait_for(state="visible", timeout=10_000)
        like_button.scroll_into_view_if_needed(timeout=5_000)
        like_button.click(timeout=5_000)
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_INTERCEPTED",
            message="Like button not clickable",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )
    except PlaywrightError as exc:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="BROWSER_ERROR",
            message=str(exc),
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )

    try:
        article.locator('button[data-testid="unlike"]').first.wait_for(state="visible", timeout=5_000)
        return ExecuteActionResult(
            status="succeeded",
            error_code=None,
            message=None,
            current_url=str(page.url),
            screenshot_base64=None,
            metadata={"already_liked": False},
        )
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="POST_VALIDATION_FAILED",
            message="Like action not confirmed (unlike not visible)",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={"already_liked": False},
        )


def _x_repost(page: Any, *, target_url: str | None, tweet_id: str | None) -> ExecuteActionResult:
    if target_url is None or not str(target_url).strip():
        return ExecuteActionResult(
            status="failed",
            error_code="INVALID_TARGET",
            message="target_url is required for x_repost",
            current_url=None,
            screenshot_base64=None,
            metadata={},
        )

    page.goto(str(target_url), wait_until="domcontentloaded")

    if not _x_is_logged_in(page):
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="AUTH_REQUIRED",
            message="Not logged in",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={"logged_in": False},
        )

    try:
        if tweet_id and str(tweet_id).strip():
            article = page.locator("article").filter(has=page.locator(f'a[href*=\"/status/{tweet_id}\"]')).first
        else:
            article = page.locator("article").first
        article.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_SELECTOR_CHANGED",
            message="Tweet article not found",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )

    if article.locator('button[data-testid="unretweet"]').count() > 0:
        return ExecuteActionResult(
            status="skipped",
            error_code=None,
            message="Already reposted",
            current_url=str(page.url),
            screenshot_base64=None,
            metadata={"already_reposted": True},
        )

    try:
        repost_button = article.locator('button[data-testid="retweet"]').first
        repost_button.wait_for(state="visible", timeout=10_000)
        repost_button.scroll_into_view_if_needed(timeout=5_000)
        repost_button.click(timeout=5_000)
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_INTERCEPTED",
            message="Repost button not clickable",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )
    except PlaywrightError as exc:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="BROWSER_ERROR",
            message=str(exc),
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )

    try:
        confirm = page.locator('[data-testid="retweetConfirm"]').first
        confirm.wait_for(state="visible", timeout=5_000)
        confirm.click(timeout=5_000)
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_SELECTOR_CHANGED",
            message="Repost confirm not found",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )
    except PlaywrightError as exc:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="BROWSER_ERROR",
            message=str(exc),
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )

    try:
        article.locator('button[data-testid="unretweet"]').first.wait_for(state="visible", timeout=5_000)
        return ExecuteActionResult(
            status="succeeded",
            error_code=None,
            message=None,
            current_url=str(page.url),
            screenshot_base64=None,
            metadata={"already_reposted": False},
        )
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="POST_VALIDATION_FAILED",
            message="Repost action not confirmed (unretweet not visible)",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={"already_reposted": False},
        )


def _safe_screenshot(page: Any) -> str | None:
    try:
        png = page.screenshot(type="png", full_page=False)
        return base64.b64encode(png).decode("ascii")
    except Exception:
        return None
