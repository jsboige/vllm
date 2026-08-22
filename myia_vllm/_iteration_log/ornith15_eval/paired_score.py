#!/usr/bin/env python3
"""Paired same-index scoring: Ornith-1.5 (first 300) vs Qwen3.6 full-run references."""
import json
import math

REF = "myia_vllm/qwen3_benchmark/lmms_results/qwen3.6-35b-a3b"
NEW = "myia_vllm/qwen3_benchmark/lmms_results/ornith-1.5-35b-a3b/ornith-1.5-35b-a3b"


def load(path, field):
    d = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            v = r.get(field)
            if isinstance(v, str):
                v = v.lower() == "true"
            if r.get("error_msg"):
                continue
            d[int(r["index"])] = bool(v)
    return d


def ci95(p, n):
    if n == 0:
        return 0.0
    return 1.96 * math.sqrt(p * (1 - p) / n)


for bench, field in [("gsm8k", "correct"), ("ifeval", "all_instructions_followed"), ("mmstar", "correct")]:
    try:
        new = load(f"{NEW}/{bench}_results.jsonl", field)
    except FileNotFoundError:
        print(f"{bench}: not yet written, skipping")
        continue
    ref = load(f"{REF}/{bench}_results.jsonl", field)
    common = sorted(set(new) & set(ref))
    n = len(common)
    if n == 0:
        print(f"{bench}: no common indexes")
        continue
    both = sum(1 for i in common if new[i] and ref[i])
    only_new = sum(1 for i in common if new[i] and not ref[i])
    only_ref = sum(1 for i in common if not new[i] and ref[i])
    neither = n - both - only_new - only_ref
    p_new = (both + only_new) / n
    p_ref = (both + only_ref) / n
    # exact McNemar on the discordant pairs
    b, c = only_new, only_ref
    if b + c > 0:
        chi2 = (abs(b - c) - 1) ** 2 / (b + c)
    else:
        chi2 = 0.0
    sig = "SIGNIFICATIVE" if chi2 > 3.84 else "ns"
    print(
        f"{bench:8s} n={n:3d}  Ornith {100*p_new:5.1f}%  vs 3.6 {100*p_ref:5.1f}%  "
        f"Δ={100*(p_new-p_ref):+5.1f} pts  (CI95 ±{100*ci95(p_new,n):.1f})  "
        f"| +Ornith={b} +3.6={c} | McNemar chi2={chi2:.2f} {sig}"
    )
