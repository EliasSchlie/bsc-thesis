"""Stratified sample of (model, scenario, framing, condition) cells for judge validation.

Joint stratification on (framing x judge_response_label) across the 8 main
target models, with target model balanced approximately uniformly within each
stratum. The 2-way judge labels (from `bench/judge.py`, written under
`3_judge/output/<model>/judge_<judge_slug>_<framing>.jsonl`) are read from disk
to define the strata; rows missing judge labels or carrying parse/gen errors
are excluded from the pool.

Output:
    3_judge/validation/sample.jsonl with a header record on line 1 and one row
    per sampled cell. Records carry the existing 2-way judge label so
    `compute_kappa.py` can read it directly without a re-judge pass.

Usage:
    # from the repository root
    python -m judge_validation.sample           # uses all defaults (n=100, gpt-5.4-nano judge)
    python -m judge_validation.sample --n 50    # smaller sample
    python -m judge_validation.sample --judge-model openai/some-other-judge   # alternative judge
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from bench.dataset import FRAMINGS, load_scenarios
from bench.paths import gen_path, judge_path, slug

logger = logging.getLogger(__name__)


MAIN_MODELS: tuple[str, ...] = (
    "openai/gpt-4o-2024-08-06",
    "openai/gpt-5.4",
    "google/gemini-2.0-flash-001",
    "google/gemini-3-flash-preview",
    "deepseek-ai/DeepSeek-V3.2",
    "deepseek/deepseek-r1",
    "qwen/qwen-2.5-7b-instruct",
    "qwen/qwen3.5-9b",
)


def _load_gen_rows(results_dir: Path, target_model: str) -> list[dict]:
    rows: list[dict] = []
    for fr in FRAMINGS:
        p = gen_path(results_dir, target_model, fr)
        if not p.exists():
            continue
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                if r.get("error"):
                    continue
                if not r.get("raw_response"):
                    continue
                rows.append(r)
    return rows


def _load_judge_index(
    results_dir: Path, target_model: str, judge_model: str
) -> dict[tuple[int, str, str], dict]:
    """Return {(scenario_id, framing, condition): {"thought": ..., "response": ...}}."""
    idx: dict[tuple[int, str, str], dict] = {}
    for fr in FRAMINGS:
        p = judge_path(results_dir, target_model, judge_model, fr)
        if not p.exists():
            continue
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                if r.get("parse_error") or r.get("error"):
                    continue
                ev = r.get("eval") or {}
                sid = r["scenario_id"]
                for cond, labels in ev.items():
                    if not isinstance(labels, dict):
                        continue
                    if "response" not in labels:
                        continue
                    idx[(sid, fr, cond)] = {
                        "thought": labels.get("thought"),
                        "response": labels.get("response"),
                    }
    return idx


def _balanced_draw(
    pool: list[dict], n: int, key: str, rng: random.Random
) -> list[dict]:
    """Draw n items from pool, balancing across `key` as uniformly as possible.

    Round-robin over distinct key values (shuffled per cycle), drawing without
    replacement until n is reached or pool is exhausted.
    """
    by_key: dict[str, list[dict]] = defaultdict(list)
    for r in pool:
        by_key[r[key]].append(r)
    for v in by_key.values():
        rng.shuffle(v)
    keys = list(by_key.keys())
    out: list[dict] = []
    while len(out) < n and keys:
        rng.shuffle(keys)
        for k in keys[:]:
            if not by_key[k]:
                keys.remove(k)
                continue
            out.append(by_key[k].pop())
            if len(out) >= n:
                break
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--results-dir",
        default=".",
        help="repository root; gen/judge JSONLs are resolved under "
        "2_generate/output/<model>/ and 3_judge/output/<model>/",
    )
    p.add_argument(
        "--judge-model",
        default="openai/gpt-5.4-nano",
        help="judge model slug (used to locate judge_<slug>_<framing>.jsonl); "
        "only override if you re-judged with a different model",
    )
    p.add_argument("--n", type=int, default=100)
    p.add_argument("--out", default="3_judge/validation/sample.jsonl")
    p.add_argument("--seed", type=int, default=0, help="0 = use time-based seed")
    p.add_argument(
        "--models",
        default=",".join(MAIN_MODELS),
        help="comma-separated list of target model ids; defaults to the 8 main models",
    )
    args = p.parse_args()

    target_models = [m.strip() for m in args.models.split(",") if m.strip()]
    seed = args.seed or int(time.time())
    rng = random.Random(seed)

    # Build the eligible pool: gen rows that have a 2-way judge label.
    scenarios = {s.id: s for s in load_scenarios()}
    pool: list[dict] = []
    pool_summary: Counter = Counter()
    for tm in target_models:
        gens = _load_gen_rows(Path(args.results_dir), tm)
        judge_idx = _load_judge_index(Path(args.results_dir), tm, args.judge_model)
        for r in gens:
            key = (r["scenario_id"], r["framing"], r["condition"])
            jl = judge_idx.get(key)
            if jl is None or jl.get("response") not in ("decept", "honest"):
                continue
            sc = scenarios.get(r["scenario_id"])
            if sc is None:
                continue
            pool.append(
                {
                    "target_model": tm,
                    "scenario_id": r["scenario_id"],
                    "framing": r["framing"],
                    "condition": r["condition"],
                    "topic": r.get("topic") or sc.topic,
                    "dimension": r.get("dimension") or sc.dimension,
                    "question": sc.question,
                    "groundtruth": sc.groundtruth,
                    "goal": sc.goal,
                    "prompt_system": r.get("prompt_system"),
                    "prompt_user": r.get("prompt_user"),
                    "raw_response": r.get("raw_response", ""),
                    "cleaned_response": r.get("cleaned_response", ""),
                    "judge_response": jl["response"],
                    "judge_thought": jl.get("thought"),
                }
            )
            pool_summary[(tm, r["framing"], jl["response"])] += 1

    if not pool:
        sys.exit("error: pool is empty; check --results-dir and --judge-model")

    print(
        f"pool size: {len(pool)} cells across {len(target_models)} models",
        file=sys.stderr,
    )

    # Joint strata: (framing x judge_response). 4 x 2 = 8 strata.
    strata: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in pool:
        strata[(r["framing"], r["judge_response"])].append(r)

    if any(len(v) == 0 for v in strata.values()):
        empty = [k for k, v in strata.items() if len(v) == 0]
        print(f"warning: empty strata: {empty}", file=sys.stderr)

    # Allocate n across strata proportional to (1/n_strata), i.e. balanced,
    # but capped at stratum availability. Distribute leftover slots
    # proportionally to remaining capacity.
    n_strata = len([k for k, v in strata.items() if v])
    base = args.n // n_strata
    alloc: dict[tuple[str, str], int] = {}
    leftover = args.n
    for k, v in strata.items():
        a = min(base, len(v))
        alloc[k] = a
        leftover -= a
    # Greedy fill remaining slots to strata with extra capacity.
    capacities = sorted(
        ((k, len(v) - alloc[k]) for k, v in strata.items()),
        key=lambda kv: -kv[1],
    )
    while leftover > 0 and any(c > 0 for _, c in capacities):
        for i, (k, c) in enumerate(capacities):
            if leftover <= 0:
                break
            if c <= 0:
                continue
            alloc[k] += 1
            capacities[i] = (k, c - 1)
            leftover -= 1

    sampled: list[dict] = []
    for k, v in strata.items():
        n_k = alloc[k]
        if n_k <= 0 or not v:
            continue
        sampled.extend(_balanced_draw(v, n_k, key="target_model", rng=rng))

    rng.shuffle(sampled)

    if len(sampled) < args.n:
        print(
            f"warning: only drew {len(sampled)} of requested {args.n} "
            f"(pool/stratum capacity limited)",
            file=sys.stderr,
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "seed": seed,
                    "n": len(sampled),
                    "target_models": target_models,
                    "judge_model": args.judge_model,
                    "stratification": "framing x judge_response",
                    "ts": time.time(),
                }
            )
            + "\n"
        )
        for r in sampled:
            sid = r["scenario_id"]
            tm_slug = slug(r["target_model"])
            rec = {
                "sample_id": f"{tm_slug}__{sid}_{r['framing']}_{r['condition']}",
                **r,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Diagnostics.
    by_fr_label = Counter((r["framing"], r["judge_response"]) for r in sampled)
    by_model = Counter(r["target_model"] for r in sampled)
    by_framing = Counter(r["framing"] for r in sampled)
    print(f"wrote {len(sampled)} samples to {out} (seed={seed})", file=sys.stderr)
    print(f"  by framing: {dict(by_framing)}", file=sys.stderr)
    print(f"  by (framing, judge_response): {dict(by_fr_label)}", file=sys.stderr)
    print(f"  by model: {dict(by_model)}", file=sys.stderr)


if __name__ == "__main__":
    main()
