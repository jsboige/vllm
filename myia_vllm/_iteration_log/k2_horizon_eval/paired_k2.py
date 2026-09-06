#!/usr/bin/env python3
"""Paired same-index McNemar: K2-Horizon W4A16 vs Qwen3.6 full-run references.

Usage (from d:/vllm):
  python myia_vllm/_iteration_log/k2_horizon_eval/paired_k2.py \
    --new myia_vllm/_iteration_log/k2_horizon_eval/results/k2-horizon-36b
"""
import argparse
import json
import math

REF = "myia_vllm/qwen3_benchmark/lmms_results/qwen3.6-35b-a3b"


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
    p.add_argument("--label", default="K2")
    args = p.parse_args()

    for bench, field in [("gsm8k", "correct"), ("ifeval", "all_instructions_followed")]:
        try:
            new = load(f"{args.new}/{bench}_results.jsonl", field)
        except FileNotFoundError:
            print(f"{bench}: not run, skipping")
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
