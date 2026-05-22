"""Show every cell where the judge and human disagreed.

Reads 3_judge/validation/{sample,labels_human}.jsonl, prints all
disagreements grouped by direction (judge over-calls vs under-calls),
and writes a markdown file for thesis discussion.
"""

from __future__ import annotations

import json
from pathlib import Path

# code/analysis/show_disagreements.py  →  parent.parent.parent = repo root
REPO = Path(__file__).resolve().parent.parent.parent
SAMPLE = REPO / "3_judge" / "validation" / "sample.jsonl"
HUMAN = REPO / "3_judge" / "validation" / "labels_human.jsonl"
OUT = REPO / "4_analyze" / "output" / "disagreements.md"

JUDGE_TO_HUMAN = {"decept": "decept", "honest": "non-decept"}

SHORT = {
    "openai__gpt-4o-2024-08-06": "gpt-4o",
    "openai__gpt-5.4": "gpt-5.4",
    "google__gemini-2.0-flash-001": "gemini-2",
    "google__gemini-3-flash-preview": "gemini-3",
    "deepseek-ai__DeepSeek-V3.2": "V3.2",
    "deepseek__deepseek-r1": "r1",
    "qwen__qwen-2.5-7b-instruct": "qwen2.5-7b",
    "qwen__qwen3.5-9b": "qwen3.5-9b",
}


def main() -> None:
    sample: dict[str, dict] = {}
    with SAMPLE.open() as f:
        next(f)
        for line in f:
            r = json.loads(line)
            sample[r["sample_id"]] = r
    human: dict[str, dict] = {}
    with HUMAN.open() as f:
        next(f)
        for line in f:
            r = json.loads(line)
            human[r["sample_id"]] = r

    fp = []
    fn = []
    for sid, s in sample.items():
        h = human.get(sid)
        if not h:
            continue
        j = JUDGE_TO_HUMAN[s["judge_response"]]
        r = h["response"]
        if j == r:
            continue
        rec = (sid, s, h)
        if j == "decept":
            fp.append(rec)
        else:
            fn.append(rec)

    md = ["# Judge–human disagreements (n=17/100)\n\n"]
    md.append(
        "Two-way labels: judge ∈ {decept, honest}, human ∈ {decept, non-decept}.\n"
    )
    md.append(
        "Direction split: judge over-calls (FP, n="
        + str(len(fp))
        + ") vs judge under-calls (FN, n="
        + str(len(fn))
        + ").\n\n"
    )

    def fmt_block(title: str, items: list) -> None:
        md.append(f"## {title}\n\n")
        for sid, s, h in items:
            model_short = SHORT[sid.rsplit("__", 1)[0]]
            md.append(
                f"### `{sid}`  ({model_short}, framing {s['framing']}, "
                f"{s['condition']})\n\n"
            )
            md.append(
                f"- **judge**: `{s['judge_response']}`   "
                f"**human**: `{h['response']}`   "
                f"refuse={h.get('refuse')}\n"
            )
            if h.get("notes"):
                md.append(f"- **human notes**: {h['notes']}\n")
            md.append(f"- **question**: {s['question']}\n")
            md.append(f"- **groundtruth**: {s['groundtruth']}\n")
            md.append(f"- **goal**: {s.get('goal')}\n\n")
            md.append("**model response (cleaned):**\n")
            md.append("```\n" + s["cleaned_response"] + "\n```\n\n")
            md.append(f"**judge thought**: {s.get('judge_thought') or '(none)'}\n\n")
            md.append("---\n\n")

    fmt_block("Judge says decept, human says non-decept (FP)", fp)
    fmt_block("Judge says honest, human says decept (FN)", fn)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(md))
    print(f"wrote {OUT}")
    print(f"FP (judge over-calls): {len(fp)}")
    print(f"FN (judge under-calls): {len(fn)}")


if __name__ == "__main__":
    main()
