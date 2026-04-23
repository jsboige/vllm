"""Quick DFlash benchmark — single-user decode tok/s + acceptance rate.

Compares against baseline (Qwen3.6-35B-A3B without spec_decode).
Reads spec_decode metrics from /metrics before/after each request.
"""
import json
import re
import sys
import time
import urllib.request

API_URL = "http://localhost:5002/v1/chat/completions"
METRICS_URL = "http://localhost:5002/metrics"
API_KEY = "7711C3D0426C998B10FBC84811BF2E4D"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}

PROMPTS = [
    {
        "name": "code_short_nothink",
        "system": "You are a senior Python developer.",
        "user": (
            "Write a Python function `merge_intervals(intervals)` that takes a "
            "list of [start, end] intervals and returns the merged "
            "non-overlapping intervals sorted by start. Include type hints, a "
            "one-line docstring, and 3 example test cases as comments. "
            "No explanations outside the code."
        ),
        "max_tokens": 500,
        "thinking": False,
    },
    {
        "name": "reason_medium_think",
        "system": "You are a careful reasoner.",
        "user": (
            "Three friends Alice, Bob, and Charlie share 60 marbles. Alice has "
            "twice as many as Bob, and Charlie has 5 fewer than Alice. How many "
            "marbles does each have? Show your work step by step."
        ),
        "max_tokens": 800,
        "thinking": True,
    },
    {
        "name": "code_long_nothink",
        "system": "You are a senior backend engineer.",
        "user": (
            "Implement a Python class `LRUCache` with `get(key)` and `put(key, "
            "value)` methods, both O(1). Use OrderedDict. Include type hints, a "
            "constructor `__init__(capacity)`, docstrings, and a small unit test "
            "block in `if __name__ == '__main__'`."
        ),
        "max_tokens": 1000,
        "thinking": False,
    },
]

METRIC_KEYS = [
    "vllm:spec_decode_num_drafts_total",
    "vllm:spec_decode_num_draft_tokens_total",
    "vllm:spec_decode_num_accepted_tokens_total",
]


def fetch_metrics() -> dict:
    req = urllib.request.Request(METRICS_URL, headers={"Authorization": HEADERS["Authorization"]})
    with urllib.request.urlopen(req, timeout=10) as r:
        text = r.read().decode("utf-8")
    out = {}
    for key in METRIC_KEYS:
        m = re.search(rf'^{re.escape(key)}\{{[^}}]*\}}\s+([\d.eE+-]+)', text, re.M)
        out[key] = float(m.group(1)) if m else 0.0
    return out


def run_one(prompt: dict) -> dict:
    body = {
        "model": "qwen3.6-35b-a3b",
        "messages": [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": prompt["user"]},
        ],
        "max_tokens": prompt["max_tokens"],
        "temperature": 0.6,
        "chat_template_kwargs": {"enable_thinking": prompt["thinking"]},
    }
    metrics_before = fetch_metrics()
    t0 = time.perf_counter()
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers=HEADERS,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.loads(r.read().decode("utf-8"))
    elapsed = time.perf_counter() - t0
    metrics_after = fetch_metrics()
    delta = {k: metrics_after[k] - metrics_before[k] for k in METRIC_KEYS}

    completion = resp["usage"]["completion_tokens"]
    prompt_tok = resp["usage"]["prompt_tokens"]
    drafts = delta["vllm:spec_decode_num_drafts_total"]
    draft_tokens = delta["vllm:spec_decode_num_draft_tokens_total"]
    accepted = delta["vllm:spec_decode_num_accepted_tokens_total"]
    accept_rate = (accepted / draft_tokens * 100) if draft_tokens else 0.0
    accept_per_step = (accepted / drafts) if drafts else 0.0
    tok_s = completion / elapsed

    return {
        "name": prompt["name"],
        "prompt_tokens": prompt_tok,
        "completion_tokens": completion,
        "wall_s": elapsed,
        "tok_s": tok_s,
        "drafts": int(drafts),
        "draft_tokens": int(draft_tokens),
        "accepted": int(accepted),
        "accept_rate_pct": accept_rate,
        "accept_per_step": accept_per_step,
        "first_chars": resp["choices"][0]["message"]["content"][:200] if resp["choices"][0]["message"]["content"] else "",
        "reasoning_first": (resp["choices"][0]["message"].get("reasoning") or "")[:200],
    }


def main() -> int:
    results = []
    for p in PROMPTS:
        print(f"--- running {p['name']} (max_tok={p['max_tokens']}, thinking={p['thinking']}) ---", flush=True)
        try:
            r = run_one(p)
        except Exception as e:
            print(f"FAILED: {e}", flush=True)
            continue
        results.append(r)
        print(f"  prompt={r['prompt_tokens']}  completion={r['completion_tokens']}  wall={r['wall_s']:.2f}s  tok/s={r['tok_s']:.1f}", flush=True)
        print(f"  drafts={r['drafts']}  draft_tok={r['draft_tokens']}  accepted={r['accepted']}  accept={r['accept_rate_pct']:.1f}%  per_step={r['accept_per_step']:.2f}", flush=True)

    print("\n========== SUMMARY ==========")
    print(f"{'name':28} {'tok/s':>7} {'accept%':>8} {'per_step':>9} {'compl':>6}")
    for r in results:
        print(f"{r['name']:28} {r['tok_s']:>7.1f} {r['accept_rate_pct']:>7.1f}% {r['accept_per_step']:>9.2f} {r['completion_tokens']:>6}")

    out_path = sys.argv[1] if len(sys.argv) > 1 else "myia_vllm/qwen3_benchmark/results/dflash_quick_bench.json"
    try:
        import os
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nSaved: {out_path}")
    except Exception as e:
        print(f"\nNot saved ({e}) — results above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
