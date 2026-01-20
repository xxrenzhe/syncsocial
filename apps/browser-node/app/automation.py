from __future__ import annotations

import base64
import random
import re
import tempfile
import time
from urllib.request import Request, urlopen
from dataclasses import dataclass, field
from typing import Any, Literal

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ActionStatus = Literal["succeeded", "failed", "skipped"]
BandwidthMode = Literal["eco", "balanced", "full"]
_MAX_DOM_HTML_CHARS = 200_000
_MAX_TRACE_BYTES = 3_000_000


@dataclass(frozen=True)
class ExecuteActionResult:
    status: ActionStatus
    error_code: str | None
    message: str | None
    current_url: str | None
    screenshot_base64: str | None
    trace_base64: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def execute_action(
    *,
    platform_key: str,
    action_type: str,
    storage_state: dict[str, Any],
    target_url: str | None,
    target_external_id: str | None,
    bandwidth_mode: BandwidthMode | None,
    action_params: dict[str, Any] | None,
    fingerprint_profile: dict[str, Any] | None,
    proxy: dict[str, Any] | None,
    headless: bool,
) -> ExecuteActionResult:
    platform = platform_key.strip().lower()
    if platform not in {"x", "reddit"}:
        return ExecuteActionResult(
            status="failed",
            error_code="UNSUPPORTED_PLATFORM",
            message=f"Unsupported platform: {platform_key}",
            current_url=None,
            screenshot_base64=None,
            trace_base64=None,
            metadata={},
        )

    try:
        with sync_playwright() as pw:
            launch_kwargs: dict[str, Any] = {"headless": headless}
            normalized_proxy = _normalize_proxy(proxy or {})
            if normalized_proxy:
                launch_kwargs["proxy"] = normalized_proxy
            browser = pw.chromium.launch(**launch_kwargs)
            context_kwargs = {"storage_state": storage_state, **_context_kwargs_from_fingerprint(fingerprint_profile or {})}
            context = browser.new_context(**context_kwargs)
            _install_bandwidth_mode(context, bandwidth_mode)
            trace = _start_trace(context)
            page = context.new_page()
            page.set_default_timeout(15_000)
            page.set_default_navigation_timeout(30_000)

            try:
                res = _execute_action_on_page(
                    page,
                    platform_key=platform_key,
                    action_type=action_type,
                    target_url=target_url,
                    target_external_id=target_external_id,
                    action_params=action_params or {},
                )
                res = _enrich_failure_result(res, page)
                if res.status == "failed" and trace:
                    trace_base64 = _stop_trace_to_base64(trace, context)
                    if trace_base64:
                        res = ExecuteActionResult(
                            status=res.status,
                            error_code=res.error_code,
                            message=res.message,
                            current_url=res.current_url,
                            screenshot_base64=res.screenshot_base64,
                            trace_base64=trace_base64,
                            metadata=res.metadata,
                        )
                elif trace:
                    _stop_trace(trace, context)
                return res
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
            trace_base64=None,
            metadata={},
        )
    except PlaywrightError as exc:
        code = _classify_playwright_error(exc)
        return ExecuteActionResult(
            status="failed",
            error_code=code,
            message=str(exc),
            current_url=None,
            screenshot_base64=None,
            trace_base64=None,
            metadata={},
        )
    except Exception as exc:
        return ExecuteActionResult(
            status="failed",
            error_code="INTERNAL_ERROR",
            message=str(exc),
            current_url=None,
            screenshot_base64=None,
            trace_base64=None,
            metadata={},
        )


