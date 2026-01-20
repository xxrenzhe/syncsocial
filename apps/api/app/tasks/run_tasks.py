from __future__ import annotations

import base64
import hashlib
import random
import re
import uuid
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import or_, select, update

from app.celery_app import celery_app
from app.core.config import settings
from app.core.crypto import decrypt_json
from app.db.session import SessionLocal
from app.models.account_run import AccountRun
from app.models.action import Action
from app.models.artifact import Artifact
from app.models.credential import Credential
from app.models.prompt_stack import PromptStack
from app.models.run import Run
from app.models.schedule import Schedule
from app.models.social_account import SocialAccount
from app.models.strategy import Strategy
from app.services.browser_cluster import browser_cluster
from app.services.llm_gateway import generate_text as llm_generate_text
from app.services.llm_gateway import get_workspace_llm_config
from app.services.prompt_stack_engine import generate_prompt_from_stack
from app.services.proxy_selection import select_proxy_for_account_with_id
from app.services.subscription import increment_automation_runtime_seconds
from app.utils.time import utc_now

_TWEET_ID_RE = re.compile(r"/status/(?P<tweet_id>\d+)")
_RETRYABLE_ACCOUNT_RUN_ERRORS = {"PROXY_FAILED", "BROWSER_NODE_ERROR", "BROWSER_ERROR"}


@celery_app.task(name="syncsocial.execute_account_run")
def execute_account_run(account_run_id: str) -> None:
    account_run_uuid = uuid.UUID(account_run_id)
    now = utc_now()

    with SessionLocal() as db:
        claim = (
            update(AccountRun)
            .where(AccountRun.id == account_run_uuid)
            .where(AccountRun.status.in_(["queued", "retry_waiting"]))
            .where(or_(AccountRun.next_retry_at.is_(None), AccountRun.next_retry_at <= now))
            .values(status="running", started_at=now, finished_at=None, error_code=None)
        )
        claimed = db.execute(claim)
        if not claimed.rowcount:
            return
        db.commit()

        account_run = db.get(AccountRun, account_run_uuid)
        if account_run is None:
            return

        run = db.get(Run, account_run.run_id)
        if run is None:
            account_run.status = "failed"
            account_run.error_code = "RUN_NOT_FOUND"
            account_run.finished_at = utc_now()
            account_run.next_retry_at = None
            db.add(account_run)
            db.commit()
            return

        strategy = db.get(Strategy, run.strategy_id)
        if strategy is None:
            _fail_account_run(db, account_run, run, error_code="STRATEGY_NOT_FOUND")
            return

        if run.status == "queued":
            run.status = "running"
            run.started_at = now
            db.add(run)

        db.commit()

        account = db.get(SocialAccount, account_run.social_account_id)
        if account is None:
            _fail_account_run(db, account_run, run, error_code="ACCOUNT_NOT_FOUND")
            return
        if str(account.platform_key or "").strip().lower() != str(strategy.platform_key or "").strip().lower():
            _fail_account_run(db, account_run, run, error_code="STRATEGY_PLATFORM_MISMATCH")
            return

        credential = db.scalar(
            select(Credential).where(
                Credential.workspace_id == account_run.workspace_id,
                Credential.social_account_id == account.id,
                Credential.credential_type == "storage_state",
            )
        )

        if account.status != "healthy" or credential is None:
            _fail_account_run(db, account_run, run, error_code="AUTH_REQUIRED")
            return

        try:
            storage_state = decrypt_json(credential.encrypted_blob)
        except Exception:
            _fail_account_run(db, account_run, run, error_code="CREDENTIAL_DECRYPT_FAILED")
            return

        strategy_type = _strategy_type(strategy)
        if _strategy_requires_action_text(strategy_type) and not _resolve_action_text(db, workspace_id=account_run.workspace_id, strategy=strategy):
            _fail_account_run(db, account_run, run, error_code="STRATEGY_CONFIG_INVALID")
            return
        if _resolve_action_type(strategy_type) == "x_publish_post" and not _strategy_has_publish_content(strategy):
            _fail_account_run(db, account_run, run, error_code="STRATEGY_CONFIG_INVALID")
            return

        if strategy_type in {"keyword_repost", "x_keyword_repost"}:
            config = strategy.config if isinstance(strategy.config, dict) else {}
            if not _resolve_search_query(config):
                _fail_account_run(db, account_run, run, error_code="STRATEGY_CONFIG_INVALID")
                return
            search_specs = _build_search_collect_specs(db, strategy, account_run=account_run, account=account, run=run)
            executed_actions, results, error_code = _execute_specs(
                db,
                account_run=account_run,
                run=run,
                account=account,
                strategy=strategy,
                storage_state=storage_state,
                specs=search_specs,
            )
            if error_code is not None:
                if not _retry_or_fail_account_run(db, account_run, run, error_code=error_code):
                    _fail_account_run(db, account_run, run, error_code=error_code)
                return

            candidates = _extract_candidates(executed_actions, results)
            if not candidates:
                account_run.status = "succeeded"
                account_run.finished_at = utc_now()
                account_run.next_retry_at = None
                db.add(account_run)
                db.commit()
                _finalize_run_if_done(db, run.id)
                return

            action_specs = _build_keyword_repost_specs(
                db,
                strategy,
                account_run=account_run,
                account=account,
                run=run,
                candidates=candidates,
            )
            if not action_specs:
                _fail_account_run(db, account_run, run, error_code="CONTENT_GENERATION_FAILED")
                return
            _, _, action_error = _execute_specs(
                db,
                account_run=account_run,
                run=run,
                account=account,
                strategy=strategy,
                storage_state=storage_state,
                specs=action_specs,
            )
            if action_error is not None:
                if not _retry_or_fail_account_run(db, account_run, run, error_code=action_error):
                    _fail_account_run(db, account_run, run, error_code=action_error)
                return

        elif strategy_type in {
            "x_search_like",
            "x_search_repost",
            "x_search_reply",
            "x_search_quote",
            "x_verified_like",
            "x_verified_repost",
            "x_verified_reply",
            "x_verified_quote",
            "keyword_like",
            "keyword_reply",
            "keyword_quote",
            "keyword_retweet",
        }:
            search_specs = _build_search_collect_specs(db, strategy, account_run=account_run, account=account, run=run)
            executed_actions, results, error_code = _execute_specs(
                db,
                account_run=account_run,
                run=run,
                account=account,
                strategy=strategy,
                storage_state=storage_state,
                specs=search_specs,
            )
            if error_code is not None:
                if not _retry_or_fail_account_run(db, account_run, run, error_code=error_code):
                    _fail_account_run(db, account_run, run, error_code=error_code)
                return

            candidates = _extract_candidates(executed_actions, results)
            if not candidates:
                account_run.status = "succeeded"
                account_run.finished_at = utc_now()
                account_run.next_retry_at = None
                db.add(account_run)
                db.commit()
                _finalize_run_if_done(db, run.id)
                return

            action_specs = _build_search_action_specs(
                db,
                strategy,
                account_run=account_run,
                account=account,
                candidates=candidates,
            )
            _, _, action_error = _execute_specs(
                db,
                account_run=account_run,
                run=run,
                account=account,
                strategy=strategy,
                storage_state=storage_state,
                specs=action_specs,
            )
            if action_error is not None:
                if not _retry_or_fail_account_run(db, account_run, run, error_code=action_error):
                    _fail_account_run(db, account_run, run, error_code=action_error)
                return
        else:
            action_specs = _build_action_specs(db, strategy, account_run=account_run, account=account)
            _, _, error_code = _execute_specs(
                db,
                account_run=account_run,
                run=run,
                account=account,
                strategy=strategy,
                storage_state=storage_state,
                specs=action_specs,
            )
            if error_code is not None:
                if not _retry_or_fail_account_run(db, account_run, run, error_code=error_code):
                    _fail_account_run(db, account_run, run, error_code=error_code)
                return

        account_run.status = "succeeded"
        account_run.finished_at = utc_now()
        account_run.next_retry_at = None
        db.add(account_run)
        increment_automation_runtime_seconds(
            db,
            workspace_id=account_run.workspace_id,
            started_at=account_run.started_at,
            finished_at=account_run.finished_at,
        )
        db.commit()

        _finalize_run_if_done(db, run.id)


