from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models.prompt_stack import PromptStack
from app.models.strategy import Strategy
from app.models.user import User
from app.platforms.registry import get_login_adapter
from app.platforms.registry import list_supported_platforms
from app.schemas.strategy import CreateStrategyRequest, StrategyPublic, StrategyValidateResponse, UpdateStrategyRequest
from app.services.llm_gateway import get_workspace_llm_config

router = APIRouter()


@router.get("", response_model=list[StrategyPublic])
def list_strategies(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[StrategyPublic]:
    rows = (
        db.scalars(select(Strategy).where(Strategy.workspace_id == user.workspace_id).order_by(Strategy.created_at.desc()))
        .all()
    )
    return [StrategyPublic.model_validate(row, from_attributes=True) for row in rows]


@router.get("/{strategy_id}", response_model=StrategyPublic)
def get_strategy(
    strategy_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategyPublic:
    row = db.get(Strategy, strategy_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return StrategyPublic.model_validate(row, from_attributes=True)


@router.post("", response_model=StrategyPublic, status_code=status.HTTP_201_CREATED)
def create_strategy(
    payload: CreateStrategyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategyPublic:
    platform_key = payload.platform_key.strip().lower()
    if not platform_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid platform_key")
    try:
        get_login_adapter(platform_key)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported platform_key") from None

    row = Strategy(workspace_id=user.workspace_id, name=payload.name, platform_key=platform_key, version=1, config=payload.config)
    db.add(row)
    db.commit()
    db.refresh(row)
    return StrategyPublic.model_validate(row, from_attributes=True)


@router.patch("/{strategy_id}", response_model=StrategyPublic)
def update_strategy(
    strategy_id: uuid.UUID,
    payload: UpdateStrategyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategyPublic:
    row = db.get(Strategy, strategy_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    if payload.name is not None:
        row.name = payload.name
    if payload.config is not None:
        row.config = payload.config
        row.version += 1

    db.add(row)
    db.commit()
    db.refresh(row)
    return StrategyPublic.model_validate(row, from_attributes=True)


@router.post("/{strategy_id}/validate", response_model=StrategyValidateResponse)
def validate_strategy(
    strategy_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StrategyValidateResponse:
    row = db.get(Strategy, strategy_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    config = row.config if isinstance(row.config, dict) else {}
    kind = str(config.get("type") or "").strip().lower()
    if not kind:
        return StrategyValidateResponse(ok=False, errors=["Missing config.type"])

    platforms = list_supported_platforms()
    platform = next((p for p in platforms if str(p.get("platform_key") or "").strip().lower() == row.platform_key), None)
    caps = set(platform.get("capabilities") or []) if isinstance(platform, dict) else set()

    def require(capability: str, errors: list[str]) -> None:
        if capability not in caps:
            errors.append(f"Missing capability: {capability}")

    errors: list[str] = []
    warnings: list[str] = []

    is_original_posts = kind in {"original_posts", "original_post", "x_original_post"}
    is_keyword_rewrite = kind in {"keyword_repost", "x_keyword_repost"}
    is_competitor_rewrite = kind in {
        "competitor_repost",
        "competitor_repost_as_original",
        "x_competitor_repost",
        "x_competitor_repost_as_original",
    }

    if kind.startswith(("x_search_", "x_verified_", "keyword_")) or is_keyword_rewrite:
        require("SOURCE_KEYWORD_SEARCH", errors)
    if kind.startswith(("x_profile_", "x_competitor_")) or is_competitor_rewrite:
        require("SOURCE_PROFILE", errors)
    if kind.startswith("x_community_"):
        require("SOURCE_COMMUNITY", errors)
    if kind.startswith("x_feed_"):
        require("SOURCE_FEED", errors)
    if kind.startswith("x_verified_"):
        require("TARGET_VERIFIED_ONLY", errors)

    if "publish_post" in kind or kind == "reddit_post" or is_original_posts or is_keyword_rewrite or is_competitor_rewrite:
        require("PUBLISH_POST", errors)
    if ("like" in kind) or ("upvote" in kind):
        require("ENGAGE_LIKE", errors)
    if ("reply" in kind) or ("comment" in kind):
        require("ENGAGE_COMMENT", errors)
    if (("repost" in kind) or ("retweet" in kind)) and not (is_keyword_rewrite or is_competitor_rewrite):
        require("ENGAGE_REPOST", errors)
    if "quote" in kind:
        require("ENGAGE_QUOTE", errors)

    def has_nonempty_list(value: object) -> bool:
        return isinstance(value, list) and any(str(item).strip() for item in value)

    def has_nonempty_string(value: object) -> bool:
        return isinstance(value, str) and value.strip() != ""

    def require_source_query() -> None:
        if has_nonempty_string(config.get("query")):
            return
        if has_nonempty_list(config.get("keywords")):
            return
        errors.append("Missing query/keywords for keyword search source")

    def require_profile_source() -> None:
        keys = [
            "profile_url",
            "profile",
            "handle",
            "handles",
            "profile_urls",
            "profile_handles",
            "competitor_profiles",
            "competitor_handles",
        ]
        if any(has_nonempty_string(config.get(k)) or has_nonempty_list(config.get(k)) for k in keys):
            return
        errors.append("Missing handle/profile for profile source")

    def require_community_source() -> None:
        keys = ["community_id", "community_ids", "community_url", "community_urls", "communities"]
        if any(has_nonempty_string(config.get(k)) or has_nonempty_list(config.get(k)) for k in keys):
            return
        errors.append("Missing community_id/community_url for community source")

    if kind.startswith(("x_search_", "x_verified_", "keyword_")) or is_keyword_rewrite:
        require_source_query()
    if kind.startswith(("x_profile_", "x_competitor_")) or is_competitor_rewrite:
        require_profile_source()
    if kind.startswith("x_community_"):
        require_community_source()

    use_llm = bool(config.get("use_llm") is True or config.get("llm_enabled") is True)
    if use_llm and get_workspace_llm_config(db, workspace_id=user.workspace_id) is None:
        errors.append("use_llm=true but workspace has no LLM config")

    stack_keys: list[str] = []
    for k in ["prompt_stack_key", "reply_prompt_stack_key", "quote_prompt_stack_key", "keyword_repost_prompt_stack_key"]:
        if has_nonempty_string(config.get(k)):
            stack_keys.append(str(config.get(k)).strip())
    if stack_keys:
        rows = db.scalars(
            select(PromptStack.key).where(PromptStack.workspace_id == user.workspace_id, PromptStack.key.in_(stack_keys))
        ).all()
        existing = {str(r) for r in rows}
        for k in stack_keys:
            if k not in existing:
                errors.append(f"PromptStack not found: {k}")

    if "publish_post" in kind or is_original_posts:
        has_media = has_nonempty_list(config.get("media_urls")) or has_nonempty_list(config.get("media"))
        has_text = has_nonempty_string(config.get("text")) or has_nonempty_string(config.get("post_text")) or has_nonempty_list(config.get("texts"))
        has_prompt_stack = has_nonempty_string(config.get("prompt_stack_key"))
        if not (has_media or has_text or has_prompt_stack):
            errors.append("Missing post content (text/texts/media_urls/prompt_stack_key)")
        if use_llm and not has_prompt_stack:
            warnings.append("use_llm=true but prompt_stack_key missing; LLM generation may fail")

    ok = not errors
    return StrategyValidateResponse(ok=ok, errors=errors, warnings=warnings)
