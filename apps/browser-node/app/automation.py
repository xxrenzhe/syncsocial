from __future__ import annotations

import base64
import random
import re
import time
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
    action_params: dict[str, Any] | None,
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
                if action in {"x_search_collect", "search_collect"}:
                    return _x_search_collect(page, search_url=target_url, params=action_params or {})
                if action in {"x_reply", "reply", "comment", "x_comment"}:
                    return _x_reply(page, target_url=target_url, tweet_id=target_external_id, params=action_params or {})
                if action in {"x_quote", "quote"}:
                    return _x_quote(page, target_url=target_url, tweet_id=target_external_id, params=action_params or {})
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
                action_params = item.get("action_params") if isinstance(item.get("action_params"), dict) else {}
                try:
                    res = _execute_action_on_page(
                        page,
                        action_type=action_type,
                        target_url=target_url,
                        target_external_id=target_external_id,
                        action_params=action_params,
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
    action_params: dict[str, Any],
) -> ExecuteActionResult:
    action = str(action_type).strip().lower()
    if action in {"health_check", "x_health_check"}:
        return _x_health_check(page)
    if action in {"x_like", "like"}:
        return _x_like(page, target_url=target_url, tweet_id=target_external_id)
    if action in {"x_repost", "x_retweet", "retweet", "repost"}:
        return _x_repost(page, target_url=target_url, tweet_id=target_external_id)
    if action in {"x_search_collect", "search_collect"}:
        return _x_search_collect(page, search_url=target_url, params=action_params)
    if action in {"x_reply", "reply", "comment", "x_comment"}:
        return _x_reply(page, target_url=target_url, tweet_id=target_external_id, params=action_params)
    if action in {"x_quote", "quote"}:
        return _x_quote(page, target_url=target_url, tweet_id=target_external_id, params=action_params)
    return ExecuteActionResult(
        status="failed",
        error_code="UNSUPPORTED_ACTION",
        message=f"Unsupported action_type: {action_type}",
        current_url=str(getattr(page, "url", "")) or None,
        screenshot_base64=_safe_screenshot(page),
        metadata={},
    )


def _x_search_collect(page: Any, *, search_url: str | None, params: dict[str, Any]) -> ExecuteActionResult:
    if search_url is None or not str(search_url).strip():
        return ExecuteActionResult(
            status="failed",
            error_code="INVALID_TARGET",
            message="target_url is required for x_search_collect",
            current_url=None,
            screenshot_base64=None,
            metadata={},
        )

    max_candidates = _get_int(params, "max_candidates", default=20, min_value=1, max_value=200)
    scroll_limit = _get_int(params, "scroll_limit", default=6, min_value=0, max_value=50)
    verified_only_dom = bool(params.get("verified_only_dom") is True)

    page.goto(str(search_url), wait_until="domcontentloaded")
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
        page.wait_for_selector("article", timeout=10_000)
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="skipped",
            error_code=None,
            message="No search results",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={"candidates": [], "collected": 0},
        )

    candidates_by_id: dict[str, dict[str, Any]] = {}

    for _ in range(scroll_limit + 1):
        articles = page.locator("article")
        count = articles.count()
        for idx in range(count):
            if len(candidates_by_id) >= max_candidates:
                break
            article = articles.nth(idx)
            href = article.locator("a[href*='/status/']").first.get_attribute("href")
            if not href:
                continue
            tweet_id = _extract_tweet_id_from_href(href)
            if not tweet_id or tweet_id in candidates_by_id:
                continue

            url = _normalize_x_url(href)
            is_verified = False
            try:
                is_verified = article.locator("[data-testid='icon-verified']").count() > 0
            except Exception:
                is_verified = False

            if verified_only_dom and not is_verified:
                continue

            candidates_by_id[tweet_id] = {
                "tweet_id": tweet_id,
                "url": url,
                "is_verified": is_verified,
            }

        if len(candidates_by_id) >= max_candidates:
            break

        page.mouse.wheel(0, random.randint(900, 1400))
        page.wait_for_timeout(random.randint(450, 900))

    candidates = list(candidates_by_id.values())
    if not candidates:
        return ExecuteActionResult(
            status="skipped",
            error_code=None,
            message="No candidates found",
            current_url=str(page.url),
            screenshot_base64=None,
            metadata={"candidates": [], "collected": 0},
        )

    return ExecuteActionResult(
        status="succeeded",
        error_code=None,
        message=None,
        current_url=str(page.url),
        screenshot_base64=None,
        metadata={"candidates": candidates, "collected": len(candidates)},
    )


