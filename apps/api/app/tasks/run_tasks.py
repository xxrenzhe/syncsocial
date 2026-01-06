from __future__ import annotations

import base64
import random
import re
import uuid
import urllib.parse
from pathlib import Path

from sqlalchemy import select

from app.celery_app import celery_app
from app.core.config import settings
from app.core.crypto import decrypt_json
from app.db.session import SessionLocal
from app.models.account_run import AccountRun
from app.models.action import Action
from app.models.artifact import Artifact
from app.models.credential import Credential
from app.models.run import Run
from app.models.social_account import SocialAccount
from app.models.strategy import Strategy
from app.services.browser_cluster import browser_cluster
from app.utils.time import utc_now

_TWEET_ID_RE = re.compile(r"/status/(?P<tweet_id>\\d+)")


@celery_app.task(name="syncsocial.execute_account_run")
def execute_account_run(account_run_id: str) -> None:
    account_run_uuid = uuid.UUID(account_run_id)
    now = utc_now()

    with SessionLocal() as db:
        account_run = db.get(AccountRun, account_run_uuid)
        if account_run is None:
            return
        if account_run.status not in {"queued", "retry_waiting"}:
            return

        run = db.get(Run, account_run.run_id)
        if run is None:
            return

        strategy = db.get(Strategy, run.strategy_id)
        if strategy is None:
            _fail_account_run(db, account_run, run, error_code="STRATEGY_NOT_FOUND")
            return

        account_run.status = "running"
        account_run.started_at = now
        db.add(account_run)

        if run.status == "queued":
            run.status = "running"
            run.started_at = now
            db.add(run)

        db.commit()

        account = db.get(SocialAccount, account_run.social_account_id)
        if account is None:
            _fail_account_run(db, account_run, run, error_code="ACCOUNT_NOT_FOUND")
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
        if strategy_type in {"x_search_like", "x_search_repost", "x_verified_like", "x_verified_repost"}:
            search_specs = _build_search_collect_specs(strategy, account_run=account_run, account=account, run=run)
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
                _fail_account_run(db, account_run, run, error_code=error_code)
                return

            candidates = _extract_candidates(executed_actions, results)
            if not candidates:
                account_run.status = "succeeded"
                account_run.finished_at = utc_now()
                db.add(account_run)
                db.commit()
                _finalize_run_if_done(db, run.id)
                return

            action_specs = _build_search_action_specs(
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
                _fail_account_run(db, account_run, run, error_code=action_error)
                return
        else:
            action_specs = _build_action_specs(strategy, account_run=account_run, account=account)
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
                _fail_account_run(db, account_run, run, error_code=error_code)
                return

        account_run.status = "succeeded"
        account_run.finished_at = utc_now()
        db.add(account_run)
        db.commit()

        _finalize_run_if_done(db, run.id)


def _fail_account_run(db, account_run: AccountRun, run: Run, *, error_code: str) -> None:
    account_run.status = "failed"
    account_run.error_code = error_code
    account_run.finished_at = utc_now()
    db.add(account_run)
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


def _build_action_specs(strategy: Strategy, *, account_run: AccountRun, account: SocialAccount) -> list[dict]:
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
    if account.platform_key != "x":
        return specs
    if action_kind not in {"x_like", "like", "x_repost", "x_retweet", "retweet", "repost"}:
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

    for target in targets:
        tweet_id = target.get("tweet_id") or None
        stable_target = tweet_id or target.get("url")
        if not stable_target:
            continue
        action_type = "x_like" if action_kind in {"x_like", "like"} else "x_repost"
        specs.append(
            {
                "action_type": action_type,
                "platform_key": "x",
                "target_url": target.get("url"),
                "target_external_id": tweet_id,
                "idempotency_key": f"{account_run.workspace_id}:{account.id}:{action_type}:{stable_target}:v{strategy.version}",
                "bandwidth_mode": bandwidth_mode,
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

    for spec in specs:
        action = _create_action(db, account_run=account_run, strategy=strategy, account=account, spec=spec)
        if action is None:
            continue
        if action.status in {"succeeded", "skipped"}:
            continue

        actions_to_execute.append(action)
        action_params = spec.get("action_params") if isinstance(spec.get("action_params"), dict) else {}
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

    if not actions_to_execute:
        return [], [], None

    started_at = utc_now()
    for action in actions_to_execute:
        action.status = "running"
        action.started_at = started_at
        db.add(action)
    db.commit()

    try:
        results = browser_cluster.execute_actions(
            platform_key=account.platform_key,
            storage_state=storage_state,
            actions=execute_payload,
            bandwidth_mode=bandwidth_mode,
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

    if len(results) != len(actions_to_execute):
        finished_at = utc_now()
        for action in actions_to_execute:
            action.status = "failed"
            action.error_code = "BROWSER_NODE_ERROR"
            action.metadata_ = {**(action.metadata_ or {}), "message": "Browser node returned mismatched results"}
            action.finished_at = finished_at
            db.add(action)
        db.commit()
        return actions_to_execute, results if isinstance(results, list) else [], "BROWSER_NODE_ERROR"

    failures: list[tuple[Action, str | None]] = []
    now_finished = utc_now()
    for action, result in zip(actions_to_execute, results, strict=True):
        status_value = str(result.get("status") or "failed")
        error_code = str(result.get("error_code")) if result.get("error_code") else None
        message = str(result.get("message")) if result.get("message") else None
        current_url = str(result.get("current_url")) if result.get("current_url") else None
        screenshot_base64 = str(result.get("screenshot_base64")) if result.get("screenshot_base64") else None
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}

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

        db.add(action)

    if any(err == "AUTH_REQUIRED" for _, err in failures):
        account.status = "needs_login"
        account.last_health_check_at = utc_now()
        db.add(account)

    db.commit()

    if failures:
        cause = next((err for _, err in failures if err and err != "ABORTED"), None) or failures[0][1] or "ACTION_FAILED"
        return actions_to_execute, results, cause
    return actions_to_execute, results, None


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


def _build_search_collect_specs(
    strategy: Strategy, *, account_run: AccountRun, account: SocialAccount, run: Run
) -> list[dict]:
    config = strategy.config if isinstance(strategy.config, dict) else {}
    bandwidth_mode = config.get("bandwidth_mode")
    specs = _build_action_specs(strategy, account_run=account_run, account=account)

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

    search_url = _build_x_search_url(query=query, search_mode=str(config.get("search_mode") or "live"))
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
    strategy: Strategy,
    *,
    account_run: AccountRun,
    account: SocialAccount,
    candidates: list[dict],
) -> list[dict]:
    config = strategy.config if isinstance(strategy.config, dict) else {}
    bandwidth_mode = config.get("bandwidth_mode")

    action_kind = _strategy_type(strategy)
    action_type = "x_like" if action_kind.endswith("like") else "x_repost"
    max_actions = _get_int_from_config(config, "max_actions", default=3, min_value=1, max_value=50)
    verified_only = bool(config.get("verified_only") is True or action_kind.startswith("x_verified_"))

    random.shuffle(candidates)
    picked: list[dict] = []
    for cand in candidates:
        if len(picked) >= max_actions:
            break
        if not isinstance(cand, dict):
            continue
        tweet_id = str(cand.get("tweet_id") or "").strip() or None
        url = str(cand.get("url") or "").strip() or None
        if not tweet_id and not url:
            continue
        if verified_only and cand.get("is_verified") is False:
            continue
        picked.append({"tweet_id": tweet_id, "url": url})

    specs: list[dict] = []
    for item in picked:
        tweet_id = item.get("tweet_id") or None
        url = item.get("url") or None
        stable_target = tweet_id or url
        if not stable_target:
            continue
        specs.append(
            {
                "action_type": action_type,
                "platform_key": "x",
                "target_url": url,
                "target_external_id": tweet_id,
                "idempotency_key": f"{account_run.workspace_id}:{account.id}:{action_type}:{stable_target}:v{strategy.version}",
                "bandwidth_mode": bandwidth_mode,
            }
        )
    return specs


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
        metadata_={"strategy_id": str(strategy.id), "strategy_version": strategy.version},
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
