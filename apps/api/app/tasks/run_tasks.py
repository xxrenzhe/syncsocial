from __future__ import annotations

import re
import uuid

from sqlalchemy import select

from app.celery_app import celery_app
from app.core.crypto import decrypt_json
from app.db.session import SessionLocal
from app.models.account_run import AccountRun
from app.models.action import Action
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

        action_specs = _build_action_specs(strategy, account_run=account_run, account=account)
        for spec in action_specs:
            action = _create_action(db, account_run=account_run, strategy=strategy, account=account, spec=spec)
            if action is None:
                continue

            if action.status in {"succeeded", "skipped"}:
                continue

            action.status = "running"
            action.started_at = utc_now()
            db.add(action)
            db.commit()
            db.refresh(action)

            result = browser_cluster.execute_action(
                platform_key=account.platform_key,
                action_type=action.action_type,
                storage_state=storage_state,
                target_url=action.target_url,
                target_external_id=action.target_external_id,
                bandwidth_mode=_normalize_bandwidth_mode(spec.get("bandwidth_mode")),
            )

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
                "screenshot_base64": screenshot_base64,
                "result_metadata": metadata,
            }
            action.finished_at = utc_now()
            if status_value == "succeeded":
                action.status = "succeeded"
            elif status_value == "skipped":
                action.status = "skipped"
            else:
                action.status = "failed"

            db.add(action)
            db.commit()

            if action.error_code == "AUTH_REQUIRED":
                account.status = "needs_login"
                account.last_health_check_at = utc_now()
                db.add(account)
                db.commit()

            if action.status == "failed":
                _fail_account_run(db, account_run, run, error_code=action.error_code or "ACTION_FAILED")
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
