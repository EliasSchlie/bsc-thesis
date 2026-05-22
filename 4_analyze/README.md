# 4. Analyze

Statistical analysis backing the figures and tables in §5 of the thesis.

The primary analysis fits one binomial GLMM per target model:

```r
glmer(deceived ~ wording * split + (1 | item_id), family = binomial)
```

where `wording ∈ {narrated, interactive}`, `split ∈ {single, split}`, and `item_id` indexes each (scenario, motive condition) pair. Three planned contrasts are computed per model via `emmeans`:

- **Sub-RQ1 (wording):** main effect of wording, `{C, D} – {A, B}`.
- **Sub-RQ2 (split):** main effect of delivery-structure split, `{B, D} – {A, C}`.
- **Sub-RQ3 (interaction):** wording-by-split interaction.

Each contrast is reported on two scales: the log-odds difference β with a 95 % Wald CI, and the percentage-point shift in the deception rate (computed from the empirical cell rates with a normal-approximation 95 % CI).

The substantive threshold is **|β| ≥ 0.36** log-odds (Cohen-small *d* = 0.2 via Chinn 2000 conversion). See `SUBSTANTIVE` in [`../code/analysis/results_pipeline.R`](../code/analysis/results_pipeline.R).

## Files

Every file in `output/` directly backs a thesis claim or figure.

| Path | Backs |
| --- | --- |
| [`output/cell_deception_rates.csv`](output/cell_deception_rates.csv) | Figure 6 + Table 3 — per-(model, framing) deception rate with Wilson 95 % CIs. |
| [`output/glmm_contrasts.csv`](output/glmm_contrasts.csv) | Appendix E / Table 4 — per-model planned-contrast estimates (Sub-RQ1, Sub-RQ2, Sub-RQ3) with 95 % CIs on log-odds and percentage-point scales. |
| [`output/glmm_contrast_summary.csv`](output/glmm_contrast_summary.csv) | Table 2 — cross-model distribution of contrast estimates (median, range, count of CIs excluding zero, count above ±0.36). |
| [`output/glmm_diagnostics.csv`](output/glmm_diagnostics.csv) | §4.5 GLMM fit diagnostics (singular fits, item-intercept SD, min cell count) — supporting due-diligence artifact. |
| [`output/successor_pairs.csv`](output/successor_pairs.csv) | §5.2 — per-vendor old vs. new deltas ("OpenAI −12 to −40pp, Qwen −46 to −48pp …"). Wide format (per-framing + mean per pair). |
| [`output/successor_pairs_long.csv`](output/successor_pairs_long.csv) | §5.2 — long-format equivalent. |
| [`output/qwen35_loop_summary.csv`](output/qwen35_loop_summary.csv) | §5.3 — Qwen3.5-9B empty-response rate by framing (A: 33.6 %, B: 40.9 %, C: 35.8 %, D: 44.9 %). |
| [`output/qwen35_glmm_dual.csv`](output/qwen35_glmm_dual.csv) | §5.3 — side-by-side GLMM fits on all-cells vs. responder-only data for Qwen3.5-9B. |
| [`output/qwen35_responder_rates_by_framing.csv`](output/qwen35_responder_rates_by_framing.csv) | Table 3 (parens for Qwen3.5-9B) — deception rate per framing on cells where the model emitted a response. |
| [`output/qwen35_response_subset.csv`](output/qwen35_response_subset.csv) | §5.3 — the responder-only subset used for the dual GLMM fit. |
| [`output/judge_kappa.csv`](output/judge_kappa.csv) | §5.4 — overall and per-framing Cohen's κ between the judge and the human labeler, with confusion-matrix counts. |
| [`output/translator_kappa.csv`](output/translator_kappa.csv) | §4.2 / Appendix C — Cohen's κ between the translator's counterparty classification and the blind manual labels. |
| [`output/disagreements.md`](output/disagreements.md) | §5.4 — per-cell rendering of the 17 judge–human disagreements (8 FP + 9 FN) for qualitative inspection. |

## Implementation

Analysis code: [`../code/analysis/`](../code/analysis/). R dependencies are listed in [`../code/analysis/R_DEPENDENCIES.md`](../code/analysis/R_DEPENDENCIES.md).

```bash
# from the repo root, with PYTHONPATH=code
Rscript code/analysis/results_pipeline.R   # primary pipeline (Tables 2-4, Figure 6 data)
python -m analysis.thesis_tables           # successor-pairs table + console digest
python -m analysis.show_disagreements      # writes disagreements.md
python -m judge_validation.compute_kappa   # writes judge_kappa.csv
python -m translate_validation.compute_kappa  # writes translator_kappa.csv
```