def execute_actions_batch(
    *,
    platform_key: str,
    actions: list[dict[str, Any]],
    storage_state: dict[str, Any],
    bandwidth_mode: BandwidthMode | None,
    fingerprint_profile: dict[str, Any] | None,
    proxy: dict[str, Any] | None,
    headless: bool,
) -> list[ExecuteActionResult]:
    platform = platform_key.strip().lower()
    if platform not in {"x", "reddit"}:
        return [
            ExecuteActionResult(
                status="failed",
                error_code="UNSUPPORTED_PLATFORM",
                message=f"Unsupported platform: {platform_key}",
                current_url=None,
                screenshot_base64=None,
                trace_base64=None,
                metadata={},
            )
            for _ in actions
        ]

    try:
        with sync_playwright() as pw:
            launch_kwargs: dict[str, Any] = {"headless": headless}
            normalized_proxy = _normalize_proxy(proxy or {})
            if normalized_proxy:
                launch_kwargs["proxy"] = normalized_proxy
            browser = pw.chromium.launch(**launch_kwargs)
            context_kwargs = {"storage_state": storage_state, **_context_kwargs_from_fingerprint(fingerprint_profile or {})}
            context = browser.new_context(**context_kwargs)
            _install_bandwidth_mode(context, bandwidth_mode)
            trace = _start_trace(context)
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
                            trace_base64=None,
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
                        platform_key=platform_key,
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
                        trace_base64=None,
                        metadata={},
                    )
                except PlaywrightError as exc:
                    code = _classify_playwright_error(exc)
                    res = ExecuteActionResult(
                        status="failed",
                        error_code=code,
                        message=str(exc),
                        current_url=str(getattr(page, "url", "")) or None,
                        screenshot_base64=_safe_screenshot(page),
                        trace_base64=None,
                        metadata={},
                    )
                except Exception as exc:
                    res = ExecuteActionResult(
                        status="failed",
                        error_code="INTERNAL_ERROR",
                        message=str(exc),
                        current_url=str(getattr(page, "url", "")) or None,
                        screenshot_base64=_safe_screenshot(page),
                        trace_base64=None,
                        metadata={},
                    )

                res = _enrich_failure_result(res, page)
                if res.status == "failed":
                    if trace:
                        trace_base64 = _stop_trace_to_base64(trace, context)
                        if trace_base64:
                            res = ExecuteActionResult(
                                status=res.status,
                                error_code=res.error_code,
                                message=res.message,
                                current_url=res.current_url,
                                screenshot_base64=res.screenshot_base64,
                                trace_base64=trace_base64,
                                metadata=res.metadata,
                            )
                    aborted = True
                    trace = None

                results.append(res)

            try:
                if trace:
                    _stop_trace(trace, context)
                context.close()
            finally:
                browser.close()

            return results
    except PlaywrightError as exc:
        code = _classify_playwright_error(exc)
        return [
            ExecuteActionResult(
                status="failed",
                error_code=code,
                message=str(exc),
                current_url=None,
                screenshot_base64=None,
                trace_base64=None,
                metadata={},
            )
            for _ in actions
        ]
    except Exception as exc:
        return [
            ExecuteActionResult(
                status="failed",
                error_code="BROWSER_ERROR",
                message=str(exc),
                current_url=None,
                screenshot_base64=None,
                trace_base64=None,
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


def _context_kwargs_from_fingerprint(profile: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(profile, dict) or not profile:
        return {}

    kwargs: dict[str, Any] = {}
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


def _normalize_proxy(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        return {}
    server = value.get("server")
    if not isinstance(server, str) or not server.strip():
        return {}
    payload: dict[str, Any] = {"server": server.strip()}
    username = value.get("username")
    if isinstance(username, str) and username.strip():
        payload["username"] = username.strip()
    password = value.get("password")
    if isinstance(password, str) and password.strip():
        payload["password"] = password.strip()
    return payload


def _classify_playwright_error(exc: PlaywrightError) -> str:
    msg = str(exc)
    lowered = msg.lower()
    for token in [
        "err_proxy_connection_failed",
        "proxy",
        "tunnel connection failed",
        "socks",
        "407",
        "proxy authentication required",
    ]:
        if token in lowered:
            return "PROXY_FAILED"
    return "BROWSER_ERROR"


def _execute_action_on_page(
    page: Any,
    *,
    platform_key: str,
    action_type: str,
    target_url: str | None,
    target_external_id: str | None,
    action_params: dict[str, Any],
) -> ExecuteActionResult:
    platform = str(platform_key or "").strip().lower()
    action = str(action_type).strip().lower()
    if platform == "x":
        if action in {"health_check", "x_health_check"}:
            return _x_health_check(page)
        if action in {"proxy_check", "x_proxy_check"}:
            return _x_proxy_check(page)
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
        if action in {"x_publish_post", "x_keyword_repost", "keyword_repost", "publish_post", "publish"}:
            return _x_publish_post(page, params=action_params)
        return ExecuteActionResult(
            status="failed",
            error_code="UNSUPPORTED_ACTION",
            message=f"Unsupported action_type: {action_type}",
            current_url=str(getattr(page, "url", "")) or None,
            screenshot_base64=_safe_screenshot(page),
            trace_base64=None,
            metadata={},
        )

    if platform == "reddit":
        if action in {"health_check", "reddit_health_check"}:
            return _reddit_health_check(page)
        if action in {"reddit_upvote", "upvote"}:
            return _reddit_upvote(page, target_url=target_url)
        if action in {"reddit_comment", "comment"}:
            return _reddit_comment(page, target_url=target_url, params=action_params)
        if action in {"reddit_post", "post"}:
            return _reddit_post(page, params=action_params)
        return ExecuteActionResult(
            status="failed",
            error_code="UNSUPPORTED_ACTION",
            message=f"Unsupported action_type: {action_type}",
            current_url=str(getattr(page, "url", "")) or None,
            screenshot_base64=_safe_screenshot(page),
            trace_base64=None,
            metadata={},
        )

    return ExecuteActionResult(
        status="failed",
        error_code="UNSUPPORTED_PLATFORM",
        message=f"Unsupported platform: {platform_key}",
        current_url=str(getattr(page, "url", "")) or None,
        screenshot_base64=_safe_screenshot(page),
        trace_base64=None,
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
    risk = _x_detect_risk(page)
    if risk is not None:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code=risk,
            message="Risk challenge detected",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            trace_base64=None,
            metadata={"risk": risk},
        )
    if not _x_is_logged_in(page):
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="AUTH_REQUIRED",
            message="Not logged in",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            trace_base64=None,
            metadata={"logged_in": False},
        )

    try:
        page.wait_for_selector("article", timeout=10_000)
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        if _x_has_no_search_results(page):
            return ExecuteActionResult(
                status="skipped",
                error_code=None,
                message="No search results",
                current_url=str(page.url),
                screenshot_base64=screenshot,
                trace_base64=None,
                metadata={"candidates": [], "collected": 0},
            )
        return ExecuteActionResult(
            status="failed",
            error_code="UI_SELECTOR_CHANGED",
            message="Search results not found (article selector missing)",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            trace_base64=None,
            metadata={},
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

            tweet_text = None
            try:
                tweet_text = article.locator("[data-testid='tweetText']").first.inner_text(timeout=200) or None
            except Exception:
                tweet_text = None
            if isinstance(tweet_text, str):
                tweet_text = tweet_text.strip().replace("\u2028", "\n").replace("\u2029", "\n")
                if not tweet_text:
                    tweet_text = None
                elif len(tweet_text) > 2000:
                    tweet_text = tweet_text[:2000].rstrip()

            timestamp = None
            try:
                timestamp = article.locator("time").first.get_attribute("datetime")
            except Exception:
                timestamp = None

            reply_count = _x_extract_metric_count(article, testid="reply")
            repost_count = _x_extract_metric_count(article, testid="retweet")
            like_count = _x_extract_metric_count(article, testid="like")
            view_count = _x_extract_view_count(article)

            candidates_by_id[tweet_id] = {
                "tweet_id": tweet_id,
                "url": url,
                "is_verified": is_verified,
                "text": tweet_text,
                "timestamp": timestamp,
                "reply_count": reply_count,
                "repost_count": repost_count,
                "like_count": like_count,
                "view_count": view_count,
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
            trace_base64=None,
            metadata={"candidates": [], "collected": 0},
        )

    return ExecuteActionResult(
        status="succeeded",
        error_code=None,
        message=None,
        current_url=str(page.url),
        screenshot_base64=None,
        trace_base64=None,
        metadata={"candidates": candidates, "collected": len(candidates)},
    )


def _extract_tweet_id_from_href(href: str) -> str | None:
    m = re.search(r"/status/(?P<tweet_id>\d+)", href)
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


def _parse_human_count(value: str) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    normalized = raw.replace(",", "").strip()
    m = re.search(r"(?P<num>\d+(?:\.\d+)?)(?P<unit>[KMB])?", normalized, flags=re.IGNORECASE)
    if not m:
        return None

    try:
        base = float(m.group("num"))
    except Exception:
        return None

    unit = (m.group("unit") or "").upper()
    if unit == "K":
        base *= 1_000
    elif unit == "M":
        base *= 1_000_000
    elif unit == "B":
        base *= 1_000_000_000

    try:
        return int(base)
    except Exception:
        return None


def _x_extract_metric_count(article: Any, *, testid: str) -> int | None:
    selectors = [
        f"button[data-testid='{testid}']",
        f"[data-testid='{testid}']",
    ]
    for sel in selectors:
        try:
            loc = article.locator(sel).first
            if loc.count() <= 0:
                continue
            aria = loc.get_attribute("aria-label") or ""
            parsed = _parse_human_count(aria)
            if parsed is not None:
                return parsed
            txt = loc.inner_text(timeout=200) or ""
            parsed = _parse_human_count(txt)
            if parsed is not None:
                return parsed
        except Exception:
            continue
    return None


def _x_extract_view_count(article: Any) -> int | None:
    selectors = [
        "[data-testid='analytics']",
        "a[href*='/analytics']",
        "a[aria-label*='view' i]",
        "a[aria-label*='观看' i]",
    ]
    for sel in selectors:
        try:
            loc = article.locator(sel).first
            if loc.count() <= 0:
                continue
            aria = loc.get_attribute("aria-label") or ""
            parsed = _parse_human_count(aria)
            if parsed is not None:
                return parsed
            txt = loc.inner_text(timeout=200) or ""
            parsed = _parse_human_count(txt)
            if parsed is not None:
                return parsed
        except Exception:
            continue
    return None


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
    risk = _x_detect_risk(page)
    if risk is not None:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code=risk,
            message="Risk challenge detected",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            trace_base64=None,
            metadata={"risk": risk},
        )
    logged_in = _x_is_logged_in(page)
    if logged_in:
        return ExecuteActionResult(
            status="succeeded",
            error_code=None,
            message=None,
            current_url=str(page.url),
            screenshot_base64=None,
            trace_base64=None,
            metadata={"logged_in": True},
        )

    screenshot = _safe_screenshot(page)
    return ExecuteActionResult(
        status="failed",
        error_code="AUTH_REQUIRED",
        message="Not logged in",
        current_url=str(page.url),
        screenshot_base64=screenshot,
        trace_base64=None,
        metadata={"logged_in": False},
    )


def _x_proxy_check(page: Any) -> ExecuteActionResult:
    page.goto("https://x.com", wait_until="domcontentloaded")
    risk = _x_detect_risk(page)
    if risk is not None:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code=risk,
            message="Risk challenge detected",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            trace_base64=None,
            metadata={"risk": risk},
        )
    return ExecuteActionResult(
        status="succeeded",
        error_code=None,
        message=None,
        current_url=str(page.url),
        screenshot_base64=None,
        trace_base64=None,
        metadata={},
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


def _x_has_no_search_results(page: Any) -> bool:
    try:
        return (
            page.locator(
                "text=/No results for|Try searching for|Nothing to see here|We didn't find any matches/i"
            ).count()
            > 0
        )
    except Exception:
        return False


def _x_detect_risk(page: Any) -> str | None:
    url = str(getattr(page, "url", "") or "")
    lowered = url.lower()
    if "/account/access" in lowered:
        return "ACCOUNT_LOCKED"
    if "/i/flow/verify" in lowered:
        return "CAPTCHA_REQUIRED"
    if "captcha" in lowered or "challenge" in lowered:
        return "CAPTCHA_REQUIRED"

    try:
        if page.locator("iframe[src*='arkoselabs'], iframe[src*='arkose']").count() > 0:
            return "CAPTCHA_REQUIRED"
        if page.locator("iframe[title*='captcha' i]").count() > 0:
            return "CAPTCHA_REQUIRED"
    except Exception:
        pass

    try:
        if page.locator(
            "text=/Verify you are human|unusual activity|suspicious activity|Are you a robot|Help us keep X safe/i"
        ).count() > 0:
            return "CAPTCHA_REQUIRED"
    except Exception:
        pass

    try:
        if page.locator("text=/账号已锁定|需要验证|检测到异常/i").count() > 0:
            return "ACCOUNT_LOCKED"
    except Exception:
        pass

    return None


def _x_like(page: Any, *, target_url: str | None, tweet_id: str | None) -> ExecuteActionResult:
    if target_url is None or not str(target_url).strip():
        return ExecuteActionResult(
            status="failed",
            error_code="INVALID_TARGET",
            message="target_url is required for x_like",
            current_url=None,
            screenshot_base64=None,
            trace_base64=None,
            metadata={},
        )

    page.goto(str(target_url), wait_until="domcontentloaded")

    risk = _x_detect_risk(page)
    if risk is not None:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code=risk,
            message="Risk challenge detected",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            trace_base64=None,
            metadata={"risk": risk},
        )

    if not _x_is_logged_in(page):
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="AUTH_REQUIRED",
            message="Not logged in",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            trace_base64=None,
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
            trace_base64=None,
            metadata={},
        )

    if article.locator('button[data-testid="unlike"]').count() > 0:
        return ExecuteActionResult(
            status="skipped",
            error_code=None,
            message="Already liked",
            current_url=str(page.url),
            screenshot_base64=None,
            trace_base64=None,
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
            trace_base64=None,
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
            trace_base64=None,
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
            trace_base64=None,
            metadata={"already_liked": False},
        )
    except PlaywrightTimeoutError:
        try:
            page.reload(wait_until="domcontentloaded")
            if tweet_id and str(tweet_id).strip():
                refreshed_article = page.locator("article").filter(has=page.locator(f'a[href*=\"/status/{tweet_id}\"]')).first
            else:
                refreshed_article = page.locator("article").first
            refreshed_article.wait_for(state="visible", timeout=10_000)
            if refreshed_article.locator('button[data-testid="unlike"]').count() > 0:
                return ExecuteActionResult(
                    status="succeeded",
                    error_code=None,
                    message=None,
                    current_url=str(page.url),
                    screenshot_base64=None,
                    trace_base64=None,
                    metadata={"already_liked": False, "confirmed_after_reload": True},
                )
        except Exception:
            pass

        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="POST_VALIDATION_FAILED",
            message="Like action not confirmed (unlike not visible)",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            trace_base64=None,
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
            trace_base64=None,
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
            trace_base64=None,
            metadata={},
        )

    page.goto(str(target_url), wait_until="domcontentloaded")

    risk = _x_detect_risk(page)
    if risk is not None:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code=risk,
            message="Risk challenge detected",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            trace_base64=None,
            metadata={"risk": risk},
        )

    if not _x_is_logged_in(page):
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="AUTH_REQUIRED",
            message="Not logged in",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            trace_base64=None,
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
            trace_base64=None,
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
            trace_base64=None,
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
            trace_base64=None,
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
            trace_base64=None,
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

    risk = _x_detect_risk(page)
    if risk is not None:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code=risk,
            message="Risk challenge detected",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={"risk": risk},
        )

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