def _extract_tweet_id_from_href(href: str) -> str | None:
    m = re.search(r"/status/(?P<tweet_id>\\d+)", href)
    if not m:
        return None
    return m.group("tweet_id")


def _normalize_x_url(href: str) -> str:
    raw = href.strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw.split("?", 1)[0]
    if raw.startswith("/"):
        return f"https://x.com{raw}".split("?", 1)[0]
    return f"https://x.com/{raw}".split("?", 1)[0]


def _get_int(source: dict[str, Any], key: str, *, default: int, min_value: int, max_value: int) -> int:
    value = source.get(key, default)
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    if parsed < min_value:
        return min_value
    if parsed > max_value:
        return max_value
    return parsed


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


def _x_reply(page: Any, *, target_url: str | None, tweet_id: str | None, params: dict[str, Any]) -> ExecuteActionResult:
    if target_url is None or not str(target_url).strip():
        return ExecuteActionResult(
            status="failed",
            error_code="INVALID_TARGET",
            message="target_url is required for x_reply",
            current_url=None,
            screenshot_base64=None,
            metadata={},
        )

    text = str(params.get("text") or "").strip()
    if not text:
        return ExecuteActionResult(
            status="failed",
            error_code="INVALID_PARAMS",
            message="action_params.text is required for x_reply",
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

    try:
        reply_button = article.locator('button[data-testid="reply"]').first
        reply_button.wait_for(state="visible", timeout=10_000)
        reply_button.scroll_into_view_if_needed(timeout=5_000)
        reply_button.click(timeout=5_000)
        page.wait_for_timeout(random.randint(900, 1600))
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_INTERCEPTED",
            message="Reply button not clickable",
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

    if _x_has_reply_restriction(page):
        _x_dismiss_reply_restriction(page)
        return ExecuteActionResult(
            status="skipped",
            error_code="REPLY_RESTRICTED",
            message="Reply restricted by author",
            current_url=str(page.url),
            screenshot_base64=None,
            metadata={},
        )

    dialog = page.locator("div[role='dialog'][aria-modal='true']").first
    scope = dialog if dialog.count() > 0 else page
    try:
        textarea = scope.locator("[data-testid='tweetTextarea_0']").first
        textarea.wait_for(state="visible", timeout=12_000)
        textarea.click(timeout=5_000)
        _x_type_text(page, text)
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_SELECTOR_CHANGED",
            message="Reply textarea not found",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )

    try:
        post_button = scope.locator("[data-testid='tweetButton'], [data-testid='tweetButtonInline']").first
        post_button.wait_for(state="visible", timeout=10_000)
        _wait_for_enabled(page, post_button, timeout_ms=5_000)
        post_button.click(timeout=5_000)
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_INTERCEPTED",
            message="Reply submit not clickable",
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

    if dialog.count() > 0:
        try:
            dialog.wait_for(state="detached", timeout=15_000)
        except Exception:
            pass

    return ExecuteActionResult(
        status="succeeded",
        error_code=None,
        message=None,
        current_url=str(page.url),
        screenshot_base64=None,
        metadata={},
    )


