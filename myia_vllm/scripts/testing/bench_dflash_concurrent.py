"""DFlash concurrent benchmark — 5 simultaneous users to mimic Roo+OWUI load."""
import concurrent.futures as cf
import json
import re
import time
import urllib.request

API_URL = "http://localhost:5002/v1/chat/completions"
METRICS_URL = "http://localhost:5002/metrics"
API_KEY = "7711C3D0426C998B10FBC84811BF2E4D"
HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}

PROMPT = {
    "system": "You are a senior Python developer.",
    "user": (
        "Implement a Python function `kth_largest(arr, k)` that returns the "
        "k-th largest element of arr in O(n) average time using quickselect. "
        "Include type hints, a docstring, and 4 example test cases as comments."
    ),
    "max_tokens": 400,
}


def fetch_metrics():
    req = urllib.request.Request(METRICS_URL, headers={"Authorization": HEADERS["Authorization"]})
    with urllib.request.urlopen(req, timeout=10) as r:
        text = r.read().decode("utf-8")
    keys = [
        "vllm:spec_decode_num_drafts_total",
        "vllm:spec_decode_num_draft_tokens_total",
        "vllm:spec_decode_num_accepted_tokens_total",
    ]
    out = {}
    for k in keys:
        m = re.search(rf'^{re.escape(k)}\{{[^}}]*\}}\s+([\d.eE+-]+)', text, re.M)
        out[k] = float(m.group(1)) if m else 0.0
    return out


def call_one(idx: int):
    body = {
        "model": "qwen3.6-35b-a3b",
        "messages": [
            {"role": "system", "content": PROMPT["system"]},
            {"role": "user", "content": PROMPT["user"]},
        ],
        "max_tokens": PROMPT["max_tokens"],
        "temperature": 0.6,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    t0 = time.perf_counter()
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode("utf-8"), headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.loads(r.read().decode("utf-8"))
    elapsed = time.perf_counter() - t0
    return {
        "idx": idx,
        "completion_tokens": resp["usage"]["completion_tokens"],
        "wall_s": elapsed,
        "tok_s": resp["usage"]["completion_tokens"] / elapsed,
    }


def main():
    for n_users in (5,):
        m_before = fetch_metrics()
        t0 = time.perf_counter()
        with cf.ThreadPoolExecutor(max_workers=n_users) as ex:
            futs = [ex.submit(call_one, i) for i in range(n_users)]
            results = [f.result() for f in cf.as_completed(futs)]
        wall = time.perf_counter() - t0
        m_after = fetch_metrics()
        delta = {k: m_after[k] - m_before[k] for k in m_before}

        total_tok = sum(r["completion_tokens"] for r in results)
        agg_tps = total_tok / wall
        per_user_tps = [r["tok_s"] for r in results]
        accept = (delta["vllm:spec_decode_num_accepted_tokens_total"] /
                  max(1, delta["vllm:spec_decode_num_draft_tokens_total"]) * 100)

        print(f"=== Concurrent N={n_users} ===")
        for r in sorted(results, key=lambda x: x["idx"]):
            print(f"  user {r['idx']}: {r['completion_tokens']:4d} tok in {r['wall_s']:.2f}s = {r['tok_s']:.1f} tok/s")
        print(f"AGGREGATE:  {total_tok} tok in {wall:.2f}s = {agg_tps:.1f} tok/s aggregate")
        print(f"PER-USER:   min={min(per_user_tps):.1f}  max={max(per_user_tps):.1f}  avg={sum(per_user_tps)/len(per_user_tps):.1f} tok/s")
        print(f"SPEC:       drafts={int(delta['vllm:spec_decode_num_drafts_total'])}  accept={accept:.1f}%")


if __name__ == "__main__":
    main()
