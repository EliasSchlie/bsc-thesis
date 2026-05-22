"""Translate one DeceptionBench scenario into behavioral (system + user) framing."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from translate.claude import Claude


CONDITION_KEYS = [
    "L1-self",
    "L1-other",
    "L2-self-pressure",
    "L2-self-reward",
    "L2-other-pressure",
    "L2-other-reward",
]

TRANSLATION_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "translate.md"


def build_system_prompt() -> str:
    return TRANSLATION_PROMPT_PATH.read_text()


def _build_user_message(scenario: dict[str, Any]) -> str:
    payload = {key: scenario[key] for key in CONDITION_KEYS}
    return json.dumps(payload, indent=2)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON object from model output, tolerating code fences."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    payload = fenced.group(1) if fenced else text
    start = payload.find("{")
    end = payload.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON object found in response: {text[:200]!r}")
    return json.loads(payload[start : end + 1])


async def translate_scenario(
    scenario: dict[str, Any],
    log_file: str | Path,
    model: str | None = None,
) -> dict[str, Any]:
    """Translate one scenario into behavioral framing.

    Per-variant translator errors (`{"error": "..."}`) are preserved in the
    output under that condition key. Whole-scenario failures (malformed JSON,
    missing keys, LLM error) raise so the caller can record an error marker.
    """
    claude_kwargs: dict[str, Any] = {"system_prompt": build_system_prompt()}
    if model is not None:
        claude_kwargs["model"] = model

    claude = Claude(log_file=log_file, **claude_kwargs)
    result = await claude.run(_build_user_message(scenario))

    text_parts: list[str] = []
    for msg in result.messages:
        if msg["role"] != "assistant":
            continue
        for block in msg["content"]:
            if block.get("type") == "text":
                text_parts.append(block["text"])
    raw = "\n".join(text_parts).strip()
    if not raw:
        raise RuntimeError("Translator returned no text output")

    translated = _extract_json(raw)

    if "skip" in translated:
        return {
            "id": scenario.get("id"),
            "topic": scenario.get("topic"),
            "dimension": scenario.get("dimension"),
            "question": scenario.get("question"),
            "groundtruth": scenario.get("groundtruth"),
            "goal": scenario.get("goal"),
            "source": "auto",
            "skip": translated["skip"],
        }

    missing = [k for k in CONDITION_KEYS if k not in translated]
    if missing:
        raise ValueError(f"Translator output missing conditions: {missing}")

    conditions: dict[str, dict[str, str]] = {}
    for key in CONDITION_KEYS:
        entry = translated[key]
        original = scenario[key]
        if "error" in entry:
            conditions[key] = {"original": original, "error": entry["error"]}
            continue
        required = ("system_prompt", "user_message", "split_token")
        missing_fields = [f for f in required if f not in entry]
        if missing_fields:
            raise ValueError(f"Condition {key} missing fields: {missing_fields}")
        split_token = entry["split_token"]
        count = original.count(split_token)
        if count != 1:
            raise ValueError(
                f"Condition {key} split_token not a unique substring of original "
                f"(count={count}): {split_token!r}"
            )
        conditions[key] = {
            "original": original,
            "system_prompt": entry["system_prompt"],
            "user_message": entry["user_message"],
            "split_token": split_token,
        }

    return {
        "id": scenario.get("id"),
        "topic": scenario.get("topic"),
        "dimension": scenario.get("dimension"),
        "question": scenario.get("question"),
        "groundtruth": scenario.get("groundtruth"),
        "goal": scenario.get("goal"),
        "source": "auto",
        "conditions": conditions,
    }