def _retry_or_fail_account_run(db, account_run: AccountRun, run: Run, *, error_code: str) -> bool:
    code = str(error_code or "").strip()
    if not code or code not in _RETRYABLE_ACCOUNT_RUN_ERRORS:
        return False

    max_retries = max(0, int(getattr(settings, "account_run_max_retries", 3) or 0))
    retry_count = int(getattr(account_run, "retry_count", 0) or 0)
    if retry_count >= max_retries:
        return False

    base = max(1, int(getattr(settings, "account_run_retry_base_seconds", 30) or 30))
    cap = max(base, int(getattr(settings, "account_run_retry_max_seconds", 30 * 60) or 30 * 60))
    delay = min(cap, base * (2**retry_count))
    delay = int(delay * random.uniform(0.85, 1.15))
    if delay < 1:
        delay = 1

    now = utc_now()
    account_run.status = "retry_waiting"
    account_run.error_code = code
    account_run.finished_at = now
    account_run.next_retry_at = now + timedelta(seconds=delay)
    account_run.retry_count = retry_count + 1
    db.add(account_run)

    increment_automation_runtime_seconds(
        db,
        workspace_id=account_run.workspace_id,
        started_at=account_run.started_at,
        finished_at=account_run.finished_at,
    )
    if run.status == "queued":
        run.status = "running"
        run.started_at = now
        db.add(run)
    db.commit()

    if not settings.celery_task_always_eager:
        try:
            celery_app.send_task("syncsocial.execute_account_run", args=[str(account_run.id)], countdown=delay)
        except Exception:
            pass

    _finalize_run_if_done(db, run.id)
    return True


def _fail_account_run(db, account_run: AccountRun, run: Run, *, error_code: str) -> None:
    account_run.status = "failed"
    account_run.error_code = error_code
    account_run.finished_at = utc_now()
    account_run.next_retry_at = None
    db.add(account_run)
    increment_automation_runtime_seconds(
        db,
        workspace_id=account_run.workspace_id,
        started_at=account_run.started_at,
        finished_at=account_run.finished_at,
    )
    if run.status == "queued":
        run.status = "running"
        run.started_at = utc_now()
        db.add(run)
    db.commit()
    _finalize_run_if_done(db, run.id)


def _finalize_run_if_done(db, run_id: uuid.UUID) -> None:
    run = db.get(Run, run_id)
    if run is None:
        return

    account_runs = db.scalars(select(AccountRun).where(AccountRun.run_id == run.id)).all()
    if not account_runs:
        run.status = "succeeded"
        run.finished_at = utc_now()
        db.add(run)
        db.commit()
        return

    if any(ar.status in {"queued", "running", "retry_waiting"} for ar in account_runs):
        return

    if any(ar.status == "failed" for ar in account_runs):
        run.status = "failed"
    else:
        run.status = "succeeded"
    run.finished_at = utc_now()
    db.add(run)
    db.commit()


