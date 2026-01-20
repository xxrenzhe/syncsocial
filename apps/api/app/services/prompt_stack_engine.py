from __future__ import annotations

import random
from typing import Any


def generate_prompt_from_stack(payload: dict[str, Any], *, seed: int | None = None) -> str:
    if not isinstance(payload, dict):
        raise ValueError("Invalid prompt stack payload")

    legacy = payload.get("legacy_prompt")
    layers = payload.get("layers")
    if not isinstance(layers, list) or not layers:
        if isinstance(legacy, str) and legacy.strip():
            return legacy.strip()
        return ""

    rng = random.Random(seed) if seed is not None else random
    parts: list[str] = []
    for layer in layers:
        if not isinstance(layer, dict):
            continue

        layer_type = str(layer.get("layer_type") or layer.get("type") or "").strip().lower()
        if layer_type == "empty":
            parts.append("")
            continue

        if layer_type != "text":
            continue

        options = layer.get("options")
        if not isinstance(options, list) or not options:
            continue

        selected = _select_option(rng, options)
        if selected:
            parts.append(selected)

    return "\n".join(parts)


def _select_option(rng: random.Random, options: list[Any]) -> str:
    cleaned: list[tuple[str, int]] = []
    for opt in options:
        if not isinstance(opt, dict):
            continue
        text = str(opt.get("text") or "")
        prob = opt.get("probability")
        try:
            prob_int = int(prob)
        except Exception:
            prob_int = 0
        if prob_int < 0:
            prob_int = 0
        cleaned.append((text, prob_int))

    if not cleaned:
        return ""

    if len(cleaned) == 1:
        return cleaned[0][0]

    total = sum(p for _, p in cleaned)
    if total <= 0:
        return rng.choice([t for t, _ in cleaned])

    pick = rng.randint(1, total)
    acc = 0
    for text, prob in cleaned:
        acc += prob
        if pick <= acc:
            return text

    return cleaned[-1][0]

