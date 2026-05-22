# 5. Appendix

Materials that do not fit one of the linear pipeline stages.

## Files

| Path | Description |
| --- | --- |
| [`qwen35_looping/analysis.md`](qwen35_looping/analysis.md) | Case study of the Qwen3.5-9B looping failure mode under deterministic decoding (§5.3 of the thesis). Documents the three-phase reasoning trace, aggregate statistics, and interpretation. |
| [`qwen35_looping/sample_trace.json`](qwen35_looping/sample_trace.json) | Raw 56 597-character reasoning trace from scenario 1 (framing A, L2-self-reward) hitting the 16 384-token completion cap without emitting a final response. Referenced in §5.3 and `analysis.md`. |