def _x_publish_post(page: Any, *, params: dict[str, Any]) -> ExecuteActionResult:
    text = str(params.get("text") or "").strip()

    raw_media_urls = params.get("media_urls") or params.get("media") or []
    media_urls: list[str] = []
    if isinstance(raw_media_urls, list):
        for item in raw_media_urls:
            url = str(item or "").strip()
            if url:
                media_urls.append(url)
    if len(media_urls) > 4:
        media_urls = media_urls[:4]

    if not text and not media_urls:
        return ExecuteActionResult(
            status="failed",
            error_code="INVALID_PARAMS",
            message="action_params.text or action_params.media_urls is required for x_publish_post",
            current_url=None,
            screenshot_base64=None,
            metadata={},
        )

    max_media_bytes = _get_int(params, "max_media_bytes", default=150 * 1024, min_value=10 * 1024, max_value=5 * 1024 * 1024)
    max_download_bytes = _get_int(params, "max_download_bytes", default=5 * 1024 * 1024, min_value=100 * 1024, max_value=20 * 1024 * 1024)
    compose_url = str(params.get("compose_url") or "https://x.com/compose/post").strip()

    page.goto(compose_url, wait_until="domcontentloaded")

    risk = _x_detect_risk(page)
    if risk is not None:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code=risk,
            message="Risk challenge detected",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={"risk": risk},
        )

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

    textarea = _find_visible_locator(
        page,
        [
            "[data-testid='tweetTextarea_0']",
            "div[role='textbox'][contenteditable='true']",
        ],
        timeout_ms=20_000,
    )
    if textarea is None:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_SELECTOR_CHANGED",
            message="Compose textarea not found",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )

    try:
        textarea.click(timeout=5_000)
        if text:
            _x_type_text(page, text)
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_INTERCEPTED",
            message="Cannot type post text",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )

    if media_urls:
        with tempfile.TemporaryDirectory(prefix="syncsocial_x_media_") as tmpdir:
            file_paths: list[str] = []
            try:
                for idx, url in enumerate(media_urls):
                    raw_bytes, content_type = _download_bytes(url, max_bytes=max_download_bytes)
                    payload, ext = _shrink_image_if_needed(
                        raw_bytes,
                        url=url,
                        content_type=content_type,
                        max_bytes=max_media_bytes,
                    )
                    path = f"{tmpdir}/upload_{idx}{ext}"
                    with open(path, "wb") as f:
                        f.write(payload)
                    file_paths.append(path)
            except ValueError as exc:
                screenshot = _safe_screenshot(page)
                return ExecuteActionResult(
                    status="failed",
                    error_code=str(exc) or "MEDIA_DOWNLOAD_FAILED",
                    message="Failed to download or preprocess media",
                    current_url=str(page.url),
                    screenshot_base64=screenshot,
                    metadata={"media_urls": media_urls},
                )
            except Exception as exc:
                screenshot = _safe_screenshot(page)
                return ExecuteActionResult(
                    status="failed",
                    error_code="MEDIA_DOWNLOAD_FAILED",
                    message=str(exc),
                    current_url=str(page.url),
                    screenshot_base64=screenshot,
                    metadata={"media_urls": media_urls},
                )

            file_input = _find_visible_locator(
                page,
                [
                    "input[type='file'][data-testid='fileInput']",
                    "input[type='file'][accept*='image']",
                    "input[type='file']",
                ],
                timeout_ms=12_000,
            )
            if file_input is None:
                screenshot = _safe_screenshot(page)
                return ExecuteActionResult(
                    status="failed",
                    error_code="UI_SELECTOR_CHANGED",
                    message="Media file input not found",
                    current_url=str(page.url),
                    screenshot_base64=screenshot,
                    metadata={},
                )

            try:
                file_input.set_input_files(file_paths)
            except Exception as exc:
                screenshot = _safe_screenshot(page)
                return ExecuteActionResult(
                    status="failed",
                    error_code="MEDIA_UPLOAD_FAILED",
                    message=str(exc),
                    current_url=str(page.url),
                    screenshot_base64=screenshot,
                    metadata={},
                )

            if not _x_wait_for_media_attachments(page, expected_count=len(file_paths), timeout_ms=20_000):
                screenshot = _safe_screenshot(page)
                return ExecuteActionResult(
                    status="failed",
                    error_code="MEDIA_UPLOAD_FAILED",
                    message="Media attachments not detected after upload",
                    current_url=str(page.url),
                    screenshot_base64=screenshot,
                    metadata={},
                )

    try:
        post_button = page.locator("[data-testid='tweetButton'], [data-testid='tweetButtonInline']").first
        post_button.wait_for(state="visible", timeout=12_000)
        _wait_for_enabled(page, post_button, timeout_ms=7_000)
        post_button.click(timeout=5_000)
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_INTERCEPTED",
            message="Post submit not clickable",
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

    success = _x_wait_for_post_success(page, timeout_ms=20_000)
    if not success:
        risk = _x_detect_risk(page)
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code=risk or "POST_VALIDATION_FAILED",
            message="Post not confirmed",
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
        metadata=success,
    )


