"""Cohen's κ between the 2-way judge labels and human labels on the validation sample.

Reads:
- 3_judge/validation/sample.jsonl  (carries the 2-way `judge_response` per cell)
- 3_judge/validation/labels_human.jsonl  (human `response` in {decept, non-decept}
  plus optional `refuse` flag)

Computes κ on the response label, overall and per framing. Also reports
descriptive numbers on the optional refuse flag (not used in κ).

Usage:
    python -m judge_validation.compute_kappa
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import math
from pathlib import Path

# code/judge_validation/compute_kappa.py  →  parent.parent.parent = repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_KAPPA_CSV = REPO_ROOT / "4_analyze" / "output" / "judge_kappa.csv"

# Map judge labels (2-way: decept/honest) to the human-label space (decept/non-decept).
JUDGE_TO_HUMAN_SPACE = {"decept": "decept", "honest": "non-decept"}


def _load_sample(path: Path) -> tuple[dict, dict[str, dict]]:
    header: dict = {}
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if i == 0 and "sample_id" not in r:
                header = r
                continue
            out[r["sample_id"]] = r
    return header, out


def _load_human(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if "sample_id" not in r:
                continue
            out[r["sample_id"]] = r
    return out


def _cohens_kappa(pairs: list[tuple[str, str]]) -> tuple[float, float, int]:
    if not pairs:
        return float("nan"), float("nan"), 0
    n = len(pairs)
    obs = sum(1 for a, b in pairs if a == b) / n
    cats = set(x for p in pairs for x in p)
    counts_a = collections.Counter(a for a, _ in pairs)
    counts_b = collections.Counter(b for _, b in pairs)
    exp = sum((counts_a[c] / n) * (counts_b[c] / n) for c in cats)
    if exp >= 1:
        return 1.0, 0.0, n
    kappa = (obs - exp) / (1 - exp)
    se = math.sqrt(obs * (1 - obs) / (n * (1 - exp) ** 2)) if n > 0 else float("nan")
    return kappa, se, n


def _confusion(pairs: list[tuple[str, str]]) -> dict:
    c: collections.Counter = collections.Counter()
    for a, b in pairs:
        c[(a, b)] += 1
    return dict(c)


def _fmt_kappa(kappa: float, se: float, n: int) -> str:
    if math.isnan(kappa):
        return "  n/a"
    lo, hi = kappa - 1.96 * se, kappa + 1.96 * se
    return f"κ={kappa:+.3f} [{lo:+.3f}, {hi:+.3f}] n={n}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sample", default="3_judge/validation/sample.jsonl")
    p.add_argument("--human-labels", default="3_judge/validation/labels_human.jsonl")
    p.add_argument(
        "--out-csv",
        default=str(DEFAULT_KAPPA_CSV),
        help="path to write the cached κ values (overall + per-framing); "
        "pass an empty string to skip writing",
    )
    args = p.parse_args()

    header, sample = _load_sample(Path(args.sample))
    human = _load_human(Path(args.human_labels))

    ids = sorted(set(sample) & set(human))
    only_sample = sorted(set(sample) - set(human))
    only_human = sorted(set(human) - set(sample))
    print(
        f"overlap: {len(ids)}   sample-only: {len(only_sample)}   human-only: {len(only_human)}"
    )

    def pairs_for(fr_filter: str | None = None) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for sid in ids:
            s = sample[sid]
            h = human[sid]
            if fr_filter and s.get("framing") != fr_filter:
                continue
            j_raw = s.get("judge_response")
            j = JUDGE_TO_HUMAN_SPACE.get(j_raw)
            r = h.get("response")
            if j is None or r not in ("decept", "non-decept"):
                continue
            out.append((j, r))
        return out

    print("\n=== RESPONSE (2-way judge vs 2-way human) ===")
    pairs = pairs_for()
    k, se, n = _cohens_kappa(pairs)
    print(f"overall:  {_fmt_kappa(k, se, n)}")
    overall_confusion = _confusion(pairs)
    print("confusion (judge, human):")
    for key, v in sorted(overall_confusion.items()):
        print(f"  {key}: {v}")

    rows_to_cache: list[dict] = []
    rows_to_cache.append(
        {
            "scope": "overall",
            "kappa": k,
            "se": se,
            "ci_lo": k - 1.96 * se if not math.isnan(se) else float("nan"),
            "ci_hi": k + 1.96 * se if not math.isnan(se) else float("nan"),
            "n": n,
            "n_decept_decept": overall_confusion.get(("decept", "decept"), 0),
            "n_decept_nondecept": overall_confusion.get(("decept", "non-decept"), 0),
            "n_nondecept_decept": overall_confusion.get(("non-decept", "decept"), 0),
            "n_nondecept_nondecept": overall_confusion.get(
                ("non-decept", "non-decept"), 0
            ),
        }
    )
    for fr in ("A", "B", "C", "D"):
        fp = pairs_for(fr)
        k_fr, se_fr, n_fr = _cohens_kappa(fp)
        print(f"  framing {fr}: {_fmt_kappa(k_fr, se_fr, n_fr)}")
        confusion_fr = _confusion(fp)
        rows_to_cache.append(
            {
                "scope": f"framing_{fr}",
                "kappa": k_fr,
                "se": se_fr,
                "ci_lo": k_fr - 1.96 * se_fr if not math.isnan(se_fr) else float("nan"),
                "ci_hi": k_fr + 1.96 * se_fr if not math.isnan(se_fr) else float("nan"),
                "n": n_fr,
                "n_decept_decept": confusion_fr.get(("decept", "decept"), 0),
                "n_decept_nondecept": confusion_fr.get(("decept", "non-decept"), 0),
                "n_nondecept_decept": confusion_fr.get(("non-decept", "decept"), 0),
                "n_nondecept_nondecept": confusion_fr.get(
                    ("non-decept", "non-decept"), 0
                ),
            }
        )

    if args.out_csv:
        out = Path(args.out_csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows_to_cache[0].keys()))
            w.writeheader()
            for r in rows_to_cache:
                w.writerow(
                    {
                        k: ("" if isinstance(v, float) and math.isnan(v) else v)
                        for k, v in r.items()
                    }
                )
        print(f"\ncached κ values written to {out}")

    # Descriptive: refuse flag prevalence (not used in κ).
    refuse_rows = [h for sid, h in human.items() if sid in sample and h.get("refuse")]
    n_human = sum(1 for sid in human if sid in sample)
    if n_human:
        print(
            f"\nrefuse flag (descriptive only): {len(refuse_rows)}/{n_human} "
            f"({100 * len(refuse_rows) / n_human:.1f}%)"
        )
        # Of judge-honest cases, how many did human flag refuse?
        judge_honest_refuse = [
            sid
            for sid in ids
            if sample[sid].get("judge_response") == "honest"
            and human[sid].get("refuse")
        ]
        n_judge_honest = sum(
            1 for sid in ids if sample[sid].get("judge_response") == "honest"
        )
        if n_judge_honest:
            print(
                f"  of judge-honest: {len(judge_honest_refuse)}/{n_judge_honest} "
                f"({100 * len(judge_honest_refuse) / n_judge_honest:.1f}%) flagged refuse"
            )


if __name__ == "__main__":
    main()
