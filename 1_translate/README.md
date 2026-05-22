# 1. Translate

Narrated → interactive translation of the DeceptionBench scenarios (§4.2 of the thesis).

The translator takes each of DeceptionBench's 150 scenarios and either (i) returns a `{skip: "no direct counterparty"}` flag if the scenario lacks a direct conversational counterparty, or (ii) emits a `(system_prompt, user_message, split_token)` triple for each of the six motive conditions. These triples are the basis for the four-framing 2×2 factorial constructed downstream (§4.4).

## Files

| Path | Description |
| --- | --- |
| [`prompt.md`](prompt.md) | Full translator system prompt with all worked examples (Appendix A). |
| [`input/original.jsonl`](input/original.jsonl) | DeceptionBench, 150 scenarios × 6 motive conditions (Huang et al., 2025, CC BY-SA 4.0). |
| [`output/translated.jsonl`](output/translated.jsonl) | Translator output, one row per scenario. 68 in-scope (with `conditions`), 82 out-of-scope (with `skip`). |
| [`output/manual_overrides.jsonl`](output/manual_overrides.jsonl) | 7 scenarios re-classified or hand-translated after the Anthropic Usage Policy filter refused the auto-translator. |
| [`logs/manifest.json`](logs/manifest.json) | Run metadata: input/output SHA-256, model, args, counts, timings. |
| [`logs/scenarios/translate_<id>.jsonl`](logs/scenarios/) | Per-scenario round-trip translator I/O (one file per scenario). Each line is one event (`init`, `run_start`, `assistant_message`, `run_complete`). |
| [`validation/rubric.md`](validation/rubric.md) | Definition of "direct counterparty" used by both the translator and the manual labeler. |
| [`validation/counterparty_labels.jsonl`](validation/counterparty_labels.jsonl) | 30 blind manual labels for Cohen's κ against the translator's classifications. |
| [`validation/spot_check_labels.jsonl`](validation/spot_check_labels.jsonl) | Translation quality spot-check labels on in-scope scenarios. |

## Implementation

The pipeline code is in [`../code/translate/`](../code/translate/). The translator was run with **Claude Opus 4.7** via the Claude Agent SDK (see `logs/manifest.json` for the exact hash and timestamps).

```bash
# from repo root
python -m code.translate.run --input 1_translate/input/original.jsonl \
                             --output 1_translate/output/translated.jsonl
python -m code.translate.apply_overrides   # applies manual_overrides.jsonl on top
```

Validation utilities (counterparty-presence and spot-check UIs, κ computation) are in [`../code/translate_validation/`](../code/translate_validation/).

## Verification

The 28-of-30 agreement reported in Appendix C corresponds to Cohen's κ = 0.87 (95 % Wald CI [0.69, 1.05]; see `4_analyze/output/translator_kappa.csv`) between the blind manual labeler and the translator on the counterparty-presence axis. The two disagreements are documented in Appendix C of the thesis.
