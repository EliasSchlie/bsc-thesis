# code/

Pipeline implementation. Each subdirectory is the Python package or set of scripts that produces the outputs of one stage. The modules import each other (`from bench.dataset import ...`), so the entire `code/` tree must be on `PYTHONPATH` to run end-to-end:

```bash
# from the repository root
export PYTHONPATH="$PWD/code:$PYTHONPATH"
```

Python dependencies and versions are pinned in [`../pyproject.toml`](../pyproject.toml). R dependencies for the analysis stage are listed in [`analysis/R_DEPENDENCIES.md`](analysis/R_DEPENDENCIES.md).

## Layout

```
code/
├── bench/                          run harness
│   ├── dataset.py                    scenarios / conditions / framings
│   ├── generate.py                   target-model generation under each framing
│   ├── io.py                         JSONL append, resume keys
│   ├── judge.py                      judge harness + verbatim DeceptionBench rubric
│   ├── llm.py                        OpenAI-compatible client (used for OpenRouter)
│   ├── log.py                        per-run stamps and config snapshots
│   ├── paths.py                      filesystem layout helpers
│   ├── run.py                        CLI: `gen`, `judge`, `summarize`, `all`
│   └── summarize.py                  per-cell and per-framing aggregates
├── translate/                      narrated → interactive translator (stage 1)
│   ├── claude.py                     Claude Agent SDK wrapper
│   ├── translate.py                  single-scenario translation logic
│   ├── runlog.py                     per-run manifest + per-scenario logging
│   ├── overrides.py                  loading and applying manual overrides
│   ├── apply_overrides.py            merge step
│   └── run.py                        CLI entry point
├── translate_validation/           translator κ (stage 1 validation)
│   ├── counterparty_check.py         blind labeling UI (port 8002)
│   ├── spot_check.py                 translation quality UI (port 8001)
│   └── compute_kappa.py              Cohen's κ + confusion matrix
├── judge_validation/               judge κ (stage 3 validation)
│   ├── sample.py                     stratified sampler
│   ├── label_ui.py                   blind labeling UI (port 8003)
│   └── compute_kappa.py              Cohen's κ overall + per framing
└── analysis/                       statistical analysis (stage 4)
    ├── results_pipeline.R            primary R pipeline (Tables 2-4, Figure 6 data)
    ├── thesis_tables.py              successor-pair table for §5.2
    └── show_disagreements.py         renders 4_analyze/output/disagreements.md
```

## Configuration

API keys are read from a `.env` file at the repo root. Create one with:

- `OPENROUTER_API_KEY` — target-model and judge calls
- `ANTHROPIC_API_KEY` — translator (Claude Opus 4.7 via Claude Agent SDK)

## Path conventions

The CLI defaults assume invocation from the repository root and write into the pipeline-staged layout automatically. `bench/paths.py` resolves:

- gen outputs → `2_generate/output/<model_slug>/gen_<framing>.jsonl`
- judge outputs → `3_judge/output/<model_slug>/judge_<judge_slug>_<framing>.jsonl`
- summary + flat results → `3_judge/output/<model_slug>/{summary.json,results.csv}`

Typical invocations:

```bash
# from the repository root
python -m bench.run gen   --model deepseek/deepseek-r1
python -m bench.run judge --target-model deepseek/deepseek-r1 \
                          --judge-model openai/gpt-5.4-nano
python -m bench.run all   --model deepseek/deepseek-r1 \
                          --judge-model openai/gpt-5.4-nano
```

Override `--data` to point at a different scenarios file, or `--results-dir` to write outside the repo. See `python -m bench.run --help` for the full surface.
