"""Run the target model on every (scenario, condition, framing) and append rows to JSONL.

Output: `2_generate/output/<model_slug>/gen_<framing>.jsonl`, one row per call,
resumable by (scenario_id, condition, framing). Each row is self-contained:
full prompt, raw response, cleaned response, usage, latency, attempts.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from tqdm import tqdm

from bench.dataset import (
    CONDITIONS,
    FRAMINGS,
    Condition,
    Framing,
    Prompt,
    Scenario,
    iter_prompts,
)
from bench.io import JSONLAppender, completed_gen_keys
from bench.llm import OpenAICompatClient
from bench.paths import gen_path

logger = logging.getLogger(__name__)


def _run_one(
    client: OpenAICompatClient,
    scenario: Scenario,
    condition: Condition,
    framing: Framing,
    prompt: Prompt,
) -> dict[str, Any]:
    t0 = time.time()
    result = client.chat(system=prompt.system, user=prompt.user)
    return {
        "scenario_id": scenario.id,
        "topic": scenario.topic,
        "dimension": scenario.dimension,
        "condition": condition,
        "framing": framing,
        "prompt_system": prompt.system,
        "prompt_user": prompt.user,
        "model": result.model,
        "raw_response": result.raw_text,
        "cleaned_response": result.cleaned_text,
        "reasoning": result.reasoning,
        "reasoning_tokens": result.reasoning_tokens,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "total_tokens": result.total_tokens,
        "response_full": result.response_full,
        "latency_ms": result.latency_ms,
        "attempts": result.attempts,
        "error": result.error,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(t0)),
    }


def run_generation(
    *,
    scenarios: list[Scenario],
    client: OpenAICompatClient,
    model_id: str,
    results_dir: Path,
    framings: tuple[Framing, ...] = FRAMINGS,
    conditions: tuple[Condition, ...] = CONDITIONS,
    max_workers: int = 50,
) -> dict[str, int]:
    """Generate responses for the full product of (scenarios, conditions, framings).

    Returns a summary dict: per-framing counts of already-done, newly-run, errored.
    """
    appenders: dict[Framing, JSONLAppender] = {}
    done: dict[Framing, set[tuple[int, str, str]]] = {}
    for fr in framings:
        path = gen_path(results_dir, model_id, fr)
        appenders[fr] = JSONLAppender(path)
        done[fr] = completed_gen_keys(appenders[fr].load_all())
        logger.info("framing %s: %d rows already done at %s", fr, len(done[fr]), path)

    pending: list[tuple[Scenario, Condition, Framing, Prompt]] = []
    for s, cond, fr, pr in iter_prompts(scenarios, framings, conditions):
        if (s.id, cond, fr) in done[fr]:
            continue
        pending.append((s, cond, fr, pr))

    if not pending:
        logger.info(
            "nothing to do: all %d calls already complete",
            sum(len(d) for d in done.values()),
        )
        return {"pending": 0, "errored": 0}

    logger.info(
        "running %d pending calls across %d framings (workers=%d)",
        len(pending),
        len(framings),
        max_workers,
    )

    errored = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {
            pool.submit(_run_one, client, s, cond, fr, pr): (s, cond, fr)
            for s, cond, fr, pr in pending
        }
        for fut in tqdm(as_completed(futs), total=len(futs), desc="gen"):
            s, cond, fr = futs[fut]
            try:
                row = fut.result()
            except Exception as e:
                logger.exception(
                    "unexpected error scenario=%d cond=%s fr=%s", s.id, cond, fr
                )
                row = {
                    "scenario_id": s.id,
                    "condition": cond,
                    "framing": fr,
                    "error": f"{type(e).__name__}: {e}",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                }
            if row.get("error"):
                errored += 1
                logger.warning(
                    "gen error scenario=%d cond=%s fr=%s: %s",
                    s.id,
                    cond,
                    fr,
                    row["error"],
                )
            appenders[fr].append(row)

    logger.info("gen complete: %d rows written, %d errors", len(pending), errored)
    return {"pending": len(pending), "errored": errored}