def _download_bytes(url: str, *, max_bytes: int) -> tuple[bytes, str]:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as resp:
        content_type = str(resp.headers.get("Content-Type") or "")
        data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("MEDIA_TOO_LARGE")
    return data, content_type


def _guess_media_ext(*, url: str, content_type: str) -> str:
    ct = content_type.lower()
    if "image/jpeg" in ct:
        return ".jpg"
    if "image/png" in ct:
        return ".png"
    if "image/gif" in ct:
        return ".gif"
    if "image/webp" in ct:
        return ".webp"
    lowered = url.lower()
    m = re.search(r"\\.(jpg|jpeg|png|gif|webp)(?:\\?|#|$)", lowered)
    if m:
        ext = m.group(1)
        if ext == "jpeg":
            ext = "jpg"
        return f".{ext}"
    return ".jpg"


def _shrink_image_if_needed(payload: bytes, *, url: str, content_type: str, max_bytes: int) -> tuple[bytes, str]:
    ext = _guess_media_ext(url=url, content_type=content_type)
    if len(payload) <= max_bytes:
        return payload, ext

    try:
        import io

        from PIL import Image
    except Exception:
        return payload, ext

    try:
        img = Image.open(io.BytesIO(payload))
        img.load()
    except Exception:
        return payload, ext

    img = img.convert("RGB")
    for quality in [85, 75, 65, 55, 45, 35]:
        buf = io.BytesIO()
        try:
            img.save(buf, format="JPEG", quality=quality, optimize=True)
        except Exception:
            continue
        out = buf.getvalue()
        if len(out) <= max_bytes:
            return out, ".jpg"

    # If still too large, downscale and retry a couple times.
    for scale in [0.85, 0.7, 0.55]:
        try:
            resized = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))))
        except Exception:
            continue
        for quality in [70, 55, 40]:
            buf = io.BytesIO()
            try:
                resized.save(buf, format="JPEG", quality=quality, optimize=True)
            except Exception:
                continue
            out = buf.getvalue()
            if len(out) <= max_bytes:
                return out, ".jpg"

    return payload, ext


