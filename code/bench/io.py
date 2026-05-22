"""JSONL append-only storage with id-based resumption.

Every generation call and every judge call is a row. Primary key:
- gen row:   (scenario_id, condition, framing)
- judge row: (scenario_id, framing) -- one judge call batches 6 conditions

On resume, we read the output file once, collect completed keys, and skip them.
Rows with `error` set are NOT counted as done, so retries sweep them up.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


class JSONLAppender:
    """Thread-safe JSONL writer. Flushes + fsyncs each append so rows survive SIGKILL."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, row: dict[str, Any]) -> None:
        line = json.dumps(row, ensure_ascii=False, default=str)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())

    def load_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.warning("skipping malformed row in %s: %s", self.path, e)
        return rows


def completed_gen_keys(rows: Iterable[dict[str, Any]]) -> set[tuple[int, str, str]]:
    keys: set[tuple[int, str, str]] = set()
    for r in rows:
        if r.get("error"):
            continue
        try:
            keys.add((r["scenario_id"], r["condition"], r["framing"]))
        except KeyError:
            continue
    return keys


def completed_judge_keys(rows: Iterable[dict[str, Any]]) -> set[tuple[int, str]]:
    keys: set[tuple[int, str]] = set()
    for r in rows:
        if r.get("error"):
            continue
        try:
            keys.add((r["scenario_id"], r["framing"]))
        except KeyError:
            continue
    return keys
