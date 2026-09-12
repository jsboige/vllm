#!/usr/bin/env python3
"""Paired same-index McNemar: Qwen3.8-27B (GPU 2) vs same-window prod Qwen3.6 (:5002).

Both runs come from quality_27b.py (indexes align: 0..N-1 on the same datasets).
Usage (from d:/vllm):
  python myia_vllm/_iteration_log/qwen38_27b_gpu2/paired_27b.py \
    --new myia_vllm/_iteration_log/qwen38_27b_gpu2/results/qwen38-27b \
    --ref myia_vllm/_iteration_log/qwen38_27b_gpu2/results/qwen36-prod-ref
"""
import argparse
import json
import math


def load(path, field):
    d = {}
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        v = r.get(field)
        if isinstance(v, str):
            v = v.lower() == "true"
        if r.get("error_msg") or r.get("error"):
            continue
        d[int(r["index"])] = bool(v)
    return d


def ci95(p, n):
    return 1.96 * math.sqrt(p * (1 - p) / n) if n else 0.0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--new", required=True)
    p.add_argument("--ref", required=True)
    p.add_argument("--label", default="27B")
    args = p.parse_args()

    for bench, field in [("gsm8k", "correct"), ("ifeval", "all_instructions_followed")]:
        try:
            new = load(f"{args.new}/{bench}_results.jsonl", field)
        except FileNotFoundError:
            print(f"{bench}: not run, skipping")
            continue
        try:
            ref = load(f"{args.ref}/{bench}_results.jsonl", field)
        except FileNotFoundError:
            print(f"{bench}: ref not run, skipping")
            continue
        common = sorted(set(new) & set(ref))
        n = len(common)
        if n == 0:
            print(f"{bench}: no common indexes")
            continue
        both = sum(1 for i in common if new[i] and ref[i])
        only_new = sum(1 for i in common if new[i] and not ref[i])
        only_ref = sum(1 for i in common if not new[i] and ref[i])
        p_new = (both + only_new) / n
        p_ref = (both + only_ref) / n
        b, c = only_new, only_ref
        chi2 = (abs(b - c) - 1) ** 2 / (b + c) if b + c > 0 else 0.0
        sig = "SIGNIFICATIVE" if chi2 > 3.84 else "ns"
        print(
            f"{bench:8s} n={n:3d}  {args.label} {100*p_new:5.1f}%  vs 3.6 {100*p_ref:5.1f}%  "
            f"Δ={100*(p_new-p_ref):+5.1f} pts (CI95 ±{100*ci95(p_new,n):.1f})  "
            f"| +{args.label}={b} +3.6={c} | McNemar chi2={chi2:.2f} {sig}"
        )


if __name__ == "__main__":
    main()