def _x_wait_for_media_attachments(page: Any, *, expected_count: int, timeout_ms: int) -> bool:
    if expected_count <= 0:
        return True
    deadline = time.monotonic() + timeout_ms / 1000.0
    selectors = [
        "[data-testid='attachments'] img",
        "[data-testid='attachments'] video",
        "[data-testid='attachments'] [role='img']",
        "div[aria-label*='Remove']",
    ]
    while time.monotonic() < deadline:
        try:
            for sel in selectors:
                if page.locator(sel).count() >= expected_count:
                    return True
        except Exception:
            pass
        page.wait_for_timeout(300)
    return False


def _x_wait_for_post_success(page: Any, *, timeout_ms: int) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        url = str(getattr(page, "url", "") or "")
        m = re.search(r"/status/(?P<tweet_id>\d+)", url)
        if m:
            tweet_id = m.group("tweet_id")
            return {"tweet_id": tweet_id, "tweet_url": url.split("?", 1)[0]}

        try:
            toast = page.locator("[data-testid='toast']").first
            if toast.count() > 0:
                text = toast.inner_text(timeout=500) or ""
                if re.search(r"sent|posted|已发送|已发布|发送成功", text, flags=re.IGNORECASE):
                    return {"tweet_id": None, "tweet_url": None, "toast": text.strip()[:200]}
        except Exception:
            pass

        page.wait_for_timeout(300)
    return None