def _build_action_specs(db, strategy: Strategy, *, account_run: AccountRun, account: SocialAccount) -> list[dict]:
    config = strategy.config if isinstance(strategy.config, dict) else {}
    bandwidth_mode = config.get("bandwidth_mode")
    specs: list[dict] = [
        {
            "action_type": "health_check",
            "platform_key": account.platform_key,
            "target_url": None,
            "target_external_id": None,
            "idempotency_key": f"{account_run.workspace_id}:{account.id}:health_check:{account_run.run_id}",
            "bandwidth_mode": bandwidth_mode,
        }
    ]

    action_kind = str(config.get("type") or "").strip().lower()
    action_type = _resolve_action_type(action_kind)
    if action_type is None:
        return specs

    if action_type.startswith("x_") and account.platform_key != "x":
        return specs
    if action_type.startswith("reddit_") and account.platform_key != "reddit":
        return specs

    if action_type == "x_publish_post":
        texts = _resolve_publish_texts(strategy)
        media_urls = _resolve_media_urls(config)
        if not texts and not media_urls:
            return specs

        max_actions = _get_int_from_config(config, "max_actions", default=1, min_value=1, max_value=10)
        picked_texts: list[str] = []
        if texts:
            random.shuffle(texts)
            picked_texts = texts[:max_actions]
        else:
            picked_texts = [""] * min(max_actions, 1)

        window_days = _get_int_from_config(config, "repeat_window_days", default=1, min_value=1, max_value=365)
        window_suffix = f":w{_idempotency_window_key(window_days)}"

        max_media_bytes = _get_int_from_config(config, "max_media_bytes", default=150 * 1024, min_value=10 * 1024, max_value=5 * 1024 * 1024)
        max_download_bytes = _get_int_from_config(config, "max_download_bytes", default=5 * 1024 * 1024, min_value=100 * 1024, max_value=20 * 1024 * 1024)
        compose_url = str(config.get("compose_url") or "https://x.com/compose/post").strip()

        for text in picked_texts:
            stable_target = _stable_content_key(text=text, media_urls=media_urls)
            specs.append(
                {
                    "action_type": action_type,
                    "platform_key": "x",
                    "target_url": None,
                    "target_external_id": None,
                    "idempotency_key": f"{account_run.workspace_id}:{account.id}:{action_type}:{stable_target}:v{strategy.version}{window_suffix}",
                    "bandwidth_mode": bandwidth_mode,
                    "action_params": {
                        "text": text,
                        "media_urls": media_urls,
                        "max_media_bytes": max_media_bytes,
                        "max_download_bytes": max_download_bytes,
                        "compose_url": compose_url,
                    },
                }
            )
        return specs

    if action_type == "reddit_post":
        subreddit = str(config.get("subreddit") or "").strip()
        title = str(config.get("title") or "").strip()
        body = str(config.get("text") or config.get("body") or "").strip()
        if not subreddit or not title:
            return specs

        max_actions = _get_int_from_config(config, "max_actions", default=1, min_value=1, max_value=5)
        window_days = _get_int_from_config(config, "repeat_window_days", default=7, min_value=1, max_value=365)
        window_suffix = f":w{_idempotency_window_key(window_days)}"

        for _ in range(max_actions):
            stable_target = _stable_content_key(text=f"r/{subreddit}\n{title}\n{body}", media_urls=[])
            specs.append(
                {
                    "action_type": "reddit_post",
                    "platform_key": "reddit",
                    "target_url": None,
                    "target_external_id": None,
                    "idempotency_key": f"{account_run.workspace_id}:{account.id}:reddit_post:{stable_target}:v{strategy.version}{window_suffix}",
                    "bandwidth_mode": bandwidth_mode,
                    "action_params": {"subreddit": subreddit, "title": title, "text": body},
                }
            )
        return specs

    raw_targets = config.get("targets") or config.get("target_urls") or []
    targets: list[dict] = []
    if isinstance(raw_targets, list):
        for item in raw_targets:
            if isinstance(item, str) and item.strip():
                url = item.strip()
                targets.append({"url": url, "tweet_id": _extract_tweet_id(url)})
            elif isinstance(item, dict):
                url = str(item.get("url") or item.get("target_url") or "").strip()
                if not url:
                    continue
                tweet_id = str(item.get("tweet_id") or item.get("target_external_id") or "").strip() or _extract_tweet_id(url)
                targets.append({"url": url, "tweet_id": tweet_id or None})

    max_actions = config.get("max_actions")
    if isinstance(max_actions, int) and max_actions > 0:
        targets = targets[: max_actions]

    window_suffix = ""
    if action_type in {"x_reply", "x_quote", "reddit_comment"}:
        window_days = _get_int_from_config(config, "repeat_window_days", default=7, min_value=1, max_value=365)
        window_suffix = f":w{_idempotency_window_key(window_days)}"

    for target in targets:
        tweet_id = target.get("tweet_id") or None
        stable_target = tweet_id or target.get("url")
        if not stable_target:
            continue
        action_params = None
        if action_type in {"x_reply", "x_quote", "reddit_comment"}:
            text = _resolve_action_text(db, workspace_id=account_run.workspace_id, strategy=strategy, allow_llm=True)
            action_params = {"text": text} if text else {}
        specs.append(
            {
                "action_type": action_type,
                "platform_key": account.platform_key,
                "target_url": target.get("url"),
                "target_external_id": tweet_id,
                "idempotency_key": f"{account_run.workspace_id}:{account.id}:{action_type}:{stable_target}:v{strategy.version}{window_suffix}",
                "bandwidth_mode": bandwidth_mode,
                "action_params": action_params or {},
            }
        )

    return specs


