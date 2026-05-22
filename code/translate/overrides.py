"""Manual-override layer for the translator.

When the platform-level AUP filter refuses a scenario (not a model refusal,
but an Anthropic Usage Policy block upstream of the model), the translation
cannot be produced by the automated pipeline. Such scenarios are translated
or classified manually and recorded in
`1_translate/output/manual_overrides.jsonl`, where each line is one of:

    {"id": <int>, "skip": "<reason>"}
    {"id": <int>, "conditions": {<6 variants with system_prompt/user_message/split_token>}}

When the pipeline runs, these overrides take precedence over the LLM call.
Every row in `1_translate/output/translated.jsonl` carries a `source` field
(`"auto"` or `"manual"`) marking provenance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# code/translate/overrides.py  →  parent.parent.parent = repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OVERRIDES_PATH = _REPO_ROOT / "1_translate" / "output" / "manual_overrides.jsonl"

CONDITION_KEYS = [
    "L1-self",
    "L1-other",
    "L2-self-pressure",
    "L2-self-reward",
    "L2-other-pressure",
    "L2-other-reward",
]


def load_overrides(path: Path = OVERRIDES_PATH) -> dict[int, dict[str, Any]]:
    """Return {scenario_id: override_row}. Empty if file missing."""
    if not path.exists():
        return {}
    overrides: dict[int, dict[str, Any]] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            overrides[row["id"]] = row
    return overrides


def apply_override(
    scenario: dict[str, Any], override: dict[str, Any]
) -> dict[str, Any]:
    """Construct a translated-row dict from a scenario + its manual override.

    Shape matches `translate_scenario` output, plus `source: "manual"` for
    provenance.
    """
    base = {
        "id": scenario.get("id"),
        "topic": scenario.get("topic"),
        "dimension": scenario.get("dimension"),
        "question": scenario.get("question"),
        "groundtruth": scenario.get("groundtruth"),
        "goal": scenario.get("goal"),
        "source": "manual",
    }
    if "skip" in override:
        base["skip"] = override["skip"]
        return base
    if "conditions" in override:
        conditions: dict[str, dict[str, str]] = {}
        for key in CONDITION_KEYS:
            entry = override["conditions"][key]
            conditions[key] = {
                "original": scenario[key],
                "system_prompt": entry["system_prompt"],
                "user_message": entry["user_message"],
                "split_token": entry["split_token"],
            }
        base["conditions"] = conditions
        return base
    raise ValueError(
        f"Override for id={scenario.get('id')} has neither 'skip' nor 'conditions'"
    )
