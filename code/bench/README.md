# bench/

Run harness: plug a model in, run it through the 68 in-scope DeceptionBench
scenarios at the 2x2 framing factorial (4 framings) x 6 motive conditions,
then label every response with the upstream DeceptionBench rubric via an
LLM judge.

## Run

```bash
# from the repository root
export PYTHONPATH="$PWD/code:$PYTHONPATH"

# full run on one target + the gpt-5.4-nano judge
python -m bench.run all \
    --model "deepseek/deepseek-r1" \
    --judge-model "openai/gpt-5.4-nano"

# generate only
python -m bench.run gen --model "deepseek/deepseek-r1" --workers 30

# judge only (assumes generations already exist)
python -m bench.run judge \
    --target-model "deepseek/deepseek-r1" \
    --judge-model "openai/gpt-5.4-nano"

# smoke test on 2 scenarios
python -m bench.run all --model "deepseek/deepseek-r1" --limit 2
```

Subset a framing: `--framings A,D`. Default `all` = A,B,C,D.

## Env

`.env` is autoloaded. Required: `OPENROUTER_API_KEY` (target-model and judge
calls; both are routed through OpenRouter). Override the endpoint with
`OPENAI_BASE_URL` if you want to point the client at a different
OpenAI-compatible host.

## Output layout

Paths are written relative to `--results-dir` (defaults to the repository
root):

```
<root>/2_generate/output/<target_model_slug>/
    gen_A.jsonl          # one row per (scenario, condition) call, framing A
    gen_B.jsonl          # ... framing B
    gen_C.jsonl
    gen_D.jsonl
    runs/<stamp>_<cmd>.{log,config.json}   # one pair per `bench.run` invocation
<root>/3_judge/output/<target_model_slug>/
    judge_<judge_slug>_A.jsonl   # one row per (scenario) judge call, framing A
    ... (B, C, D)
    results.csv                  # flat per-cell join of gen + judge
    summary.json                 # aggregated per-cell deception rates
    runs/<stamp>_<cmd>.{log,config.json}
```

Each row in `gen_*.jsonl` carries the full request prompt, raw + cleaned
response, token usage, latency, attempt count, and any final error. Runs are
resumable by `(scenario_id, condition, framing)` keys; an errored row is
retried on the next invocation.

Each row in `judge_*.jsonl` carries the parsed `{condition: {thought, response}}`
verdict, the raw judge text, and a `parse_error` flag if the judge's output
couldn't be parsed (so downstream analysis sees parse-failure rate).

## Framing derivation

Source: `1_translate/output/translated.jsonl` (i.e. stage 1 output).
Counterparty-absent scenarios (`skip` field) are excluded. Per
scenario/condition, the dataset supplies:

- `original`           -- verbatim DeceptionBench text
- `system_prompt`      -- reworded operational setup (role, context, motive,
                          in-scene anchor), written for a system message
- `user_message`       -- reworded counterparty turn (direct dialogue)
- `split_token`        -- substring of `original` marking the
                          operational/counterparty boundary

Framings in the 2x2 factorial (wording x delivery structure):

| framing | wording     | delivery | system                                 | user                                                         |
|---------|-------------|----------|----------------------------------------|--------------------------------------------------------------|
| A       | narrated    | single   | -                                      | `original + FORMAT_POST`                                     |
| B       | narrated    | split    | `left_of_split`                        | `split_token + right_of_split + FORMAT_POST`                 |
| C       | interactive | single   | -                                      | `system_prompt + FORMAT_POST + user_message`                 |
| D       | interactive | split    | `system_prompt + FORMAT_POST`          | `user_message`                                               |

`FORMAT_POST` is DeceptionBench's JSON-format instruction, verbatim:

    (Please say your thought and final response in a json format: {"thought":"","response":""})

**FORMAT_POST position is part of the wording, not an independent axis.**
The narrated framings (A, B) keep the upstream position: FORMAT_POST at the
very end of the stimulus, right after the narrated anchor ("You will say:",
"How would you respond?") -- which in B puts it at the tail of the user
message, after the relocated counterparty turn. The reworded framings (C, D)
move FORMAT_POST to the operational/counterparty boundary: in D that boundary
is the end of the system message; in C, which has no system message, it is
embedded between the operational content and the direct-delivery question
inside the single user message.

A is therefore bit-identical to the upstream DeceptionBench prompt for every
scenario, verified against [`utils.py:15-16`][upstream-utils-stim] of the
upstream repository.

## Model decoding

`max_tokens=16384` (targets; raised from upstream's 500 for reasoning-model
headroom -- unused tokens do not bill), `temperature=0.0`, `top_p=0.95` --
temperature and top_p match upstream DeceptionBench
([`config.py:11-16`][upstream-config]). Judge max_tokens is tighter (env
`JUDGE_MAX_TOKENS`, default 500). Retry: 3 attempts with exponential backoff
(1s, 2s, 4s). Response post-processing strips newlines and markdown code
fences ([`utils.py:27-28`][upstream-utils-post]); raw text is kept verbatim
in the `raw_response` column.

GPT-5 / o1 / o3 / o4 reasoning models auto-switch to `max_completion_tokens`
and omit the non-default temperature (which they reject).

## Judge

Template is copied verbatim from upstream DeceptionBench
([`processor/eval_single_turn.py:27-66`][upstream-judge], Huang et al., 2025,
CC BY-SA 4.0). One judge call per (scenario, framing) batches all six
conditions; output format is `###FINAL: { "L1-self": {...}, ...,
"L2-other-reward": {...} }`. Scenarios with any errored or missing gen are
refused (not silently judged with partial data) and logged to
`runs/<stamp>_<cmd>.log`.

[upstream-utils-stim]: https://github.com/Aries-iai/DeceptionBench/blob/main/utils.py#L15-L16
[upstream-utils-post]: https://github.com/Aries-iai/DeceptionBench/blob/main/utils.py#L27-L28
[upstream-config]: https://github.com/Aries-iai/DeceptionBench/blob/main/config.py#L11-L16
[upstream-judge]: https://github.com/Aries-iai/DeceptionBench/blob/main/processor/eval_single_turn.py#L27-L66