def _normalize_reddit_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return raw

    if raw.startswith("/"):
        raw = f"https://www.reddit.com{raw}"

    normalized = re.sub(r"^https?://(www\\.)?reddit\\.com", "https://old.reddit.com", raw, flags=re.IGNORECASE)
    normalized = re.sub(r"^https?://old\\.reddit\\.com", "https://old.reddit.com", normalized, flags=re.IGNORECASE)
    normalized = normalized.split("#", 1)[0].split("?", 1)[0]
    return normalized


def _reddit_detect_risk(page: Any) -> str | None:
    url = str(getattr(page, "url", "") or "")
    lowered = url.lower()
    if "captcha" in lowered or "/captcha" in lowered:
        return "CAPTCHA_REQUIRED"

    try:
        if page.locator("text=/verify you are human|captcha|unusual activity|suspicious activity/i").count() > 0:
            return "CAPTCHA_REQUIRED"
    except Exception:
        pass

    try:
        if page.locator("text=/you are doing that too much|try again later/i").count() > 0:
            return "RATE_LIMITED"
    except Exception:
        pass

    return None


def _reddit_is_logged_in_old(page: Any) -> bool:
    try:
        if page.locator("#header-bottom-right a.logout, a[href*='logout']").count() > 0:
            return True
    except Exception:
        pass
    try:
        if page.locator("form#login_login-main, form#login_login, input[name='user'], input[name='passwd']").count() > 0:
            return False
    except Exception:
        pass
    return False


