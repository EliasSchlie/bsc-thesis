"""Apply manual overrides on top of an existing translated.jsonl.

This is a separate step from the automated translator (`translate/run.py`).
It patches rows in `1_translate/output/translated.jsonl` with hand-written
entries from `1_translate/output/manual_overrides.jsonl` for scenarios the
automated pipeline couldn't handle (e.g. platform AUP refusals).

Each patched row is tagged `source: "manual"`. Untouched rows keep whatever
source tag the run wrote.

Logs a manifest to `1_translate/logs/overrides_{ts}/manifest.json` with git
SHA, input/output hashes, and the ids that were patched.

Usage:
    python -m translate.apply_overrides \\
        --input 1_translate/output/translated.jsonl \\
        --output 1_translate/output/translated.jsonl \\
        --originals 1_translate/input/original.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# code/translate/apply_overrides.py  →  parent.parent.parent = repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "code"))

from translate.overrides import apply_override, load_overrides  # noqa: E402
from translate.runlog import create_run, finalize_run  # noqa: E402


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=REPO_ROOT / "1_translate" / "output" / "translated.jsonl",
        help="Translated-file to patch (read).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "1_translate" / "output" / "translated.jsonl",
        help="Where to write the patched file (can be same as --input).",
    )
    parser.add_argument(
        "--originals",
        type=Path,
        default=REPO_ROOT / "1_translate" / "input" / "original.jsonl",
        help="Source scenarios, needed to fill in `original` text per condition.",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"Input file not found: {args.input}")

    overrides = load_overrides()
    if not overrides:
        print(
            "No overrides found at 1_translate/output/manual_overrides.jsonl; "
            "nothing to do."
        )
        return

    originals = {row["id"]: row for row in load_jsonl(args.originals)}
    translated = load_jsonl(args.input)

    manifest = create_run(
        stage="overrides",
        input_path=args.input,
        model=None,
        args={
            "output": str(args.output),
            "originals": str(args.originals),
            "override_ids": sorted(overrides),
        },
    )
    print(
        f"Run {manifest.run_id} manifest at {manifest.run_dir / 'manifest.json'}",
        flush=True,
    )
    print(
        f"Loaded {len(overrides)} overrides, {len(translated)} translated rows.",
        flush=True,
    )

    patched_ids: list[int] = []
    skipped_ids: list[int] = []
    patched = []
    for row in translated:
        sid = row.get("id")
        if sid in overrides:
            scenario = originals.get(sid)
            if scenario is None:
                print(
                    f"  WARN id={sid} in overrides but not in --originals; skipping",
                    flush=True,
                )
                skipped_ids.append(sid)
                patched.append(row)
                continue
            patched.append(apply_override(scenario, overrides[sid]))
            patched_ids.append(sid)
            print(f"  patched id={sid}", flush=True)
        else:
            patched.append(row)

    unapplied = sorted(set(overrides) - set(patched_ids) - set(skipped_ids))
    if unapplied:
        print(
            f"  WARN overrides for ids={unapplied} not present in --input; unapplied",
            flush=True,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        for row in patched:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    finalize_run(
        manifest,
        args.output,
        n_scenarios=len(patched),
        n_translated=sum(1 for r in patched if "conditions" in r),
        n_skipped=sum(1 for r in patched if "skip" in r),
        n_errors=sum(
            1
            for r in patched
            if "error" in r and "conditions" not in r and "skip" not in r
        ),
    )

    print(
        f"\nPatched {len(patched_ids)} rows, wrote {args.output}. "
        f"Unapplied: {unapplied or 'none'}.",
        flush=True,
    )


if __name__ == "__main__":
    main()
