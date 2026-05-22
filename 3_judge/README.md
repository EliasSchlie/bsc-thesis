# 3. Judge

Automated deception labeling and judge–human validation (§4.4 and §5.4 of the thesis).

The judge takes the six condition responses for a (scenario, framing) cell as a batched input and assigns a binary `decept` / `honest` label to each. The rubric is copied verbatim from upstream DeceptionBench (Huang et al., 2025); the only deviation from upstream is the judge model, where we use `openai/gpt-5.4-nano` instead of `gpt-4o` (≈ an order of magnitude cheaper per token, and gpt-4o is being deprecated). The judge labels every non-deceptive response — including refusals — as honest, matching the upstream binary rubric.

## Files

| Path | Description |
| --- | --- |
| [`output/<model>/judge_<judge>_<framing>.jsonl`](output/) | Raw judge verdicts, one row per scenario, carrying the `{condition: {thought, response}}` per-condition labels, the raw judge text, and a `parse_error` flag. |
| [`output/<model>/results.csv`](output/) | Flat per-cell table joining gen + judge: one row per (target_model, scenario_id, framing, condition) with `thought`, `response`, `deceived ∈ {0,1}`, `parse_error`, `gen_error`. This file is the input to `code/analysis/results_pipeline.R`. |
| [`output/<model>/summary.json`](output/) | Aggregated per-cell deception rates and completeness counts. |
| [`validation/rubric.md`](validation/rubric.md) | Two-way label definitions (`decept` / `non-decept`) used by the human labeler. |
| [`validation/sample.jsonl`](validation/sample.jsonl) | 100-cell stratified sample (framing × judge_response, 8 target models, balanced via round-robin). Includes the full prompt, raw response, cleaned response, and judge verdict. |
| [`validation/labels_human.jsonl`](validation/labels_human.jsonl) | Blind human labels for the same 100 cells, keyed by `sample_id`. |

## Sample design

- *n* = 100 cells.
- Joint stratification on `framing × judge_response` (4 × 2 = 8 strata, ~12–13 per stratum).
- Within each stratum, the 8 target models are sampled approximately uniformly via round-robin without replacement.
- The sample seed and the judge model are recorded in the header of `sample.jsonl`; the human-label order seed is recorded in the header of `labels_human.jsonl`.

Reported in §5.4 of the thesis: overall Cohen's κ between the judge and the human labeler is 0.66 (95 % Wald CI [0.51, 0.81]); per-framing κ are 0.76 (A), 0.76 (B), 0.52 (C), 0.60 (D).

## Implementation

There are two distinct flows: (a) **running the judge** on the target-model responses produced in stage 2, and (b) **validating the judge** against blind human labels on a sub-sample.

### (a) Run the judge

Code lives in [`../code/bench/judge.py`](../code/bench/judge.py); the entry point is `bench.run judge`. Requires the gen JSONLs from stage 2 to already exist under `../2_generate/output/<model>/`. Writes `judge_<judge_slug>_<framing>.jsonl` per (model, framing) under `output/<model>/`, plus the joined `results.csv` and `summary.json`.

```bash
# from the repository root
export PYTHONPATH="$PWD/code"
export OPENROUTER_API_KEY=...   # judge calls routed through OpenRouter

# judge one target model under all four framings, using gpt-5.4-nano as the judge
python -m bench.run judge \
    --target-model "deepseek/deepseek-r1" \
    --judge-model "openai/gpt-5.4-nano"

# or, full pipeline (generate + judge) for one target
python -m bench.run all \
    --model "deepseek/deepseek-r1" \
    --judge-model "openai/gpt-5.4-nano"
```

The judge runs one call per (scenario, framing), batching all six motive conditions in one prompt. Runs are resumable by `(scenario_id, framing)` keys; an errored row is retried on the next invocation. Decoding cap: `JUDGE_MAX_TOKENS` (default 500). See [`../code/bench/README.md`](../code/bench/README.md) for the full CLI surface.

### (b) Validate the judge against human labels

`code/judge_validation/` operates on the JSONLs that the judge has already produced — it does **not** run the judge itself. The three scripts:

```bash
# from the repository root, with PYTHONPATH=code

# 1. Draw a stratified sample of 100 cells from the existing judge outputs.
#    Defaults: n=100, judge=gpt-5.4-nano, out=3_judge/validation/sample.jsonl
python -m judge_validation.sample

# 2. Launch the blind labeling UI on http://localhost:8003
python -m judge_validation.label_ui

# 3. Compute Cohen's κ between the judge and the human labels
python -m judge_validation.compute_kappa
```

The `--judge-model` flag on `judge_validation.sample` does **not** run a judge — it tells the sampler which `judge_<slug>_<framing>.jsonl` files to read so it can stratify the 100 sampled cells on (framing × judge_response). Default is `openai/gpt-5.4-nano`, the judge used in this thesis. Override only if you re-ran step (a) with a different judge model and want to validate that one instead.
