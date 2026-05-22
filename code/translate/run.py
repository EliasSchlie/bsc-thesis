"""Translate the full DeceptionBench dataset in parallel (rate-limited).

Each invocation writes to 1_translate/logs/translate_{ts}/ with a manifest.json
(git SHA, input hash, args, output hash, counts) and per-scenario logs under
scenarios/. Output JSONL is written in input order; on per-scenario failure,
an error marker row is written so line N still corresponds to input line N.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# code/translate/run.py  →  parent.parent.parent = repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "code"))

from translate.runlog import (  # noqa: E402
    RunManifest,
    create_run,
    finalize_run,
    scenario_log_path,
)
from translate.translate import translate_scenario  # noqa: E402


def load_scenarios(path: Path) -> list[dict]:
    scenarios: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            scenarios.append(json.loads(line))
    return scenarios


async def translate_one(
    scenario: dict,
    idx: int,
    total: int,
    sem: asyncio.Semaphore,
    manifest: RunManifest,
    model: str | None,
) -> dict:
    sid = scenario["id"]
    async with sem:
        log_file = scenario_log_path(manifest, sid)
        print(
            f"[{idx + 1}/{total}] id={sid} translating "
            f"({scenario.get('topic')}/{scenario.get('dimension')})...",
            flush=True,
        )
        t0 = time.time()
        try:
            translated = await translate_scenario(
                scenario, log_file=log_file, model=model
            )
            dt = time.time() - t0
            tag = "skip" if "skip" in translated else "done"
            print(
                f"[{idx + 1}/{total}] id={sid} {tag} in {dt:.1f}s log={log_file.name}",
                flush=True,
            )
            return translated
        except Exception as e:
            dt = time.time() - t0
            print(
                f"[{idx + 1}/{total}] id={sid} FAILED in {dt:.1f}s: {e} "
                f"log={log_file.name}",
                flush=True,
            )
            return {"id": sid, "error": f"{type(e).__name__}: {e}"}


def _summarize(results: list[dict]) -> tuple[int, int, int]:
    n_translated = sum(1 for r in results if "conditions" in r)
    n_skipped = sum(1 for r in results if "skip" in r)
    n_errors = sum(
        1 for r in results if "error" in r and "conditions" not in r and "skip" not in r
    )
    return n_translated, n_skipped, n_errors


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=REPO_ROOT / "1_translate" / "input" / "original.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "1_translate" / "output" / "translated.jsonl",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="Max simultaneous translator calls",
    )
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Translate only the first N scenarios (for testing)",
    )
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="Retranslate only the error-marker rows in --output, merge back in order, overwrite --output.",
    )
    args = parser.parse_args()

    scenarios = load_scenarios(args.input)
    if args.limit is not None:
        scenarios = scenarios[: args.limit]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(args.concurrency)

    manifest = create_run(
        stage="translate",
        input_path=args.input,
        model=args.model,
        args={
            "concurrency": args.concurrency,
            "limit": args.limit,
            "retry_errors": args.retry_errors,
            "output": str(args.output),
        },
    )
    print(f"Run {manifest.run_id} logs at {manifest.run_dir}", flush=True)

    if args.retry_errors:
        if not args.output.exists():
            raise SystemExit(
                f"--retry-errors requires existing output file at {args.output}"
            )
        existing = load_scenarios(args.output)
        by_id = {row["id"]: row for row in existing}
        error_ids = [
            row["id"]
            for row in existing
            if "error" in row and "conditions" not in row and "skip" not in row
        ]
        retry_scenarios = [s for s in scenarios if s["id"] in set(error_ids)]
        total = len(retry_scenarios)
        print(
            f"Retry mode: {total} error rows in {args.output}. "
            f"Concurrency={args.concurrency}. ids={error_ids}",
            flush=True,
        )
        tasks = [
            asyncio.create_task(
                translate_one(scenario, idx, total, sem, manifest, args.model)
            )
            for idx, scenario in enumerate(retry_scenarios)
        ]
        t_start = time.time()
        results = await asyncio.gather(*tasks)
        t_elapsed = time.time() - t_start

        for row in results:
            by_id[row["id"]] = row

        merged = [by_id[s["id"]] for s in scenarios]
        with open(args.output, "w") as out:
            for row in merged:
                out.write(json.dumps(row, ensure_ascii=False) + "\n")

        n_translated, n_skipped, n_errors = _summarize(merged)
        finalize_run(
            manifest, args.output, len(merged), n_translated, n_skipped, n_errors
        )
        still_errors = [
            r["id"]
            for r in merged
            if "error" in r and "conditions" not in r and "skip" not in r
        ]
        newly_fixed = [rid for rid in error_ids if rid not in set(still_errors)]
        print(
            f"\nMerged retry results into {args.output}: "
            f"{len(merged)} lines, {len(newly_fixed)} fixed "
            f"(ids={newly_fixed}), {len(still_errors)} still errored "
            f"(ids={still_errors}) in {t_elapsed:.1f}s",
            flush=True,
        )
        return

    total = len(scenarios)
    print(
        f"Loaded {total} scenarios from {args.input}. "
        f"Concurrency={args.concurrency}. Output={args.output}",
        flush=True,
    )

    tasks = [
        asyncio.create_task(
            translate_one(scenario, idx, total, sem, manifest, args.model)
        )
        for idx, scenario in enumerate(scenarios)
    ]

    t_start = time.time()
    results = await asyncio.gather(*tasks)
    t_elapsed = time.time() - t_start

    with open(args.output, "w") as out:
        for row in results:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")

    n_translated, n_skipped, n_errors = _summarize(results)
    finalize_run(manifest, args.output, total, n_translated, n_skipped, n_errors)

    print(
        f"\nWrote {args.output}: {total} lines "
        f"({n_translated} translated, {n_skipped} skipped, {n_errors} errors) "
        f"in {t_elapsed:.1f}s. Manifest: {manifest.run_dir / 'manifest.json'}",
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