def _execute_specs(
    db,
    *,
    account_run: AccountRun,
    run: Run,
    account: SocialAccount,
    strategy: Strategy,
    storage_state: dict,
    specs: list[dict],
) -> tuple[list[Action], list[dict], str | None]:
    actions_to_execute: list[Action] = []
    execute_payload: list[dict] = []
    bandwidth_mode = None
    selected_proxy = None
    selected_proxy_id = None
    content_generation_failed = False

    for spec in specs:
        action = _create_action(db, account_run=account_run, strategy=strategy, account=account, spec=spec)
        if action is None:
            continue
        if action.status in {"succeeded", "skipped"}:
            continue

        action_params = spec.get("action_params") if isinstance(spec.get("action_params"), dict) else {}
        if action.action_type in {"x_reply", "x_quote", "reddit_comment", "x_keyword_repost"}:
            text = str(action_params.get("text") or "").strip()
            if not text:
                content_generation_failed = True
                action.status = "failed"
                action.error_code = "CONTENT_GENERATION_FAILED"
                action.metadata_ = {**(action.metadata_ or {}), "message": "Content generation failed (missing text)"}
                action.finished_at = utc_now()
                db.add(action)
                continue

        actions_to_execute.append(action)
        execute_payload.append(
            {
                "action_type": action.action_type,
                "target_url": action.target_url,
                "target_external_id": action.target_external_id,
                "action_params": action_params,
            }
        )

        if bandwidth_mode is None:
            bandwidth_mode = _normalize_bandwidth_mode(spec.get("bandwidth_mode"))

    if content_generation_failed:
        db.commit()

    if not actions_to_execute:
        return [], [], "CONTENT_GENERATION_FAILED" if content_generation_failed else None

    started_at = utc_now()
    for action in actions_to_execute:
        action.status = "running"
        action.started_at = started_at
        db.add(action)
    db.commit()

    max_proxy_attempts = 1
    if getattr(account, "proxy_pool_id", None):
        max_proxy_attempts = 3

    for attempt in range(max_proxy_attempts):
        results = None
        selected_proxy = None
        selected_proxy_id = None
        if getattr(account, "proxy_pool_id", None):
            try:
                picked = select_proxy_for_account_with_id(
                    db,
                    workspace_id=account_run.workspace_id,
                    account_id=account.id,
                    pool_id=account.proxy_pool_id,
                    attempt=attempt,
                )
                selected_proxy_id = picked.proxy_id
                selected_proxy = picked.to_playwright_proxy()
            except Exception:
                if attempt == 0:
                    finished_at = utc_now()
                    for action in actions_to_execute:
                        action.status = "failed"
                        action.error_code = "PROXY_CONFIG_INVALID"
                        action.finished_at = finished_at
                        db.add(action)
                    db.commit()
                    return actions_to_execute, [], "PROXY_CONFIG_INVALID"
                continue

        if selected_proxy_id:
            for action in actions_to_execute:
                action.metadata_ = {
                    **(action.metadata_ or {}),
                    "proxy": {"proxy_id": str(selected_proxy_id), "server": selected_proxy.get("server") if selected_proxy else None},
                }
                db.add(action)
            db.commit()

        try:
            results = browser_cluster.execute_actions(
                platform_key=account.platform_key,
                storage_state=storage_state,
                actions=execute_payload,
                bandwidth_mode=bandwidth_mode,
                fingerprint_profile=getattr(account, "fingerprint_profile", None) or {},
                proxy=selected_proxy or {},
            )
        except Exception as exc:
            finished_at = utc_now()
            for action in actions_to_execute:
                action.status = "failed"
                action.error_code = "BROWSER_NODE_ERROR"
                action.metadata_ = {**(action.metadata_ or {}), "message": str(exc)}
                action.finished_at = finished_at
                db.add(action)
            db.commit()
            return actions_to_execute, [], "BROWSER_NODE_ERROR"

        if not isinstance(results, list) or len(results) != len(actions_to_execute):
            finished_at = utc_now()
            for action in actions_to_execute:
                action.status = "failed"
                action.error_code = "BROWSER_NODE_ERROR"
                action.metadata_ = {**(action.metadata_ or {}), "message": "Browser node returned mismatched results"}
                action.finished_at = finished_at
                db.add(action)
            db.commit()
            return actions_to_execute, results if isinstance(results, list) else [], "BROWSER_NODE_ERROR"

        if (
            getattr(account, "proxy_pool_id", None)
            and results
            and str(results[0].get("status") or "") == "failed"
            and str(results[0].get("error_code") or "") == "PROXY_FAILED"
            and attempt < max_proxy_attempts - 1
            and selected_proxy_id is not None
        ):
            from app.models.proxy import Proxy as ProxyModel

            proxy_row = db.get(ProxyModel, selected_proxy_id)
            if proxy_row is not None and proxy_row.workspace_id == account_run.workspace_id:
                proxy_row.consecutive_failures = int(proxy_row.consecutive_failures or 0) + 1
                proxy_row.last_error_code = "PROXY_FAILED"
                proxy_row.last_checked_at = utc_now()
                if proxy_row.consecutive_failures >= 3:
                    proxy_row.enabled = False
                db.add(proxy_row)
                db.commit()
            continue

        break

    try:
        if results is None:
            raise RuntimeError("No results from browser node")
    except Exception as exc:
        finished_at = utc_now()
        for action in actions_to_execute:
            action.status = "failed"
            action.error_code = "BROWSER_NODE_ERROR"
            action.metadata_ = {**(action.metadata_ or {}), "message": str(exc)}
            action.finished_at = finished_at
            db.add(action)
        db.commit()
        return actions_to_execute, [], "BROWSER_NODE_ERROR"

    failures: list[tuple[Action, str | None]] = []
    now_finished = utc_now()
    for action, result in zip(actions_to_execute, results, strict=True):
        status_value = str(result.get("status") or "failed")
        error_code = str(result.get("error_code")) if result.get("error_code") else None
        message = str(result.get("message")) if result.get("message") else None
        current_url = str(result.get("current_url")) if result.get("current_url") else None
        screenshot_base64 = str(result.get("screenshot_base64")) if result.get("screenshot_base64") else None
        trace_base64 = str(result.get("trace_base64")) if result.get("trace_base64") else None
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        dom_html = metadata.pop("dom_html", None) if isinstance(metadata, dict) else None

        action.error_code = error_code
        action.metadata_ = {
            **(action.metadata_ or {}),
            "message": message,
            "current_url": current_url,
            "result_metadata": metadata,
        }
        action.finished_at = now_finished
        if status_value == "succeeded":
            action.status = "succeeded"
        elif status_value == "skipped":
            action.status = "skipped"
        else:
            action.status = "failed"
            failures.append((action, error_code))

        if screenshot_base64:
            artifact = _store_screenshot_artifact(action, screenshot_base64)
            if artifact is not None:
                db.add(artifact)

        if action.status == "failed" and trace_base64:
            artifact = _store_trace_artifact(action, trace_base64)
            if artifact is not None:
                db.add(artifact)

        if action.status == "failed" and isinstance(dom_html, str) and dom_html.strip():
            artifact = _store_dom_html_artifact(action, dom_html)
            if artifact is not None:
                db.add(artifact)

        db.add(action)

    if any(err == "ACCOUNT_LOCKED" for _, err in failures):
        account.status = "locked"
        account.last_health_check_at = utc_now()
        db.add(account)
    elif any(err == "CAPTCHA_REQUIRED" for _, err in failures):
        account.status = "needs_login"
        account.last_health_check_at = utc_now()
        db.add(account)
    elif any(err == "AUTH_REQUIRED" for _, err in failures):
        account.status = "needs_login"
        account.last_health_check_at = utc_now()
        db.add(account)

    db.commit()

    if failures:
        cause = next((err for _, err in failures if err and err != "ABORTED"), None) or failures[0][1] or "ACTION_FAILED"
        if content_generation_failed:
            cause = "CONTENT_GENERATION_FAILED"

        if selected_proxy_id and any(err == "PROXY_FAILED" for _, err in failures):
            from app.models.proxy import Proxy as ProxyModel

            proxy_row = db.get(ProxyModel, selected_proxy_id)
            if proxy_row is not None and proxy_row.workspace_id == account_run.workspace_id:
                proxy_row.consecutive_failures = int(proxy_row.consecutive_failures or 0) + 1
                proxy_row.last_error_code = "PROXY_FAILED"
                proxy_row.last_checked_at = utc_now()
                if proxy_row.consecutive_failures >= 3:
                    proxy_row.enabled = False
                db.add(proxy_row)
                db.commit()

        return actions_to_execute, results, cause

    if selected_proxy_id:
        from app.models.proxy import Proxy as ProxyModel

        proxy_row = db.get(ProxyModel, selected_proxy_id)
        if proxy_row is not None and proxy_row.workspace_id == account_run.workspace_id:
            proxy_row.consecutive_failures = 0
            proxy_row.last_error_code = None
            proxy_row.last_checked_at = utc_now()
            db.add(proxy_row)
            db.commit()
    return actions_to_execute, results, "CONTENT_GENERATION_FAILED" if content_generation_failed else None