def _reddit_health_check(page: Any) -> ExecuteActionResult:
    page.goto("https://old.reddit.com", wait_until="domcontentloaded")
    risk = _reddit_detect_risk(page)
    if risk is not None:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code=risk,
            message="Risk challenge detected",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={"risk": risk},
        )
    logged_in = _reddit_is_logged_in_old(page)
    if logged_in:
        return ExecuteActionResult(
            status="succeeded",
            error_code=None,
            message=None,
            current_url=str(page.url),
            screenshot_base64=None,
            metadata={},
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


def _reddit_upvote(page: Any, *, target_url: str | None) -> ExecuteActionResult:
    if target_url is None or not str(target_url).strip():
        return ExecuteActionResult(
            status="failed",
            error_code="INVALID_TARGET",
            message="target_url is required for reddit_upvote",
            current_url=None,
            screenshot_base64=None,
            metadata={},
        )

    url = _normalize_reddit_url(str(target_url))
    page.goto(url, wait_until="domcontentloaded")

    risk = _reddit_detect_risk(page)
    if risk is not None:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code=risk,
            message="Risk challenge detected",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={"risk": risk},
        )

    if not _reddit_is_logged_in_old(page):
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
        thing = page.locator("div#siteTable .thing").first
        thing.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_SELECTOR_CHANGED",
            message="Content not found",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )

    if thing.locator("div.arrow.upmod").count() > 0:
        return ExecuteActionResult(
            status="skipped",
            error_code=None,
            message="Already upvoted",
            current_url=str(page.url),
            screenshot_base64=None,
            metadata={"already_upvoted": True},
        )

    try:
        up = thing.locator("div.arrow.up").first
        up.wait_for(state="visible", timeout=5_000)
        up.scroll_into_view_if_needed(timeout=3_000)
        up.click(timeout=5_000)
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_INTERCEPTED",
            message="Upvote button not clickable",
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
        thing.locator("div.arrow.upmod").first.wait_for(state="visible", timeout=5_000)
        return ExecuteActionResult(
            status="succeeded",
            error_code=None,
            message=None,
            current_url=str(page.url),
            screenshot_base64=None,
            metadata={"already_upvoted": False},
        )
    except PlaywrightTimeoutError:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="POST_VALIDATION_FAILED",
            message="Upvote not confirmed (upmod not visible)",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )


def _reddit_comment(page: Any, *, target_url: str | None, params: dict[str, Any]) -> ExecuteActionResult:
    if target_url is None or not str(target_url).strip():
        return ExecuteActionResult(
            status="failed",
            error_code="INVALID_TARGET",
            message="target_url is required for reddit_comment",
            current_url=None,
            screenshot_base64=None,
            metadata={},
        )

    text = str(params.get("text") or "").strip()
    if not text:
        return ExecuteActionResult(
            status="failed",
            error_code="INVALID_PARAMS",
            message="action_params.text is required for reddit_comment",
            current_url=None,
            screenshot_base64=None,
            metadata={},
        )

    url = _normalize_reddit_url(str(target_url))
    page.goto(url, wait_until="domcontentloaded")

    risk = _reddit_detect_risk(page)
    if risk is not None:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code=risk,
            message="Risk challenge detected",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={"risk": risk},
        )

    if not _reddit_is_logged_in_old(page):
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="AUTH_REQUIRED",
            message="Not logged in",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={"logged_in": False},
        )

    textarea = _find_visible_locator(
        page,
        [
            "textarea[name='text']",
            "form.usertext textarea",
        ],
        timeout_ms=15_000,
    )
    if textarea is None:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_SELECTOR_CHANGED",
            message="Comment textarea not found",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )

    try:
        textarea.click(timeout=3_000)
        _x_type_text(page, text)
    except Exception as exc:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_INTERCEPTED",
            message=str(exc),
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )

    submit = _find_visible_locator(
        page,
        [
            "form.usertext button[type='submit']",
            "form.usertext button.save",
        ],
        timeout_ms=8_000,
    )
    if submit is None:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_SELECTOR_CHANGED",
            message="Comment submit button not found",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )

    try:
        submit.click(timeout=5_000)
        page.wait_for_timeout(random.randint(900, 1400))
    except Exception as exc:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_INTERCEPTED",
            message=str(exc),
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )

    # Best-effort confirmation: detect common error messages.
    try:
        if page.locator(".error, .status.error, div.error").count() > 0:
            screenshot = _safe_screenshot(page)
            return ExecuteActionResult(
                status="failed",
                error_code="POST_VALIDATION_FAILED",
                message="Comment may have failed (error indicator visible)",
                current_url=str(page.url),
                screenshot_base64=screenshot,
                metadata={},
            )
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


