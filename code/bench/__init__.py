"""Run harness for the 2x2 framing factorial applied to DeceptionBench scenarios.

Generation, judging, and per-cell aggregation. Each (scenario, condition,
framing) is one target-model call; each (scenario, framing) is one judge call
batching the six condition responses.

Entrypoint: `python -m bench.run gen|judge|all --model <id> [--limit N]`.
See bench/README.md for layout, framing derivation, and decoding parameters.
"""
