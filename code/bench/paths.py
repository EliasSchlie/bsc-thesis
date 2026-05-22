"""Filesystem layout for bench outputs, aligned with the supplementary-materials
pipeline-staged layout:

<root>/2_generate/output/<target_model_slug>/
    gen_<framing>.jsonl
    runs/<stamp>_<command>.log
    runs/<stamp>_<command>.config.json
<root>/3_judge/output/<target_model_slug>/
    judge_<judge_model_slug>_<framing>.jsonl

`results_dir` is the repository root (default ".").
"""

from __future__ import annotations

from pathlib import Path

from bench.dataset import Framing


GEN_STAGE_DIR = Path("2_generate") / "output"
JUDGE_STAGE_DIR = Path("3_judge") / "output"


def slug(model_id: str) -> str:
    """Filesystem-safe slug, e.g. Qwen/Qwen3-30B-... -> Qwen__Qwen3-30B-..."""
    return model_id.replace("/", "__").replace(" ", "_")


def model_dir(results_dir: Path, model_id: str) -> Path:
    """Generation outputs for a target model (gen_*.jsonl + runs/)."""
    return results_dir / GEN_STAGE_DIR / slug(model_id)


def judge_model_dir(results_dir: Path, model_id: str) -> Path:
    """Judge outputs for a target model (judge_*.jsonl)."""
    return results_dir / JUDGE_STAGE_DIR / slug(model_id)


def runs_dir(results_dir: Path, model_id: str) -> Path:
    return model_dir(results_dir, model_id) / "runs"


def gen_path(results_dir: Path, model_id: str, framing: Framing) -> Path:
    return model_dir(results_dir, model_id) / f"gen_{framing}.jsonl"


def judge_path(
    results_dir: Path, target_model: str, judge_model: str, framing: Framing
) -> Path:
    return (
        judge_model_dir(results_dir, target_model)
        / f"judge_{slug(judge_model)}_{framing}.jsonl"
    )
