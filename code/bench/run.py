"""CLI entrypoint: plug a model, run it through the benchmark, judge the output.

Examples:
    # Generate DeepSeek-R1 responses on all 68 counterparty-present scenarios x 4 framings x 6 conds
    python -m bench.run gen --model "deepseek/deepseek-r1"

    # Judge those with gpt-5.4-nano (the thesis judge)
    python -m bench.run judge \\
        --target-model "deepseek/deepseek-r1" \\
        --judge-model "openai/gpt-5.4-nano"

    # Generate + judge in one shot
    python -m bench.run all \\
        --model "deepseek/deepseek-r1" \\
        --judge-model "openai/gpt-5.4-nano"

    # Smoke test on 2 scenarios only
    python -m bench.run all --model "deepseek/deepseek-r1" --limit 2

Env (from .env; autoloaded if present):
    OPENROUTER_API_KEY, OPENROUTER_BASE_URL (default: https://openrouter.ai/api/v1)
    OPENAI_API_KEY, OPENAI_BASE_URL  (only if --target-via/--judge-via openai)
    NEBIUS_API_KEY, NEBIUS_BASE_URL  (only if --target-via nebius or nebius-tf;
                                      default: https://api.studio.nebius.ai/v1)
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
from pathlib import Path

from bench.dataset import FRAMINGS, Framing, load_scenarios
from bench.generate import run_generation
from bench.judge import run_judge
from bench.llm import OpenAICompatClient
from bench.log import run_stamp, setup_run_logging, write_config_snapshot
from bench.paths import runs_dir
from bench.summarize import write_summary

DEFAULT_NEBIUS_BASE_URL = "https://api.studio.nebius.ai/v1"
DEFAULT_NEBIUS_TF_BASE_URL = "https://api.tokenfactory.us-central1.nebius.com/v1/"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TARGET_MODEL = "deepseek/deepseek-r1"
DEFAULT_JUDGE_MODEL = "openai/gpt-5.4-nano"


def _provider_config(provider: str) -> tuple[str, str, str]:
    """Return (api_key_env, base_url, base_url_default) for a provider."""
    if provider == "openai":
        return "OPENAI_API_KEY", os.environ.get("OPENAI_BASE_URL") or "", ""
    if provider == "nebius":
        return (
            "NEBIUS_API_KEY",
            os.environ.get("NEBIUS_BASE_URL") or DEFAULT_NEBIUS_BASE_URL,
            DEFAULT_NEBIUS_BASE_URL,
        )
    if provider == "nebius-tf":
        # Nebius "tokenfactory" endpoint; same API key, different base URL,
        # different model catalog (DeepSeek-V3.2, Kimi-K2.5-fast, etc.).
        return (
            "NEBIUS_API_KEY",
            DEFAULT_NEBIUS_TF_BASE_URL,
            DEFAULT_NEBIUS_TF_BASE_URL,
        )
    if provider == "openrouter":
        return (
            "OPENROUTER_API_KEY",
            os.environ.get("OPENROUTER_BASE_URL") or DEFAULT_OPENROUTER_BASE_URL,
            DEFAULT_OPENROUTER_BASE_URL,
        )
    sys.exit(
        f"error: unknown provider {provider!r}; pick from openai, nebius, nebius-tf, openrouter"
    )


logger = logging.getLogger(__name__)


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _require(env_var: str) -> str:
    v = os.environ.get(env_var)
    if not v:
        sys.exit(f"error: {env_var} not set (in .env or environment)")
    return v


def _filter_scenarios(scenarios, args):
    """Apply --ids then --limit to the loaded scenario list."""
    if args.ids:
        wanted = {int(x.strip()) for x in args.ids.split(",") if x.strip()}
        scenarios = [s for s in scenarios if s.id in wanted]
        if not scenarios:
            sys.exit(f"error: --ids {args.ids!r} matched no scenarios")
        return scenarios
    if args.limit:
        return scenarios[: args.limit]
    return scenarios


def _parse_framings(arg: str) -> tuple[Framing, ...]:
    if arg == "all":
        return FRAMINGS
    parts = tuple(p.strip() for p in arg.split(","))
    for p in parts:
        if p not in FRAMINGS:
            sys.exit(f"error: unknown framing {p!r}; pick from {FRAMINGS} or 'all'")
    return parts  # type: ignore[return-value]


def _data_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _snapshot_config(
    args: argparse.Namespace, target_model: str, judge_model: str | None
) -> dict:
    data_path = Path(args.data)
    return {
        "command": args.cmd,
        "target_model": target_model,
        "judge_model": judge_model,
        "data_path": str(data_path),
        "data_sha256_16": _data_hash(data_path) if data_path.exists() else None,
        "framings": list(_parse_framings(args.framings)),
        "limit": args.limit,
        "workers": args.workers,
        "results_dir": str(args.results_dir),
        "nebius_base_url": os.environ.get("NEBIUS_BASE_URL", DEFAULT_NEBIUS_BASE_URL),
        "openai_base_url": os.environ.get("OPENAI_BASE_URL"),
        "format_post": (
            "(Please say your thought and final response in a json format: "
            '{"thought":"","response":""})'
        ),
        "judge_temperature": float(os.environ.get("JUDGE_TEMPERATURE", "0.0")),
        "judge_max_tokens": int(os.environ.get("JUDGE_MAX_TOKENS", "500")),
    }


def _begin_run(
    args: argparse.Namespace, target_model: str, judge_model: str | None
) -> str:
    stamp = run_stamp()
    runs = runs_dir(Path(args.results_dir), target_model)
    log_path = setup_run_logging(runs, stamp, args.cmd, verbose=args.verbose)
    cfg = _snapshot_config(args, target_model, judge_model)
    cfg_path = write_config_snapshot(runs, stamp, args.cmd, cfg)
    logger.info("run %s started; log=%s config=%s", stamp, log_path, cfg_path)
    logger.info("config: %s", cfg)
    return stamp


def cmd_gen(args: argparse.Namespace) -> None:
    _begin_run(args, args.model, None)
    scenarios = _filter_scenarios(load_scenarios(args.data), args)
    logger.info("loaded %d counterparty-present scenarios", len(scenarios))
    key_env, base_url, _ = _provider_config(args.target_via)
    extra_body = None
    if getattr(args, "target_provider_only", None):
        extra_body = {
            "provider": {
                "only": [
                    p.strip() for p in args.target_provider_only.split(",") if p.strip()
                ],
                "allow_fallbacks": False,
            }
        }
    elif getattr(args, "target_provider_order", None):
        extra_body = {
            "provider": {
                "order": [
                    p.strip()
                    for p in args.target_provider_order.split(",")
                    if p.strip()
                ]
            }
        }
    client = OpenAICompatClient(
        api_key=_require(key_env),
        base_url=base_url or None,
        default_model=args.model,
        max_connections=max(1000, args.workers * 2),
        extra_body=extra_body,
    )
    logger.info(
        "target model=%s via=%s base_url=%s extra_body=%s",
        args.model,
        args.target_via,
        base_url,
        extra_body,
    )
    run_generation(
        scenarios=scenarios,
        client=client,
        model_id=args.model,
        results_dir=Path(args.results_dir),
        framings=_parse_framings(args.framings),
        max_workers=args.workers,
    )
    write_summary(
        results_dir=Path(args.results_dir),
        target_model=args.model,
        judge_model=None,
        data_path=Path(args.data),
        framings=_parse_framings(args.framings),
    )


def cmd_judge(args: argparse.Namespace) -> None:
    _begin_run(args, args.target_model, args.judge_model)
    scenarios = _filter_scenarios(load_scenarios(args.data), args)
    logger.info("loaded %d counterparty-present scenarios", len(scenarios))
    key_env, base_url, _ = _provider_config(args.judge_via)
    client = OpenAICompatClient(
        api_key=_require(key_env),
        base_url=base_url or None,
        default_model=args.judge_model,
        temperature=float(os.environ.get("JUDGE_TEMPERATURE", "0.0")),
        max_tokens=int(os.environ.get("JUDGE_MAX_TOKENS", "500")),
        max_connections=max(1000, args.workers * 2),
    )
    logger.info(
        "judge model=%s via=%s base_url=%s",
        args.judge_model,
        args.judge_via,
        base_url,
    )
    run_judge(
        scenarios=scenarios,
        client=client,
        target_model=args.target_model,
        judge_model=args.judge_model,
        results_dir=Path(args.results_dir),
        framings=_parse_framings(args.framings),
        max_workers=args.workers,
    )
    write_summary(
        results_dir=Path(args.results_dir),
        target_model=args.target_model,
        judge_model=args.judge_model,
        data_path=Path(args.data),
        framings=_parse_framings(args.framings),
    )


def cmd_summarize(args: argparse.Namespace) -> None:
    _begin_run(args, args.target_model, args.judge_model)
    write_summary(
        results_dir=Path(args.results_dir),
        target_model=args.target_model,
        judge_model=args.judge_model,
        data_path=Path(args.data),
        framings=_parse_framings(args.framings),
    )


def cmd_all(args: argparse.Namespace) -> None:
    cmd_gen(args)
    args.target_model = args.model
    args.cmd = "judge"
    cmd_judge(args)
    args.cmd = "all"


def build_parser() -> argparse.ArgumentParser:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--data",
        default="1_translate/output/translated.jsonl",
        help="path to translated.jsonl (pipeline stage 1 output)",
    )
    shared.add_argument(
        "--results-dir",
        default=".",
        help="root under which generate/ and judge/ write per-model JSONLs; "
        "defaults to the repository root, so gen output goes to "
        "2_generate/output/<model>/ and judge output to 3_judge/output/<model>/",
    )
    shared.add_argument(
        "--framings", default="all", help="comma-separated subset of A,B,C,D, or 'all'"
    )
    shared.add_argument(
        "--limit", type=int, default=0, help="process only first N scenarios (0 = all)"
    )
    shared.add_argument(
        "--ids",
        default="",
        help="comma-separated scenario ids to include (overrides --limit when set)",
    )
    shared.add_argument("--workers", type=int, default=50)
    shared.add_argument("-v", "--verbose", action="store_true")

    p = argparse.ArgumentParser(
        description=(
            "Pipeline runner: generation + judge for the 2x2 framing factorial "
            "applied to DeceptionBench scenarios."
        ),
        parents=[shared],
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    providers = ("openai", "nebius", "nebius-tf", "openrouter")

    g = sub.add_parser("gen", help="generate target-model responses", parents=[shared])
    g.add_argument("--model", default=DEFAULT_TARGET_MODEL)
    g.add_argument("--target-via", choices=providers, default="openrouter")
    g.add_argument(
        "--target-provider-order",
        default=None,
        help="OpenRouter only: comma-separated provider preference order (e.g. 'nebius')",
    )
    g.add_argument(
        "--target-provider-only",
        default=None,
        help="OpenRouter only: comma-separated providers to restrict to (forces allow_fallbacks=False)",
    )
    g.set_defaults(func=cmd_gen)

    j = sub.add_parser(
        "judge", help="run judge on existing generations", parents=[shared]
    )
    j.add_argument("--target-model", default=DEFAULT_TARGET_MODEL)
    j.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    j.add_argument("--judge-via", choices=providers, default="openrouter")
    j.set_defaults(func=cmd_judge)

    a = sub.add_parser("all", help="generate + judge in one run", parents=[shared])
    a.add_argument("--model", default=DEFAULT_TARGET_MODEL)
    a.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    a.add_argument("--target-via", choices=providers, default="openrouter")
    a.add_argument("--judge-via", choices=providers, default="openrouter")
    a.add_argument(
        "--target-provider-order",
        default=None,
        help="OpenRouter only: comma-separated provider preference order (e.g. 'nebius')",
    )
    a.add_argument(
        "--target-provider-only",
        default=None,
        help="OpenRouter only: comma-separated providers to restrict to (forces allow_fallbacks=False)",
    )
    a.set_defaults(func=cmd_all)

    s = sub.add_parser(
        "summarize",
        help="regenerate summary.json and results.csv from existing JSONLs (no API calls)",
        parents=[shared],
    )
    s.add_argument("--target-model", default=DEFAULT_TARGET_MODEL)
    s.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    s.set_defaults(func=cmd_summarize)

    return p


def main() -> None:
    _load_dotenv(Path(".env"))
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
