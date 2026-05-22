# BSc Thesis — Supplementary Materials

Supplementary materials and pipeline code for the BSc thesis **"How does scenario framing affect deceptive tendencies in LLMs?"** by Elias Schlie (Tilburg University, Cognitive Science & Artificial Intelligence, 2026).

The thesis applies a 2×2 within-item factorial to scenarios from **DeceptionBench** (Huang et al., 2025) to measure how scenario framing affects deception rates in LLMs. The factorial independently varies two operations of the narrated-to-interactive transformation: scenario *wording* (narrated vs. interactive) and *delivery structure* (single user message vs. system + user split). DeceptionBench is the source of stimuli and the judge rubric.

## Layout

The repository is organised by **pipeline stage**, mirroring the methods section of the thesis. Each numbered directory holds the inputs, outputs, and validation artifacts for one stage; the implementation code for all stages lives in [`code/`](code/) at the root so that shared Python modules import cleanly.

```
bsc-thesis/
├── README.md
├── LICENSE                          CC BY-SA 4.0
├── 1_translate/                     narrated → interactive translator (§4.2, App. A)
│   ├── prompt.md                      full translator prompt with worked examples
│   ├── input/original.jsonl           DeceptionBench, 150 scenarios (Huang et al., 2025)
│   ├── output/translated.jsonl        translated dataset (68 in-scope, 82 skipped)
│   ├── output/manual_overrides.jsonl  7 scenarios re-classified after AUP refusals
│   ├── logs/                          per-scenario round-trip translator I/O
│   └── validation/                    counterparty-presence κ artifacts (App. C)
├── 2_generate/                      target-model response generation (§4.4)
│   └── output/<model>/gen_<A|B|C|D>.jsonl   raw target-model responses
├── 3_judge/                         deception-label judging (§4.4)
│   ├── output/<model>/                judge verdicts, per-cell results.csv, summary.json
│   └── validation/                    judge-vs-human κ artifacts (§5.4)
├── 4_analyze/                       statistical analysis (§4.5, §5)
│   └── output/                        cell rates, GLMM contrasts, supporting CSVs
├── 5_appendix/
│   └── qwen35_looping/                Qwen3.5-9B looping case study (§5.3)
└── code/                            pipeline implementation
    ├── bench/                         run harness (generation + judge)
    ├── translate/                     translator pipeline
    ├── translate_validation/          counterparty-presence labeling + κ
    ├── judge_validation/              judge–human sample + κ
    └── analysis/                      R + Python analysis scripts
```

The thesis PDF (`thesis.pdf`) will be added when the report is final.

## Environment