def _x_quote(page: Any, *, target_url: str | None, tweet_id: str | None, params: dict[str, Any]) -> ExecuteActionResult:
    if target_url is None or not str(target_url).strip():
        return ExecuteActionResult(
            status="failed",
            error_code="INVALID_TARGET",
            message="target_url is required for x_quote",
            current_url=None,
            screenshot_base64=None,
            metadata={},
        )

    text = str(params.get("text") or "").strip()
    if not text:
        return ExecuteActionResult(
            status="failed",
            error_code="INVALID_PARAMS",
            message="action_params.text is required for x_quote",
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
        dropdown = page.locator("[data-testid='Dropdown'], [role='menu']").first
        dropdown.wait_for(state="visible", timeout=6_000)
        quote_option = dropdown.locator("a[href*='/compose/post'], a[href*='/compose/tweet'], a[href*='/compose'], [data-testid='retweetWithComment']").first
        quote_option.wait_for(state="visible", timeout=4_000)
        quote_option.click(timeout=5_000)
        page.wait_for_timeout(random.randint(900, 1600))
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_SELECTOR_CHANGED",
            message="Quote option not found",
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

    textarea = _find_visible_locator(
        page,
        [
            "div[role='dialog'][aria-modal='true'] [data-testid='tweetTextarea_0']",
            "[data-testid='tweetTextarea_0'][role='textbox']",
            "[data-testid='tweetTextarea_0']",
        ],
        timeout_ms=20_000,
    )
    if textarea is None:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_SELECTOR_CHANGED",
            message="Quote textarea not found",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )

    try:
        textarea.click(timeout=5_000)
        _x_type_text(page, text)
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_INTERCEPTED",
            message="Cannot type quote text",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )

    try:
        post_button = page.locator("[data-testid='tweetButton'], [data-testid='tweetButtonInline']").first
        post_button.wait_for(state="visible", timeout=10_000)
        _wait_for_enabled(page, post_button, timeout_ms=5_000)
        post_button.click(timeout=5_000)
        page.wait_for_timeout(random.randint(1200, 2200))
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_INTERCEPTED",
            message="Quote submit not clickable",
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

    return ExecuteActionResult(
        status="succeeded",
        error_code=None,
        message=None,
        current_url=str(page.url),
        screenshot_base64=None,
        metadata={},
    )


def _x_has_reply_restriction(page: Any) -> bool:
    try:
        loc = page.locator("text=/Who can reply|who can reply|Mentioned|mentioned|谁可以回复/").first
        return loc.count() > 0 and loc.is_visible()
    except Exception:
        return False


def _x_dismiss_reply_restriction(page: Any) -> None:
    for label in ["Got it", "got it", "OK", "Ok", "知道了", "确定"]:
        try:
            btn = page.locator(f"button:has-text('{label}')").first
            if btn.count() > 0:
                btn.click(timeout=2_000)
                return
        except Exception:
            continue


def _x_type_text(page: Any, text: str) -> None:
    safe = text.strip()
    if not safe:
        return
    for chunk in _split_text(safe, max_len=160):
        page.keyboard.type(chunk, delay=random.randint(35, 75))
        page.wait_for_timeout(random.randint(120, 260))


def _split_text(text: str, *, max_len: int) -> list[str]:
    if len(text) <= max_len:
        return [text]
    parts: list[str] = []
    remaining = text
    while remaining:
        parts.append(remaining[:max_len])
        remaining = remaining[max_len:]
    return parts


def _find_visible_locator(page: Any, selectors: list[str], *, timeout_ms: int) -> Any | None:
    deadline = time.monotonic() + timeout_ms / 1000.0
    while True:
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if loc.count() == 0:
                    continue
                if loc.is_visible():
                    return loc
            except Exception:
                continue
        if time.monotonic() > deadline:
            break
        page.wait_for_timeout(250)
    return None


def _wait_for_enabled(page: Any, locator: Any, *, timeout_ms: int) -> None:
    try:
        handle = locator.element_handle()
        if handle is None:
            return
        page.wait_for_function(
            "(el) => { if (!el) return false; const aria = el.getAttribute('aria-disabled'); if (aria === 'true') return false; if (typeof el.disabled !== 'undefined' && el.disabled) return false; return true; }",
            handle,
            timeout=timeout_ms,
        )
    except Exception:
        return


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