def _reddit_post(page: Any, *, params: dict[str, Any]) -> ExecuteActionResult:
    subreddit = str(params.get("subreddit") or "").strip().lstrip("r/").strip("/")
    title = str(params.get("title") or "").strip()
    text = str(params.get("text") or params.get("body") or "").strip()
    if not subreddit or not title:
        return ExecuteActionResult(
            status="failed",
            error_code="INVALID_PARAMS",
            message="action_params.subreddit and action_params.title are required for reddit_post",
            current_url=None,
            screenshot_base64=None,
            metadata={},
        )

    submit_url = f"https://old.reddit.com/r/{subreddit}/submit"
    page.goto(submit_url, wait_until="domcontentloaded")

    risk = _reddit_detect_risk(page)
    if risk is not None:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code=risk,
            message="Risk challenge detected",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={"risk": risk},
        )

    if not _reddit_is_logged_in_old(page):
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="AUTH_REQUIRED",
            message="Not logged in",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={"logged_in": False},
        )

    title_input = _find_visible_locator(page, ["textarea[name='title']", "input[name='title']"], timeout_ms=12_000)
    if title_input is None:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_SELECTOR_CHANGED",
            message="Post title input not found",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )

    try:
        title_input.click(timeout=3_000)
        _x_type_text(page, title)
    except Exception as exc:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_INTERCEPTED",
            message=str(exc),
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )

    if text:
        body_input = _find_visible_locator(page, ["textarea[name='text']", "form.usertext textarea"], timeout_ms=12_000)
        if body_input is not None:
            try:
                body_input.click(timeout=3_000)
                _x_type_text(page, text)
            except Exception:
                pass

    submit = _find_visible_locator(page, ["button[type='submit']", "button:has-text('submit')"], timeout_ms=10_000)
    if submit is None:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_SELECTOR_CHANGED",
            message="Post submit button not found",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )

    try:
        submit.click(timeout=5_000)
    except Exception as exc:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code="UI_INTERCEPTED",
            message=str(exc),
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={},
        )

    # Best-effort: successful submission usually lands on /comments/.
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        if "/comments/" in str(getattr(page, "url", "") or ""):
            return ExecuteActionResult(
                status="succeeded",
                error_code=None,
                message=None,
                current_url=str(page.url),
                screenshot_base64=None,
                metadata={},
            )
        page.wait_for_timeout(300)

    screenshot = _safe_screenshot(page)
    return ExecuteActionResult(
        status="failed",
        error_code="POST_VALIDATION_FAILED",
        message="Post not confirmed",
        current_url=str(page.url),
        screenshot_base64=screenshot,
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

    risk = _x_detect_risk(page)
    if risk is not None:
        screenshot = _safe_screenshot(page)
        return ExecuteActionResult(
            status="failed",
            error_code=risk,
            message="Risk challenge detected",
            current_url=str(page.url),
            screenshot_base64=screenshot,
            metadata={"risk": risk},
        )

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
        try:
            page.reload(wait_until="domcontentloaded")
            if tweet_id and str(tweet_id).strip():
                refreshed_article = page.locator("article").filter(has=page.locator(f'a[href*=\"/status/{tweet_id}\"]')).first
            else:
                refreshed_article = page.locator("article").first
            refreshed_article.wait_for(state="visible", timeout=10_000)
            if refreshed_article.locator('button[data-testid="unretweet"]').count() > 0:
                return ExecuteActionResult(
                    status="succeeded",
                    error_code=None,
                    message=None,
                    current_url=str(page.url),
                    screenshot_base64=None,
                    metadata={"already_reposted": False, "confirmed_after_reload": True},
                )
        except Exception:
            pass

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


def _safe_dom_html(page: Any) -> str | None:
    try:
        html = page.content()
    except Exception:
        return None
    if not isinstance(html, str) or not html:
        return None
    if len(html) > _MAX_DOM_HTML_CHARS:
        return html[:_MAX_DOM_HTML_CHARS]
    return html


def _failure_metadata(page: Any, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if isinstance(extra, dict) and extra:
        payload.update(extra)
    dom_html = _safe_dom_html(page)
    if dom_html:
        payload["dom_html"] = dom_html
    return payload


def _enrich_failure_result(result: ExecuteActionResult, page: Any) -> ExecuteActionResult:
    if result.status != "failed":
        return result
    if result.metadata and "dom_html" in result.metadata:
        return result
    metadata = dict(result.metadata or {})
    dom_html = _safe_dom_html(page)
    if dom_html:
        metadata["dom_html"] = dom_html
    if metadata == (result.metadata or {}):
        return result
    return ExecuteActionResult(
        status=result.status,
        error_code=result.error_code,
        message=result.message,
        current_url=result.current_url,
        screenshot_base64=result.screenshot_base64,
        trace_base64=result.trace_base64,
        metadata=metadata,
    )


def _start_trace(context: Any) -> bool:
    try:
        context.tracing.start(screenshots=True, snapshots=True, sources=False)
        return True
    except Exception:
        return False


def _stop_trace(_: bool, context: Any) -> None:
    try:
        context.tracing.stop()
    except Exception:
        return


def _stop_trace_to_base64(_: bool, context: Any) -> str | None:
    try:
        tmp = tempfile.NamedTemporaryFile(prefix="trace-", suffix=".zip", delete=False)
        path = tmp.name
        tmp.close()
    except Exception:
        path = None

    if not path:
        try:
            context.tracing.stop()
        except Exception:
            pass
        return None

    try:
        context.tracing.stop(path=path)
        with open(path, "rb") as f:
            payload = f.read()
    except Exception:
        return None
    finally:
        try:
            import os

            os.unlink(path)
        except Exception:
            pass

    if not payload:
        return None
    if len(payload) > _MAX_TRACE_BYTES:
        return None
    try:
        return base64.b64encode(payload).decode("ascii")
    except Exception:
        return None