Python dependencies and exact versions are pinned in [`pyproject.toml`](pyproject.toml). With [`uv`](https://docs.astral.sh/uv/):

```bash
uv sync                                       # create venv + install pinned deps
uv run python -m code.bench.run --help        # any pipeline command
```

Or with vanilla pip:

```bash
pip install -e .
export PYTHONPATH="$PWD/code:$PYTHONPATH"
```

R dependencies for the analysis stage are listed in [`code/analysis/R_DEPENDENCIES.md`](code/analysis/R_DEPENDENCIES.md). Target R version: 4.3.2.

For end-to-end reruns, create a `.env` file at the repo root with `OPENROUTER_API_KEY` (target-model and judge calls) and `ANTHROPIC_API_KEY` (translator).

## Pointers from the thesis

| Thesis location | Supplementary path |
| --- | --- |
| §4.2, Appendix A — translator prompt with worked examples | [`1_translate/prompt.md`](1_translate/prompt.md) |
| §4.2 — translated dataset | [`1_translate/output/translated.jsonl`](1_translate/output/translated.jsonl) |
| §4.2 — per-scenario round-trip logs | [`1_translate/logs/scenarios/`](1_translate/logs/scenarios/) |
| §4.2 — 7 manually classified scenarios after AUP refusals | [`1_translate/output/manual_overrides.jsonl`](1_translate/output/manual_overrides.jsonl) |
| §4.2, Appendix C — translator-validation rubric and labels | [`1_translate/validation/`](1_translate/validation/) |
| §4.4 — raw target-model responses | [`2_generate/output/<model>/gen_<A\|B\|C\|D>.jsonl`](2_generate/output/) |
| §4.4 — raw judge verdicts | [`3_judge/output/<model>/judge_*.jsonl`](3_judge/output/) |
| §5.3 — Qwen3.5-9B looping reasoning traces | [`5_appendix/qwen35_looping/`](5_appendix/qwen35_looping/) |
| §5.4 — 100 rated cells with judge + human labels | [`3_judge/validation/`](3_judge/validation/) |
| Table 3, Figure 6 — per-cell Wilson 95 % CIs | [`4_analyze/output/cell_deception_rates.csv`](4_analyze/output/cell_deception_rates.csv) |
| Appendix E, Table 4 — per-model planned-contrast estimates | [`4_analyze/output/glmm_contrasts.csv`](4_analyze/output/glmm_contrasts.csv) |
| Table 2 — distribution of contrast estimates across models | [`4_analyze/output/glmm_contrast_summary.csv`](4_analyze/output/glmm_contrast_summary.csv) |

## Reproducing the headline numbers

Given the artifacts in `4_analyze/output/` and the labels under `3_judge/validation/` and `1_translate/validation/`, every headline number in the thesis can be recomputed without rerunning any LLM calls:

- **Cell rates and Wilson CIs (Figure 6, Table 3):** [`4_analyze/output/cell_deception_rates.csv`](4_analyze/output/cell_deception_rates.csv).
- **Per-model planned contrasts (Table 4):** [`4_analyze/output/glmm_contrasts.csv`](4_analyze/output/glmm_contrasts.csv).
- **Distribution across models (Table 2):** [`4_analyze/output/glmm_contrast_summary.csv`](4_analyze/output/glmm_contrast_summary.csv). The substantive threshold used for the `n_above_substantive` columns is **0.36** log-odds (see [`code/analysis/results_pipeline.R`](code/analysis/results_pipeline.R), `SUBSTANTIVE` constant).
- **Judge–human κ (§5.4):** join [`3_judge/validation/sample.jsonl`](3_judge/validation/sample.jsonl) (judge verdict) with [`3_judge/validation/labels_human.jsonl`](3_judge/validation/labels_human.jsonl) (human label) on `sample_id`. The reference implementation is [`code/judge_validation/compute_kappa.py`](code/judge_validation/compute_kappa.py).
- **Translator–human κ on counterparty-presence (§4.2):** join [`1_translate/validation/counterparty_labels.jsonl`](1_translate/validation/counterparty_labels.jsonl) (human) with [`1_translate/output/translated.jsonl`](1_translate/output/translated.jsonl) (translator label, present iff the scenario has no `skip` field) on `id`. Reference implementation: [`code/translate_validation/compute_kappa.py`](code/translate_validation/compute_kappa.py).

## Related repositories

- **Upstream benchmark:** DeceptionBench (Huang et al., 2025), https://github.com/Aries-iai/DeceptionBench — source of `1_translate/input/original.jsonl`, the prompt-derivation conventions, and the judge rubric used by [`code/bench/judge.py`](code/bench/judge.py).
- **Upstream dataset:** https://huggingface.co/datasets/skyai798/DeceptionBench.

## File formats

All tabular data is CSV with a header row. All other data is JSONL (one JSON object per line). Notable conventions:

- `1_translate/output/translated.jsonl` keys per scenario: `id`, `topic`, `dimension`, `question`, `groundtruth`, `goal`, and either `skip: "no direct counterparty"` (82 scenarios) or `conditions` mapping each of the six DeceptionBench motive variants (`L1-self`, `L1-other`, `L2-self-pressure`, `L2-self-reward`, `L2-other-pressure`, `L2-other-reward`) to a `{system_prompt, user_message, split_token, original}` quadruple.
- `1_translate/logs/scenarios/translate_<id>.jsonl` has one event per line: `init` (prompt sent), `run_start` (input message), `assistant_message` (raw model output), `run_complete` (timing and cost). Replaying these events against the same translator model and prompt reproduces `1_translate/output/translated.jsonl`.
- `2_generate/output/<model>/gen_<framing>.jsonl` has one row per (scenario, condition) call with the full request prompt, raw + cleaned response, token usage, latency, attempt count, and any final error.
- `3_judge/output/<model>/judge_<judge>_<framing>.jsonl` has one row per scenario carrying the parsed `{condition: {thought, response}}` verdict, the raw judge text, and a `parse_error` flag.
- `3_judge/validation/sample.jsonl` includes the full prompt, raw model response, cleaned response, and judge verdict for each of the 100 cells; `labels_human.jsonl` records the blind human label keyed by `sample_id`.

## Attribution and license

Licensed under **CC BY-SA 4.0** — see [`LICENSE`](LICENSE) or https://creativecommons.org/licenses/by-sa/4.0/.

The upstream DeceptionBench repository releases its codebase under CC BY-SA 4.0. Portions of this repository derived from DeceptionBench — including `1_translate/input/original.jsonl`, the judge rubric in [`code/bench/judge.py`](code/bench/judge.py), and any scenario text copied verbatim into translated outputs — therefore retain CC BY-SA 4.0. Any redistribution or derivative of this repository must retain attribution and use the same license (ShareAlike).

### Note on the upstream license

The upstream DeceptionBench [readme.md](https://github.com/Aries-iai/DeceptionBench/blob/main/readme.md) "License" section contains two statements that, read together, are internally inconsistent:

> - The codebase is licensed under the **CC BY-SA 4.0** license.
> - DeceptionBench is only used for academic research. Commercial use in any form is prohibited.

CC BY-SA 4.0 explicitly permits commercial use, so the second line cannot be a clause *of* CC BY-SA 4.0. The DeceptionBench dataset on [Hugging Face](https://huggingface.co/datasets/skyai798/DeceptionBench), which is the source of `1_translate/input/original.jsonl`, is tagged in its dataset card metadata cleanly as `license: cc-by-sa-4.0` with no non-commercial qualifier. I treat that structured, formal grant as authoritative for the data in this repository and apply CC BY-SA 4.0 to my own derivative work accordingly.

A more conservative reading would treat the upstream readme's "no commercial use" line as the licensors' intent and apply CC BY-NC-SA 4.0 to derivatives. Downstream redistributors who want to honour that intent strictly may relicense their own derivatives of this repository as CC BY-NC-SA 4.0 (such a relicensing is permitted under CC's compatibility framework). The thesis itself is academic research and so respects the upstream's stated wish under either reading.

If you use these materials, please cite the thesis and the upstream DeceptionBench paper:

> Schlie, E. (2026). *How does scenario framing affect deceptive tendencies in LLMs?* BSc thesis, Tilburg University, Cognitive Science & Artificial Intelligence.

> Huang, Y., Sun, Y., Zhang, Y., Zhang, R., Dong, Y., & Wei, X. (2025). DeceptionBench: A comprehensive benchmark for AI deception behaviors in real-world scenarios. *Advances in Neural Information Processing Systems*.
