"""Clean per-run logging.

Each invocation of `bench.run` writes:
  runs/<UTC ISO timestamp>_<command>.log    -- human-readable INFO/WARNING/ERROR
  runs/<UTC ISO timestamp>_<command>.config.json  -- full run config snapshot

Per-row structured data stays in the JSONL files. The log file is for sequence,
timing, and errors -- everything you'd want to read to understand "what happened
during this run".
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any


def run_stamp() -> str:
    """UTC timestamp like 20260422T172203Z. Sortable, filename-safe, no colons."""
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def setup_run_logging(
    runs_dir: Path,
    stamp: str,
    command: str,
    verbose: bool = False,
) -> Path:
    """Install a file + stream handler for this run. Returns the log path."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    log_path = runs_dir / f"{stamp}_{command}.log"

    root = logging.getLogger()
    # Clear any pre-existing handlers so repeated invocations in the same
    # process (tests, notebooks) don't accumulate duplicate handlers.
    root.handlers.clear()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG if verbose else logging.INFO)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    return log_path


def write_config_snapshot(
    runs_dir: Path,
    stamp: str,
    command: str,
    config: dict[str, Any],
) -> Path:
    """Freeze the run's config (args, model, data hash, env) to disk."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = runs_dir / f"{stamp}_{command}.config.json"
    cfg_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    return cfg_path
