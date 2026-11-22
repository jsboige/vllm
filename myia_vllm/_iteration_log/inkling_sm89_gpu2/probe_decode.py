"""Single-stream decode probe: N sequential greedy chat requests, tok/s from usage (stdlib only).

usage: python -I probe_decode.py <base_url> <model> <out.json> [label] [n=3] [max_tokens=512]
A TP=1 one-card figure: says whether the SM89 kernels run at a sane speed, not what TP=2 would give.
"""
import json
import os
import sys
import time
import urllib.request

PROMPTS = [
    "Explain in plain words how a hash table handles collisions, with one short example.",
    "Write a Python function that merges two sorted lists into one sorted list, then explain it.",
    "Describe the water cycle for a ten-year-old, in about two hundred words.",
]


def post(url, body, timeout=600):
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("PROBE_API_KEY")  # only for the known-positive check on prod; the test server is keyless
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main():
    base, model, out = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
    label = sys.argv[4] if len(sys.argv) > 4 else ""
    n = int(sys.argv[5]) if len(sys.argv) > 5 else 3
    mt = int(sys.argv[6]) if len(sys.argv) > 6 else 512
    runs = []
    for i in range(n):
        t0 = time.time()
        r = post(f"{base}/chat/completions", {"model": model, "temperature": 0, "max_tokens": mt,
                                               "messages": [{"role": "user", "content": PROMPTS[i % len(PROMPTS)]}]})
        dt = time.time() - t0
        u = r.get("usage", {})
        msg = r["choices"][0]["message"]
        text = (msg.get("content") or "") + (msg.get("reasoning") or msg.get("reasoning_content") or "")
        runs.append({"i": i, "completion_tokens": u.get("completion_tokens"), "elapsed_s": round(dt, 2),
                     "tok_s": round((u.get("completion_tokens") or 0) / dt, 1) if dt else None,
                     "finish": r["choices"][0].get("finish_reason"), "head": text[:160]})
    toks = sum(x["completion_tokens"] or 0 for x in runs)
    secs = sum(x["elapsed_s"] for x in runs)
    res = {"label": label, "model": model, "runs": runs, "total_tokens": toks, "total_s": round(secs, 2),
           "tok_s_overall": round(toks / secs, 1) if secs else None}
    json.dump(res, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(json.dumps({k: v for k, v in res.items() if k != "runs"}))


if __name__ == "__main__":
    main()