def _extract_tweet_id(url: str) -> str | None:
    m = _TWEET_ID_RE.search(url)
    if not m:
        return None
    return m.group("tweet_id")


def _normalize_bandwidth_mode(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in {"eco", "balanced", "full"}:
        return normalized
    return None


def _strategy_type(strategy: Strategy) -> str:
    config = strategy.config if isinstance(strategy.config, dict) else {}
    return str(config.get("type") or "").strip().lower()


def _resolve_action_type(action_kind: str) -> str | None:
    kind = str(action_kind or "").strip().lower()
    if kind in {"x_like", "like"}:
        return "x_like"
    if kind in {"x_repost", "x_retweet", "retweet", "repost"}:
        return "x_repost"
    if kind in {"x_reply", "reply", "comment", "x_comment"}:
        return "x_reply"
    if kind in {"x_quote", "quote"}:
        return "x_quote"
    if kind in {"x_publish_post", "x_publish", "publish_post", "publish"}:
        return "x_publish_post"
    if kind in {"x_keyword_repost", "keyword_repost"}:
        return "x_keyword_repost"
    if kind in {"reddit_upvote"}:
        return "reddit_upvote"
    if kind in {"reddit_comment"}:
        return "reddit_comment"
    if kind in {"reddit_post"}:
        return "reddit_post"
    return None


def _strategy_requires_action_text(strategy_type: str) -> bool:
    kind = str(strategy_type or "").strip().lower()
    return kind.endswith("reply") or kind.endswith("comment") or kind.endswith("quote")


def _strategy_has_publish_content(strategy: Strategy) -> bool:
    config = strategy.config if isinstance(strategy.config, dict) else {}
    if _resolve_media_urls(config):
        return True
    return bool(_resolve_publish_texts(strategy))


def _resolve_action_text(
    db,
    *,
    workspace_id: uuid.UUID,
    strategy: Strategy,
    allow_llm: bool = False,
) -> str | None:
    config = strategy.config if isinstance(strategy.config, dict) else {}
    kind = _strategy_type(strategy)
    use_llm = _should_use_llm(config)

    prompt_stack_keys: list[str] = []
    if kind.endswith("quote") or kind in {"x_quote", "quote"}:
        prompt_stack_keys = ["quote_prompt_stack_key", "prompt_stack_key"]
    elif kind.endswith("reply") or kind.endswith("comment") or kind in {"x_reply", "reply", "comment", "x_comment"}:
        prompt_stack_keys = ["reply_prompt_stack_key", "prompt_stack_key"]
    else:
        prompt_stack_keys = ["prompt_stack_key"]

    if use_llm:
        llm_row = get_workspace_llm_config(db, workspace_id=workspace_id)
        if llm_row is None:
            return None
        picked_key = next(
            (
                str(config.get(key_name)).strip()
                for key_name in prompt_stack_keys
                if isinstance(config.get(key_name), str) and str(config.get(key_name)).strip()
            ),
            None,
        )
        if not picked_key:
            return None
        row = db.scalar(select(PromptStack).where(PromptStack.workspace_id == workspace_id, PromptStack.key == picked_key))
        if row is None:
            return None
        payload = row.payload if isinstance(row.payload, dict) else {}
        prompt = generate_prompt_from_stack(payload)
        if not prompt.strip():
            return None
        if not allow_llm:
            return prompt.strip()
        try:
            system, temperature, max_tokens = _resolve_llm_params(config)
            generated = llm_generate_text(
                db,
                workspace_id=workspace_id,
                prompt=prompt,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception:
            return None
        cleaned = _sanitize_generated_text(generated)
        cleaned = _enforce_text_limits(cleaned, kind=kind, config=config)
        return cleaned or None

    for key_name in prompt_stack_keys:
        raw_key = config.get(key_name)
        if isinstance(raw_key, str) and raw_key.strip():
            stack_key = raw_key.strip()
            row = db.scalar(select(PromptStack).where(PromptStack.workspace_id == workspace_id, PromptStack.key == stack_key))
            if row is None:
                return None
            payload = row.payload if isinstance(row.payload, dict) else {}
            generated = generate_prompt_from_stack(payload)
            if generated.strip():
                return generated.strip()
            return None

    if kind.endswith("quote") or kind in {"x_quote", "quote"}:
        string_keys = ["quote_text", "text"]
        list_keys = ["quote_texts", "texts"]
    elif kind.endswith("reply") or kind.endswith("comment") or kind in {"x_reply", "reply", "comment", "x_comment"}:
        string_keys = ["reply_text", "text"]
        list_keys = ["reply_texts", "texts"]
    else:
        string_keys = ["text"]
        list_keys = ["texts"]

    for key in string_keys:
        raw = config.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()

    for key in list_keys:
        raw_list = config.get(key)
        if isinstance(raw_list, list):
            cleaned = [str(item).strip() for item in raw_list if str(item).strip()]
            if cleaned:
                return random.choice(cleaned)

    return None


def _should_use_llm(config: dict) -> bool:
    return bool(config.get("use_llm") is True or config.get("llm_enabled") is True)


def _resolve_llm_params(config: dict) -> tuple[str | None, float | None, int | None]:
    system = str(config.get("llm_system") or "").strip() or None
    if system is None:
        system = "只输出最终要发布的文本，不要解释，不要使用 markdown，不要输出 JSON。"

    temperature = None
    if config.get("llm_temperature") is not None:
        try:
            temperature = float(config.get("llm_temperature"))
        except Exception:
            temperature = None

    max_tokens = None
    if config.get("llm_max_tokens") is not None:
        try:
            max_tokens = int(config.get("llm_max_tokens"))
        except Exception:
            max_tokens = None

    return system, temperature, max_tokens


def _sanitize_generated_text(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    if cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = cleaned.strip("`").strip()
    cleaned = cleaned.strip().strip('"').strip("'").strip("“”").strip("‘’").strip()
    return cleaned


def _enforce_text_limits(text: str, *, kind: str, config: dict) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""

    max_chars = None
    if config.get("max_chars") is not None:
        try:
            max_chars = int(config.get("max_chars"))
        except Exception:
            max_chars = None
    elif kind.startswith("x_"):
        max_chars = 240

    if max_chars is not None and max_chars > 0 and len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip()
    return cleaned


def _resolve_publish_texts(strategy: Strategy) -> list[str]:
    config = strategy.config if isinstance(strategy.config, dict) else {}
    raw = config.get("texts") or config.get("post_texts")
    if isinstance(raw, list):
        cleaned = [str(item).strip() for item in raw if str(item).strip()]
        if cleaned:
            return cleaned
    raw_single = config.get("text") or config.get("post_text")
    if isinstance(raw_single, str) and raw_single.strip():
        return [raw_single.strip()]
    return []


def _resolve_media_urls(config: dict) -> list[str]:
    raw = config.get("media_urls") or config.get("media") or []
    urls: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            url = str(item or "").strip()
            if url:
                urls.append(url)
    return urls[:4]


def _stable_content_key(*, text: str, media_urls: list[str]) -> str:
    normalized_text = (text or "").strip()
    normalized_media = [str(u).strip() for u in media_urls if str(u).strip()]
    payload = f"{normalized_text}\n" + "\n".join(normalized_media)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _idempotency_window_key(window_days: int) -> str:
    now = utc_now()
    if window_days <= 1:
        return now.date().isoformat()
    if window_days == 7:
        iso = now.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    if window_days in {28, 29, 30, 31}:
        return f"{now.year}-{now.month:02d}"

    epoch = date(1970, 1, 1)
    days_since_epoch = (now.date() - epoch).days
    index = days_since_epoch // window_days
    window_start = epoch + timedelta(days=index * window_days)
    return window_start.isoformat()


def _build_search_collect_specs(
    db, strategy: Strategy, *, account_run: AccountRun, account: SocialAccount, run: Run
) -> list[dict]:
    config = strategy.config if isinstance(strategy.config, dict) else {}
    bandwidth_mode = config.get("bandwidth_mode")
    specs = _build_action_specs(db, strategy, account_run=account_run, account=account)

    strategy_type = _strategy_type(strategy)
    verified_only = bool(config.get("verified_only") is True or strategy_type.startswith("x_verified_"))

    query = _resolve_search_query(config)
    if not query:
        specs.append(
            {
                "action_type": "x_search_collect",
                "platform_key": "x",
                "target_url": None,
                "target_external_id": None,
                "idempotency_key": f"{account_run.workspace_id}:{account.id}:x_search_collect:{run.id}",
                "bandwidth_mode": bandwidth_mode,
                "action_params": {"max_candidates": 0, "scroll_limit": 0},
            }
        )
        return specs

    if verified_only and "filter:verified" not in query.lower():
        query = f"{query} filter:verified"

    search_mode = str(config.get("search_mode") or "live")
    search_mode = _resolve_search_mode_from_schedule(db, run=run, default=search_mode)
    search_url = _build_x_search_url(query=query, search_mode=search_mode)
    max_candidates = _get_int_from_config(config, "max_candidates", default=20, min_value=1, max_value=200)
    scroll_limit = _get_int_from_config(config, "scroll_limit", default=6, min_value=0, max_value=50)
    verified_only_dom = verified_only

    specs.append(
        {
            "action_type": "x_search_collect",
            "platform_key": "x",
            "target_url": search_url,
            "target_external_id": None,
            "idempotency_key": f"{account_run.workspace_id}:{account.id}:x_search_collect:{run.id}",
            "bandwidth_mode": bandwidth_mode,
            "action_params": {
                "max_candidates": max_candidates,
                "scroll_limit": scroll_limit,
                "verified_only_dom": verified_only_dom,
            },
            "metadata": {"search_mode": search_mode},
        }
    )
    return specs


def _extract_candidates(executed_actions: list[Action], results: list[dict]) -> list[dict]:
    candidates: list[dict] = []
    for action, result in zip(executed_actions, results, strict=True):
        if action.action_type != "x_search_collect":
            continue
        meta = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        raw = meta.get("candidates")
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    candidates.append(item)
        break
    return candidates


def _build_search_action_specs(
    db,
    strategy: Strategy,
    *,
    account_run: AccountRun,
    account: SocialAccount,
    candidates: list[dict],
) -> list[dict]:
    config = strategy.config if isinstance(strategy.config, dict) else {}
    bandwidth_mode = config.get("bandwidth_mode")

    action_kind = _strategy_type(strategy)
    action_type: str
    if action_kind.endswith("like"):
        action_type = "x_like"
    elif action_kind.endswith("repost") or action_kind.endswith("retweet"):
        action_type = "x_repost"
    elif action_kind.endswith("reply") or action_kind.endswith("comment"):
        action_type = "x_reply"
    elif action_kind.endswith("quote"):
        action_type = "x_quote"
    else:
        return []
    max_actions = _get_int_from_config(config, "max_actions", default=3, min_value=1, max_value=50)
    verified_only = bool(config.get("verified_only") is True or action_kind.startswith("x_verified_"))
    recency_hours = _optional_int(config, "recency_hours")
    min_like_count = _optional_int(config, "min_like_count")
    min_reply_count = _optional_int(config, "min_reply_count")
    min_view_count = _optional_int(config, "min_view_count")
    now = utc_now()

    random.shuffle(candidates)
    picked: list[dict] = []
    for cand in candidates:
        if len(picked) >= max_actions:
            break
        if not isinstance(cand, dict):
            continue

        if recency_hours is not None and recency_hours > 0:
            ts_raw = cand.get("timestamp")
            ts = _parse_iso_datetime(str(ts_raw)) if ts_raw else None
            if ts is None:
                continue
            if ts < now - timedelta(hours=recency_hours):
                continue

        if min_like_count is not None and _safe_int(cand.get("like_count")) < min_like_count:
            continue
        if min_reply_count is not None and _safe_int(cand.get("reply_count")) < min_reply_count:
            continue
        if min_view_count is not None and _safe_int(cand.get("view_count")) < min_view_count:
            continue

        tweet_id = str(cand.get("tweet_id") or "").strip() or None
        url = str(cand.get("url") or "").strip() or None
        if not tweet_id and not url:
            continue
        if verified_only and cand.get("is_verified") is False:
            continue
        picked.append({"tweet_id": tweet_id, "url": url})

    specs: list[dict] = []
    window_suffix = ""
    if action_type in {"x_reply", "x_quote"}:
        window_days = _get_int_from_config(config, "repeat_window_days", default=7, min_value=1, max_value=365)
        window_suffix = f":w{_idempotency_window_key(window_days)}"

    for item in picked:
        tweet_id = item.get("tweet_id") or None
        url = item.get("url") or None
        stable_target = tweet_id or url
        if not stable_target:
            continue
        action_params = None
        if action_type in {"x_reply", "x_quote"}:
            text = _resolve_action_text(db, workspace_id=account_run.workspace_id, strategy=strategy, allow_llm=True)
            action_params = {"text": text} if text else {}
        specs.append(
            {
                "action_type": action_type,
                "platform_key": "x",
                "target_url": url,
                "target_external_id": tweet_id,
                "idempotency_key": f"{account_run.workspace_id}:{account.id}:{action_type}:{stable_target}:v{strategy.version}{window_suffix}",
                "bandwidth_mode": bandwidth_mode,
                "action_params": action_params or {},
            }
        )
    return specs


def _build_keyword_repost_specs(
    db,
    strategy: Strategy,
    *,
    account_run: AccountRun,
    account: SocialAccount,
    run: Run,
    candidates: list[dict],
) -> list[dict]:
    config = strategy.config if isinstance(strategy.config, dict) else {}
    bandwidth_mode = config.get("bandwidth_mode")

    stack_key = _resolve_keyword_repost_prompt_stack_key(config)
    if stack_key is None:
        default_row = db.scalar(
            select(PromptStack).where(PromptStack.workspace_id == account_run.workspace_id, PromptStack.key == "keyword_repost")
        )
        if default_row is not None:
            stack_key = "keyword_repost"

    prompt_template = str(config.get("prompt") or "").strip() or None
    if stack_key is not None:
        row = db.scalar(select(PromptStack).where(PromptStack.workspace_id == account_run.workspace_id, PromptStack.key == stack_key))
        if row is None:
            return []
        payload = row.payload if isinstance(row.payload, dict) else {}
        generated = generate_prompt_from_stack(payload)
        prompt_template = generated.strip() or prompt_template

    use_llm = _should_use_llm(config)
    if use_llm and get_workspace_llm_config(db, workspace_id=account_run.workspace_id) is None:
        return []

    max_actions = _get_int_from_config(config, "max_actions", default=1, min_value=1, max_value=10)
    window_days = _get_int_from_config(config, "repeat_window_days", default=7, min_value=1, max_value=365)
    window_suffix = f":w{_idempotency_window_key(window_days)}"
    now = utc_now()

    recency_hours = _optional_int(config, "recency_hours")
    min_like_count = _optional_int(config, "min_like_count")
    min_reply_count = _optional_int(config, "min_reply_count")
    min_view_count = _optional_int(config, "min_view_count")

    max_media_bytes = _get_int_from_config(config, "max_media_bytes", default=150 * 1024, min_value=10 * 1024, max_value=5 * 1024 * 1024)
    max_download_bytes = _get_int_from_config(config, "max_download_bytes", default=5 * 1024 * 1024, min_value=100 * 1024, max_value=20 * 1024 * 1024)
    compose_url = str(config.get("compose_url") or "https://x.com/compose/post").strip()
    media_urls = _resolve_media_urls(config)

    random.shuffle(candidates)
    specs: list[dict] = []
    for cand in candidates:
        if len(specs) >= max_actions:
            break
        if not isinstance(cand, dict):
            continue

        source_text = str(cand.get("text") or "").strip()
        if not source_text:
            continue

        if recency_hours is not None and recency_hours > 0:
            ts_raw = cand.get("timestamp")
            ts = _parse_iso_datetime(str(ts_raw)) if ts_raw else None
            if ts is None:
                continue
            if ts < now - timedelta(hours=recency_hours):
                continue

        if min_like_count is not None and _safe_int(cand.get("like_count")) < min_like_count:
            continue
        if min_reply_count is not None and _safe_int(cand.get("reply_count")) < min_reply_count:
            continue
        if min_view_count is not None and _safe_int(cand.get("view_count")) < min_view_count:
            continue

        tweet_id = str(cand.get("tweet_id") or "").strip() or None
        url = str(cand.get("url") or "").strip() or None
        stable_target = tweet_id or url
        if not stable_target:
            continue

        template = prompt_template or "请将下面的内容改写成一条新的推文，表达自然、避免抄袭，只输出最终推文。"
        rendered = _render_template(
            template,
            {
                "source_text": source_text,
                "source_url": url or "",
                "source_tweet_id": tweet_id or "",
            },
        )

        final_text = rendered.strip()
        if use_llm:
            full_prompt = rendered
            if "{{source_text}}" not in template:
                full_prompt = f"{rendered}\n\n原文：\n{source_text}"
            try:
                system, temperature, max_tokens = _resolve_llm_params(config)
                generated = llm_generate_text(
                    db,
                    workspace_id=account_run.workspace_id,
                    prompt=full_prompt,
                    system=system,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception:
                continue
            final_text = _sanitize_generated_text(generated)

        final_text = _enforce_text_limits(final_text, kind="x_keyword_repost", config=config)
        if not final_text:
            continue

        specs.append(
            {
                "action_type": "x_keyword_repost",
                "platform_key": "x",
                "target_url": url,
                "target_external_id": tweet_id,
                "idempotency_key": f"{account_run.workspace_id}:{account.id}:x_keyword_repost:{stable_target}:v{strategy.version}{window_suffix}",
                "bandwidth_mode": bandwidth_mode,
                "action_params": {
                    "text": final_text,
                    "media_urls": media_urls,
                    "max_media_bytes": max_media_bytes,
                    "max_download_bytes": max_download_bytes,
                    "compose_url": compose_url,
                },
                "metadata": {
                    "source": {
                        "tweet_id": tweet_id,
                        "url": url,
                        "is_verified": cand.get("is_verified"),
                        "like_count": cand.get("like_count"),
                        "reply_count": cand.get("reply_count"),
                        "view_count": cand.get("view_count"),
                    }
                },
            }
        )

    return specs


def _resolve_keyword_repost_prompt_stack_key(config: dict) -> str | None:
    for key in ["keyword_repost_prompt_stack_key", "keyword_repost_stack_key", "prompt_stack_key"]:
        raw = config.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _render_template(template: str, values: dict[str, str]) -> str:
    rendered = str(template or "")
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _resolve_search_query(config: dict) -> str | None:
    query = str(config.get("query") or "").strip()
    if query:
        return query

    keywords = config.get("keywords")
    if isinstance(keywords, list):
        cleaned = [str(item).strip() for item in keywords if str(item).strip()]
        if cleaned:
            base = random.choice(cleaned)
            if config.get("verified_only") is True:
                base = f"{base} filter:verified"
            return base

    return None


def _build_x_search_url(*, query: str, search_mode: str) -> str:
    mode = search_mode.strip().lower()
    f_value = "live" if mode in {"live", "latest"} else "top"
    q_value = urllib.parse.quote(query, safe="")
    return f"https://x.com/search?q={q_value}&src=typed_query&f={f_value}"


def _resolve_search_mode_from_schedule(db, *, run: Run, default: str) -> str:
    if run.schedule_id is None:
        return default
    schedule = db.get(Schedule, run.schedule_id)
    if schedule is None or schedule.workspace_id != run.workspace_id:
        return default
    random_config = schedule.random_config if isinstance(schedule.random_config, dict) else {}
    if random_config.get("enabled") is False:
        return default

    override = (
        random_config.get("random_search_type")
        or random_config.get("random_search_mode")
        or random_config.get("search_mode")
        or random_config.get("search_type")
    )
    if isinstance(override, str) and override.strip():
        mode = override.strip().lower()
        if mode in {"top", "live", "latest"}:
            return mode
        if mode in {"random", "auto"}:
            return _weighted_random_search_mode(random_config)

    if override is True or random_config.get("randomize_search_type") is True:
        return _weighted_random_search_mode(random_config)

    return default


def _weighted_random_search_mode(random_config: dict) -> str:
    top_p = _optional_int(random_config, "search_type_top_probability")
    live_p = _optional_int(random_config, "search_type_live_probability")
    if top_p is None:
        top_p = 50
    if live_p is None:
        live_p = 50

    total = max(0, top_p) + max(0, live_p)
    if total <= 0:
        return random.choice(["top", "live"])
    pick = random.randint(1, total)
    return "top" if pick <= top_p else "live"


def _get_int_from_config(config: dict, key: str, *, default: int, min_value: int, max_value: int) -> int:
    raw = config.get(key, default)
    try:
        value = int(raw)
    except Exception:
        value = default
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def _optional_int(config: dict, key: str) -> int | None:
    raw = config.get(key)
    if raw is None:
        return None
    try:
        return max(0, int(raw))
    except Exception:
        return None


def _safe_int(value: object) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except Exception:
        return 0


def _parse_iso_datetime(raw: str) -> datetime | None:
    value = str(raw or "").strip()
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _create_action(
    db,
    *,
    account_run: AccountRun,
    strategy: Strategy,
    account: SocialAccount,
    spec: dict,
) -> Action | None:
    idempotency_key = str(spec.get("idempotency_key") or "").strip()
    if not idempotency_key:
        return None

    existing = db.scalar(select(Action).where(Action.workspace_id == account_run.workspace_id, Action.idempotency_key == idempotency_key))
    if existing is not None:
        return existing

    extra_meta = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
    action = Action(
        workspace_id=account_run.workspace_id,
        account_run_id=account_run.id,
        action_type=str(spec.get("action_type") or "").strip()[:32],
        platform_key=str(spec.get("platform_key") or account.platform_key).strip().lower()[:32],
        target_external_id=str(spec.get("target_external_id")).strip()[:200] if spec.get("target_external_id") else None,
        target_url=str(spec.get("target_url")).strip()[:1000] if spec.get("target_url") else None,
        idempotency_key=idempotency_key[:500],
        status="queued",
        error_code=None,
        metadata_={"strategy_id": str(strategy.id), "strategy_version": strategy.version, **extra_meta},
        started_at=None,
        finished_at=None,
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def _store_screenshot_artifact(action: Action, screenshot_base64: str) -> Artifact | None:
    try:
        payload = base64.b64decode(screenshot_base64, validate=True)
    except Exception:
        return None

    workspace_prefix = str(action.workspace_id)
    storage_key = f"{workspace_prefix}/{action.id}-screenshot.png"

    base_dir = Path(settings.artifacts_dir)
    path = base_dir / storage_key
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    except Exception:
        return None

    return Artifact(
        workspace_id=action.workspace_id,
        action_id=action.id,
        type="screenshot",
        storage_key=storage_key,
        size=len(payload),
    )


def _store_dom_html_artifact(action: Action, dom_html: str) -> Artifact | None:
    try:
        payload = str(dom_html).encode("utf-8", errors="replace")
    except Exception:
        return None

    workspace_prefix = str(action.workspace_id)
    storage_key = f"{workspace_prefix}/{action.id}-dom.html"

    base_dir = Path(settings.artifacts_dir)
    path = base_dir / storage_key
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    except Exception:
        return None

    return Artifact(
        workspace_id=action.workspace_id,
        action_id=action.id,
        type="dom",
        storage_key=storage_key,
        size=len(payload),
    )


def _store_trace_artifact(action: Action, trace_base64: str) -> Artifact | None:
    try:
        payload = base64.b64decode(trace_base64, validate=True)
    except Exception:
        return None

    workspace_prefix = str(action.workspace_id)
    storage_key = f"{workspace_prefix}/{action.id}-trace.zip"

    base_dir = Path(settings.artifacts_dir)
    path = base_dir / storage_key
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    except Exception:
        return None

    return Artifact(
        workspace_id=action.workspace_id,
        action_id=action.id,
        type="trace",
        storage_key=storage_key,
        size=len(payload),
    )
