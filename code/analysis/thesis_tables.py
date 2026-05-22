"""Within-lineage successor-pair table for §5.2 of the thesis.

Reads each model's results.csv (long-format, one row per (sid, framing, condition)
with `deceived` 0/1 column), writes:

    4_analyze/output/successor_pairs.csv   4 pairs (OpenAI, Google, DeepSeek, Qwen),
                                           per-framing + mean deception rate before
                                           vs. after, with delta and relative delta.

The §5.2 numbers ("OpenAI -12 to -40pp, Qwen -46 to -48pp, DeepSeek -12 to -25pp,
Google -6 to -20pp") read off the per-framing rows.
"""

from __future__ import annotations

import csv
from pathlib import Path

# code/analysis/thesis_tables.py  →  parent.parent.parent = repo root
REPO = Path(__file__).resolve().parent.parent.parent
JUDGE_OUT = REPO / "3_judge" / "output"  # per-model results.csv lives here
OUT = REPO / "4_analyze" / "output"
OUT.mkdir(parents=True, exist_ok=True)

THESIS_MODELS: list[tuple[str, str]] = [
    ("openai/gpt-4o-2024-08-06", "gpt-4o"),
    ("openai/gpt-5.4", "gpt-5.4"),
    ("google/gemini-2.0-flash-001", "gemini-2"),
    ("google/gemini-3-flash-preview", "gemini-3"),
    ("deepseek-ai/DeepSeek-V3.2", "V3.2"),
    ("deepseek/deepseek-r1", "r1"),
    ("qwen/qwen-2.5-7b-instruct", "qwen2.5-7b"),
    ("qwen/qwen3.5-9b", "qwen3.5-9b"),
]

SUCCESSOR_PAIRS: list[tuple[str, str, str]] = [
    ("gpt-4o", "gpt-5.4", "OpenAI"),
    ("gemini-2", "gemini-3", "Google"),
    ("r1", "V3.2", "DeepSeek"),
    ("qwen2.5-7b", "qwen3.5-9b", "Qwen"),
]

FRAMINGS = ("A", "B", "C", "D")


def slug(model_id: str) -> str:
    return model_id.replace("/", "__")


def load_model_rows(model_id: str) -> list[dict]:
    path = JUDGE_OUT / slug(model_id) / "results.csv"
    rows = []
    with path.open() as f:
        for r in csv.DictReader(f):
            if r.get("gen_error") or r.get("parse_error"):
                continue
            if r["response"] not in ("decept", "honest"):
                continue
            rows.append(
                {
                    "framing": r["framing"],
                    "condition": r["condition"],
                    "deceived": int(r["deceived"]),
                }
            )
    return rows


def rate(rows: list[dict]) -> tuple[float, int, int]:
    if not rows:
        return (0.0, 0, 0)
    n = len(rows)
    k = sum(r["deceived"] for r in rows)
    return (k / n, k, n)


def main() -> None:
    all_rows: dict[str, list[dict]] = {}
    for model_id, _short in THESIS_MODELS:
        all_rows[model_id] = load_model_rows(model_id)

    short_to_id = {short: mid for mid, short in THESIS_MODELS}
    with (OUT / "successor_pairs.csv").open("w") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "family",
                "before",
                "after",
                "framing",
                "before_rate",
                "after_rate",
                "delta",
                "delta_rel",
            ]
        )
        for before_s, after_s, family in SUCCESSOR_PAIRS:
            for fr in list(FRAMINGS) + ["mean"]:
                if fr == "mean":
                    bef = [r for r in all_rows[short_to_id[before_s]]]
                    aft = [r for r in all_rows[short_to_id[after_s]]]
                else:
                    bef = [
                        r for r in all_rows[short_to_id[before_s]] if r["framing"] == fr
                    ]
                    aft = [
                        r for r in all_rows[short_to_id[after_s]] if r["framing"] == fr
                    ]
                pb, _, _ = rate(bef)
                pa, _, _ = rate(aft)
                delta = pa - pb
                delta_rel = (pa - pb) / pb if pb > 0 else float("nan")
                w.writerow(
                    [
                        family,
                        before_s,
                        after_s,
                        fr,
                        f"{pb:.4f}",
                        f"{pa:.4f}",
                        f"{delta:+.4f}",
                        "nan" if delta_rel != delta_rel else f"{delta_rel:+.3f}",
                    ]
                )

    # Console digest of the §5.2 numbers.
    print("\n=== Mean deception rate per model ===")
    for model_id, short in THESIS_MODELS:
        p, k, n = rate(all_rows[model_id])
        print(f"  {short:13s} {p * 100:5.1f}%   ({k}/{n})")

    print("\n=== Successor pairs (mean) ===")
    for before_s, after_s, family in SUCCESSOR_PAIRS:
        pb, _, _ = rate(all_rows[short_to_id[before_s]])
        pa, _, _ = rate(all_rows[short_to_id[after_s]])
        delta = pa - pb
        rel = (pa - pb) / pb * 100 if pb > 0 else float("nan")
        arrow = "↑" if delta > 0 else "↓"
        print(
            f"  {family:9s} {before_s:11s} {pb * 100:5.1f}% → "
            f"{after_s:11s} {pa * 100:5.1f}%   {arrow}{abs(delta) * 100:5.2f}pp  ({rel:+.1f}%)"
        )

    print(f"\nTable written to {OUT}/successor_pairs.csv")


if __name__ == "__main__":
    main()
