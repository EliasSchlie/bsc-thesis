"""Per-run manifest and log layout for the translate stage.

Each invocation of code/translate/run.py writes to
1_translate/logs/translate_{ts}/:
    manifest.json        - input hash, model, args, summary
    scenarios/*.jsonl    - per-scenario round-trip (one file per scenario id)

The manifest is finalized at the end of the run with output hash and counts.
Paths in the manifest are stored relative to the repository root when
possible, so logs port cleanly between machines.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


# code/translate/runlog.py  →  parent.parent.parent = repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class RunManifest:
    stage: str
    run_id: str
    run_dir: Path
    started_at: float
    model: str | None
    input_path: str
    input_sha256: str
    args: dict[str, Any]
    output_path: str | None = None
    output_sha256: str | None = None
    finished_at: float | None = None
    duration_s: float | None = None
    n_scenarios: int | None = None
    n_translated: int | None = None
    n_skipped: int | None = None
    n_errors: int | None = None
    scenario_logs: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        d = asdict(self)
        d["run_dir"] = _rel(self.run_dir)
        return json.dumps(d, indent=2, default=str)

    def write(self) -> None:
        (self.run_dir / "manifest.json").write_text(self.to_json())


def create_run(
    stage: str,
    input_path: Path,
    model: str | None,
    args: dict[str, Any],
    logs_root: Path | None = None,
) -> RunManifest:
    """Create a fresh run directory and initial manifest."""
    ts = int(time.time())
    run_id = f"{stage}_{ts}"
    logs_root = logs_root or (REPO_ROOT / "1_translate" / "logs")
    run_dir = logs_root / run_id
    (run_dir / "scenarios").mkdir(parents=True, exist_ok=True)

    manifest = RunManifest(
        stage=stage,
        run_id=run_id,
        run_dir=run_dir,
        started_at=time.time(),
        model=model,
        input_path=_rel(input_path),
        input_sha256=_sha256_of_file(input_path),
        args=args,
    )
    manifest.write()
    return manifest


def _rel(p: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def scenario_log_path(manifest: RunManifest, scenario_id: int | str) -> Path:
    path = manifest.run_dir / "scenarios" / f"translate_{scenario_id}.jsonl"
    manifest.scenario_logs.append(path.name)
    return path


def finalize_run(
    manifest: RunManifest,
    output_path: Path,
    n_scenarios: int,
    n_translated: int,
    n_skipped: int,
    n_errors: int,
) -> None:
    manifest.finished_at = time.time()
    manifest.duration_s = manifest.finished_at - manifest.started_at
    manifest.output_path = _rel(output_path)
    manifest.output_sha256 = (
        _sha256_of_file(output_path) if output_path.exists() else None
    )
    manifest.n_scenarios = n_scenarios
    manifest.n_translated = n_translated
    manifest.n_skipped = n_skipped
    manifest.n_errors = n_errors
    manifest.write()
