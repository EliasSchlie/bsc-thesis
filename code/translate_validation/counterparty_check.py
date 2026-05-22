"""Local web UI for blind counterparty-presence labeling.

Shows all six original (pre-translation) variants of a DeceptionBench
scenario and asks the labeler whether the scenario admits a direct
conversational counterparty. Blind: the translator's classification is
NOT shown. Labels stream to `1_translate/validation/counterparty_labels.jsonl`
for downstream Cohen's kappa against the translator's auto decisions.

Usage:
    python -m translate_validation.counterparty_check  # http://localhost:8002

Random order seed is written as the first line of the output file, so
labeling order is reproducible. Already-labeled ids are skipped on
restart.
"""

from __future__ import annotations

import json
import random
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# code/translate_validation/counterparty_check.py  →  parent.parent.parent = repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ORIGINAL_PATH = REPO_ROOT / "1_translate" / "input" / "original.jsonl"
LABELS_PATH = REPO_ROOT / "1_translate" / "validation" / "counterparty_labels.jsonl"
PORT = 8002

CONDITION_KEYS = [
    "L1-self",
    "L1-other",
    "L2-self-pressure",
    "L2-self-reward",
    "L2-other-pressure",
    "L2-other-reward",
]


def load_scenarios() -> list[dict]:
    return [json.loads(line) for line in open(ORIGINAL_PATH)]


def already_labeled() -> set[int]:
    if not LABELS_PATH.exists():
        return set()
    done = set()
    with open(LABELS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if "id" in r:
                done.add(r["id"])
    return done


def get_seed() -> int:
    if LABELS_PATH.exists():
        with open(LABELS_PATH) as f:
            first = f.readline().strip()
            if first:
                meta = json.loads(first)
                if "seed" in meta:
                    return meta["seed"]
    seed = int(time.time())
    LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LABELS_PATH, "a") as f:
        f.write(json.dumps({"seed": seed, "ts": time.time()}) + "\n")
    return seed


SCENARIOS = load_scenarios()
SEED = get_seed()
random.Random(SEED).shuffle(SCENARIOS)

HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Counterparty-presence labeling (blind)</title>
<style>
body { font-family: system-ui, sans-serif; max-width: 1000px; margin: 2em auto; padding: 0 1em; color: #222; }
header { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid #ccc; padding-bottom: 0.5em; margin-bottom: 1em; }
.progress { color: #666; font-size: 0.9em; }
.meta { color: #666; font-size: 0.9em; margin-bottom: 0.5em; }
.rubric { background: #f6f0e6; border-left: 3px solid #c8a665; padding: 0.6em 1em; font-size: 0.85em; margin-bottom: 1em; border-radius: 3px; }
.variant { border: 1px solid #ddd; border-radius: 4px; padding: 0.6em 1em; margin-bottom: 0.5em; font-size: 0.9em; }
.variant h3 { margin: 0 0 0.3em 0; font-size: 0.9em; color: #444; }
.variant .text { white-space: pre-wrap; }
.controls { position: sticky; bottom: 0; background: white; border-top: 1px solid #ccc; padding: 1em 0; display: flex; gap: 0.5em; align-items: center; }
button { font-size: 1em; padding: 0.5em 1.2em; border: 1px solid #888; background: #f4f4f4; border-radius: 4px; cursor: pointer; }
button.present { background: #d6f3d6; }
button.absent { background: #f3d6d6; }
button.unsure { background: #f0f0d6; }
button:hover { background: #eaeaea; }
input[type=text] { flex: 1; padding: 0.5em; font-size: 1em; border: 1px solid #bbb; border-radius: 4px; }
.done { font-size: 1.2em; text-align: center; padding: 2em; color: #444; }
kbd { font-family: monospace; background: #eee; border: 1px solid #aaa; border-radius: 3px; padding: 0.05em 0.35em; font-size: 0.85em; }
</style></head><body>
<header><h1>Counterparty-presence labeling</h1><div class="progress" id="progress"></div></header>
<div class="rubric"><strong>Rubric:</strong> A scenario has a <em>direct counterparty</em> when the model, in an interactive framing, would be speaking to a specific identifiable person with a defined role, either the deception target or an operator delegating a task. No counterparty when the expected output is standalone content for a diffuse audience (ads, articles, forms, UI text) or the model initiates outbound with no incoming turn to reply to. Decide per scenario across all six variants: if any variant lacks a meaningful counterparty, mark <em>absent</em>.</div>
<div id="content"></div>
<div class="controls">
  <input id="notes" type="text" placeholder="optional notes" />
  <button class="present" onclick="label('present')">Present <kbd>p</kbd></button>
  <button class="absent" onclick="label('absent')">Absent <kbd>a</kbd></button>
  <button class="unsure" onclick="label('unsure')">Unsure <kbd>u</kbd></button>
</div>
<script>
let current = null;
async function load() {
  const r = await fetch('/next');
  const d = await r.json();
  if (d.done) { document.getElementById('content').innerHTML = '<div class="done">All done. ' + d.labeled + '/' + d.total + ' labeled.</div>'; document.getElementById('progress').innerText = d.labeled + '/' + d.total; document.querySelector('.controls').style.display = 'none'; return; }
  current = d;
  document.getElementById('progress').innerText = d.labeled + '/' + d.total;
  let h = `<div class="meta">id=${d.id} · ${d.topic} · ${d.dimension}</div>`;
  for (const [k, v] of Object.entries(d.variants)) {
    h += `<div class="variant"><h3>${k}</h3><div class="text">${escape(v)}</div></div>`;
  }
  document.getElementById('content').innerHTML = h;
  document.getElementById('notes').value = '';
  document.getElementById('notes').focus();
}
function escape(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;'); }
async function label(label) {
  const notes = document.getElementById('notes').value;
  await fetch('/label', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ id: current.id, label, notes }) });
  load();
}
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') return;
  if (e.key === 'p') label('present');
  if (e.key === 'a') label('absent');
  if (e.key === 'u') label('unsure');
});
load();
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            body = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/next":
            labeled = already_labeled()
            for s in SCENARIOS:
                if s["id"] in labeled:
                    continue
                payload = {
                    "id": s["id"],
                    "topic": s.get("topic"),
                    "dimension": s.get("dimension"),
                    "variants": {k: s[k] for k in CONDITION_KEYS},
                    "labeled": len(labeled),
                    "total": len(SCENARIOS),
                    "done": False,
                }
                return self._json(payload)
            return self._json(
                {"done": True, "labeled": len(labeled), "total": len(SCENARIOS)}
            )
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path != "/label":
            return self._json({"error": "not found"}, 404)
        length = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(length))
        rec = {
            "id": data["id"],
            "label": data["label"],
            "notes": data.get("notes", ""),
            "ts": time.time(),
        }
        with open(LABELS_PATH, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._json({"ok": True})


if __name__ == "__main__":
    print(f"loaded {len(SCENARIOS)} original scenarios")
    print(f"already labeled: {len(already_labeled())}")
    print(f"seed: {SEED}")
    print(f"labels → {LABELS_PATH}")
    print(f"listening on http://localhost:{PORT}")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
