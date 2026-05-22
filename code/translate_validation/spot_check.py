"""Local web UI for manually spot-checking translated scenarios.

Each translated scenario is shown with the original text and all six
translated variants. The labeler rates `good` or `bad` (with optional
notes). Labels stream to `1_translate/validation/spot_check_labels.jsonl`.

Usage:
    python -m translate_validation.spot_check  # http://localhost:8001

The random order seed is written as the first line of the output file,
so labeling order is reproducible. Already-labeled scenario ids are
skipped on restart.
"""

from __future__ import annotations

import json
import random
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# code/translate_validation/spot_check.py  →  parent.parent.parent = repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TRANSLATED_PATH = REPO_ROOT / "1_translate" / "output" / "translated.jsonl"
LABELS_PATH = REPO_ROOT / "1_translate" / "validation" / "spot_check_labels.jsonl"
PORT = 8001


def load_scenarios() -> list[dict]:
    rows = [json.loads(line) for line in open(TRANSLATED_PATH)]
    return [r for r in rows if "conditions" in r]


def already_rated() -> set[int]:
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
<html><head><meta charset="utf-8"><title>Translation spot-check</title>
<style>
body { font-family: system-ui, sans-serif; max-width: 1000px; margin: 2em auto; padding: 0 1em; color: #222; }
header { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid #ccc; padding-bottom: 0.5em; margin-bottom: 1em; }
.progress { color: #666; font-size: 0.9em; }
.meta { color: #666; font-size: 0.9em; margin-bottom: 0.5em; }
.variant { border: 1px solid #ddd; border-radius: 4px; padding: 0.6em 1em; margin-bottom: 0.6em; }
.variant h3 { margin: 0 0 0.3em 0; font-size: 0.95em; color: #444; }
.orig-block { background: #f6f6f2; border-radius: 3px; padding: 0.5em 0.7em; margin-bottom: 0.5em; font-size: 0.85em; white-space: pre-wrap; color: #444; }
.orig-block .label { font-weight: 600; color: #777; font-size: 0.8em; display: block; margin-bottom: 0.2em; }
.field { margin: 0.3em 0; font-size: 0.9em; }
.field .k { display: inline-block; min-width: 7em; color: #777; font-weight: 600; }
.field .v { white-space: pre-wrap; }
.controls { position: sticky; bottom: 0; background: white; border-top: 1px solid #ccc; padding: 1em 0; display: flex; gap: 0.5em; align-items: center; }
button { font-size: 1em; padding: 0.5em 1.2em; border: 1px solid #888; background: #f4f4f4; border-radius: 4px; cursor: pointer; }
button.good { background: #d6f3d6; }
button.bad { background: #f3d6d6; }
button:hover { background: #eaeaea; }
input[type=text] { flex: 1; padding: 0.5em; font-size: 1em; border: 1px solid #bbb; border-radius: 4px; }
.done { font-size: 1.2em; text-align: center; padding: 2em; color: #444; }
kbd { font-family: monospace; background: #eee; border: 1px solid #aaa; border-radius: 3px; padding: 0.05em 0.35em; font-size: 0.85em; }
</style></head><body>
<header><h1>Translation spot-check</h1><div class="progress" id="progress"></div></header>
<div id="content"></div>
<div class="controls">
  <input id="notes" type="text" placeholder="optional notes" />
  <button class="good" onclick="rate('good')">Good <kbd>g</kbd></button>
  <button class="bad" onclick="rate('bad')">Bad <kbd>b</kbd></button>
  <button onclick="rate('skip')">Skip <kbd>s</kbd></button>
</div>
<script>
let current = null;
async function load() {
  const r = await fetch('/next');
  const d = await r.json();
  if (d.done) { document.getElementById('content').innerHTML = '<div class="done">All done. ' + d.total + ' rated.</div>'; document.getElementById('progress').innerText = d.rated + '/' + d.total; document.querySelector('.controls').style.display = 'none'; return; }
  current = d;
  document.getElementById('progress').innerText = d.rated + '/' + d.total;
  let h = `<div class="meta">id=${d.id} · ${d.topic} · ${d.dimension}</div>`;
  for (const [k, v] of Object.entries(d.conditions)) {
    h += `<div class="variant"><h3>${k}</h3>`;
    h += `<div class="orig-block"><span class="label">ORIGINAL</span>${escape(v.original)}</div>`;
    h += `<div class="field"><span class="k">system:</span><span class="v">${escape(v.system_prompt)}</span></div>`;
    h += `<div class="field"><span class="k">user:</span><span class="v">${escape(v.user_message)}</span></div>`;
    h += `<div class="field"><span class="k">split_token:</span><span class="v">${escape(v.split_token)}</span></div>`;
    h += '</div>';
  }
  document.getElementById('content').innerHTML = h;
  document.getElementById('notes').value = '';
  document.getElementById('notes').focus();
}
function escape(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;'); }
async function rate(rating) {
  const notes = document.getElementById('notes').value;
  await fetch('/rate', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ id: current.id, rating, notes }) });
  load();
}
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') return;
  if (e.key === 'g') rate('good');
  if (e.key === 'b') rate('bad');
  if (e.key === 's') rate('skip');
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
            rated = already_rated()
            for s in SCENARIOS:
                if s["id"] in rated:
                    continue
                payload = {
                    "id": s["id"],
                    "topic": s.get("topic"),
                    "dimension": s.get("dimension"),
                    "conditions": {
                        k: {
                            "original": v.get("original", ""),
                            "system_prompt": v["system_prompt"],
                            "user_message": v["user_message"],
                            "split_token": v["split_token"],
                        }
                        for k, v in s["conditions"].items()
                    },
                    "rated": len(rated),
                    "total": len(SCENARIOS),
                    "done": False,
                }
                return self._json(payload)
            return self._json(
                {"done": True, "rated": len(rated), "total": len(SCENARIOS)}
            )
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path != "/rate":
            return self._json({"error": "not found"}, 404)
        length = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(length))
        rec = {
            "id": data["id"],
            "rating": data["rating"],
            "notes": data.get("notes", ""),
            "ts": time.time(),
        }
        with open(LABELS_PATH, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._json({"ok": True})


if __name__ == "__main__":
    print(f"loaded {len(SCENARIOS)} translated scenarios")
    print(f"already rated: {len(already_rated())}")
    print(f"seed: {SEED}")
    print(f"labels → {LABELS_PATH}")
    print(f"listening on http://localhost:{PORT}")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
