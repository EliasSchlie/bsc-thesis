"""Compute Cohen's kappa between the translator's counterparty classification
and the manual blind labels collected via counterparty_check.py.

Inputs:
    1_translate/output/translated.jsonl    (automated translator + manual overrides)
    1_translate/validation/counterparty_labels.jsonl  (blind labels)

Translator -> binary label: `skip` in output row → "absent"; otherwise "present".
Human labels: "present" / "absent" / "unsure". "unsure" rows are excluded.

Prints: confusion matrix, observed agreement, expected (chance) agreement,
Cohen's kappa, 95% CI (Fleiss approximation), and per-id disagreements.

Usage:
    python -m translate_validation.compute_kappa
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path

# code/translate_validation/compute_kappa.py  →  parent.parent.parent = repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LABELS_PATH = REPO_ROOT / "1_translate" / "validation" / "counterparty_labels.jsonl"
TRANSLATED_PATH = REPO_ROOT / "1_translate" / "output" / "translated.jsonl"
OVERRIDES_PATH = REPO_ROOT / "1_translate" / "output" / "manual_overrides.jsonl"
KAPPA_CSV = REPO_ROOT / "4_analyze" / "output" / "translator_kappa.csv"


def load_labels(path: Path) -> tuple[int | None, list[dict]]:
    lines = [line.strip() for line in open(path) if line.strip()]
    seed = None
    labels: list[dict] = []
    for i, line in enumerate(lines):
        row = json.loads(line)
        if i == 0 and "seed" in row:
            seed = row["seed"]
            continue
        labels.append(row)
    return seed, labels


def translator_decisions(path: Path) -> dict[int, str]:
    out: dict[int, str] = {}
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            out[r["id"]] = "absent" if "skip" in r else "present"
    return out


def override_ids(path: Path) -> set[int]:
    if not path.exists():
        return set()
    with open(path) as f:
        return {json.loads(line)["id"] for line in f if line.strip()}


def main() -> None:
    seed, labels = load_labels(LABELS_PATH)
    translator = translator_decisions(TRANSLATED_PATH)
    overrides = override_ids(OVERRIDES_PATH)

    print(f"labels: {len(labels)} (seed: {seed})")
    print(f"distribution: {dict(Counter(r['label'] for r in labels))}")

    confusion: Counter = Counter()
    disagreements: list[tuple[int, str, str, str]] = []
    for r in labels:
        if r["label"] == "unsure":
            continue
        h = r["label"]
        a = translator[r["id"]]
        confusion[(h, a)] += 1
        if h != a:
            disagreements.append((r["id"], h, a, r.get("notes", "")))

    n = sum(confusion.values())
    if n == 0:
        print("no usable labels (all were 'unsure').")
        return

    obs = sum(v for (h, a), v in confusion.items() if h == a) / n
    ph = sum(v for (h, a), v in confusion.items() if h == "present") / n
    pa = sum(v for (h, a), v in confusion.items() if a == "present") / n
    exp = ph * pa + (1 - ph) * (1 - pa)
    kappa = (obs - exp) / (1 - exp) if exp < 1 else 1.0
    se = math.sqrt(obs * (1 - obs) / (n * (1 - exp) ** 2)) if n and exp < 1 else 0.0
    ci_lo, ci_hi = kappa - 1.96 * se, kappa + 1.96 * se

    print()
    print("confusion (human, translator):")
    for k, v in sorted(confusion.items()):
        print(f"  {k}: {v}")
    print()
    print(f"n (excluding 'unsure') = {n}")
    print(f"observed agreement     = {obs:.3f}")
    print(f"chance agreement       = {exp:.3f}")
    print(f"Cohen's kappa          = {kappa:.3f}")
    print(f"95% CI (Fleiss approx) = [{ci_lo:.3f}, {ci_hi:.3f}]")
    print()
    print(f"disagreements ({len(disagreements)}):")
    for sid, h, a, notes in disagreements:
        tag = " [MANUAL-OVERRIDE]" if sid in overrides else ""
        extra = f" | {notes}" if notes else ""
        print(f"  id={sid}: human={h}, translator={a}{tag}{extra}")

    KAPPA_CSV.parent.mkdir(parents=True, exist_ok=True)
    with KAPPA_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "scope",
                "kappa",
                "se",
                "ci_lo",
                "ci_hi",
                "n",
                "observed_agreement",
                "chance_agreement",
                "n_present_present",
                "n_present_absent",
                "n_absent_present",
                "n_absent_absent",
            ]
        )
        w.writerow(
            [
                "overall",
                f"{kappa:.4f}",
                f"{se:.4f}",
                f"{ci_lo:.4f}",
                f"{ci_hi:.4f}",
                n,
                f"{obs:.4f}",
                f"{exp:.4f}",
                confusion.get(("present", "present"), 0),
                confusion.get(("present", "absent"), 0),
                confusion.get(("absent", "present"), 0),
                confusion.get(("absent", "absent"), 0),
            ]
        )
    print(f"\ncached κ values written to {KAPPA_CSV}")


if __name__ == "__main__":
    main()
