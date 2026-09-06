#!/usr/bin/env python3
"""Concurrent GSM8K + IFEval runner for K2-Horizon on the GPU-2 eval server.

Adapted from qwen3_benchmark/benchmarks/lmms_quality.py (same JSONL schema so
paired_k2.py McNemar works against the Qwen3.6 full-run references), with:
  - ThreadPoolExecutor concurrency (--workers, default 8; server max-num-seqs 16)
  - NO chat_template_kwargs (enable_thinking is Qwen-specific; K2-Horizon's
    template does not take it)
  - timeout 300s (single-GPU 36B is slow; lmms_quality's 60s is too tight)
  - reasoning captured in the JSONL (K2 thinks by default — if the answer ends
    up in `reasoning` instead of `content`, extraction must be adapted)

Usage (from d:/vllm):
  python myia_vllm/_iteration_log/k2_horizon_eval/quality_k2.py \
    --benchmarks gsm8k ifeval --max-samples-gsm8k 300 --max-samples-ifeval 200 \
    --output-dir myia_vllm/_iteration_log/k2_horizon_eval/results/k2-horizon-36b
"""
import argparse
import concurrent.futures
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "myia_vllm/qwen3_benchmark/benchmarks")
from lmms_quality import (  # noqa: E402
    check_ifeval_instruction,
    extract_gsm8k_answer,
    extract_model_answer,
    load_gsm8k,
    load_ifeval,
)

from openai import OpenAI  # noqa: E402


def gsm8k_one(client, model, ds, i):
    question = ds[i]["question"]
    gt = extract_gsm8k_answer(ds[i]["answer"])
    result = {"index": i, "question": question[:200], "ground_truth": gt}
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": f"Q: {question}\nA: Let's think step by step."}],
            max_tokens=1280,
            temperature=0,
            timeout=300,
        )
        text = r.choices[0].message.content or ""
        reasoning = getattr(r.choices[0].message, "reasoning", None) or ""
        result["model_answer"] = extract_model_answer(text)
        result["correct"] = result["model_answer"] == gt
        result["response_preview"] = text[:300]
        result["reasoning_preview"] = reasoning[:300]
        result["reasoning_len"] = len(reasoning)
        result["tokens"] = r.usage.completion_tokens if r.usage else 0
    except Exception as e:
        result["error"] = True
        result["error_msg"] = str(e)[:200]
    return result


def ifeval_one(client, model, ds, i):
    prompt = ds[i]["prompt"]
    instruction_ids = ds[i].get("instruction_id_list", [])
    kwargs_list = ds[i].get("kwargs", [])
    parsed = []
    for kw in kwargs_list:
        if isinstance(kw, str):
            try:
                parsed.append(json.loads(kw))
            except Exception:
                parsed.append({})
        else:
            parsed.append(kw if kw else {})
    result = {"index": i, "prompt_preview": prompt[:200], "num_instructions": len(instruction_ids)}
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1280,
            temperature=0,
            timeout=300,
        )
        text = r.choices[0].message.content or ""
        reasoning = getattr(r.choices[0].message, "reasoning", None) or ""
        instr_results = [
            {"id": iid, "passed": check_ifeval_instruction(text, iid, ikw)}
            for iid, ikw in zip(instruction_ids, parsed)
        ]
        result["all_instructions_followed"] = all(x["passed"] for x in instr_results) if instr_results else True
        result["instruction_results"] = instr_results
        result["response_preview"] = text[:300]
        result["reasoning_preview"] = reasoning[:300]
        result["tokens"] = r.usage.completion_tokens if r.usage else 0
    except Exception as e:
        result["error"] = True
        result["error_msg"] = str(e)[:200]
    return result


def run_bench(name, client, model, out_dir, items, worker_fn, workers):
    results_file = Path(out_dir) / f"{name}_results.jsonl"
    completed = {}
    if results_file.exists():
        for line in open(results_file, encoding="utf-8"):
            r = json.loads(line)
            completed[r["index"]] = r
        print(f"  [{name}] resuming: {len(completed)} done")
    todo = [i for i in range(len(items)) if i not in completed]
    ok = sum(1 for r in completed.values() if r.get("correct", r.get("all_instructions_followed", False)))
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(worker_fn, client, model, items, i): i for i in todo}
        for done_n, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            r = fut.result()
            completed[r["index"]] = r
            with open(results_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(r) + "\n")
            if done_n % 25 == 0 or done_n == len(todo):
                field = "correct" if name == "gsm8k" else "all_instructions_followed"
                valid = [x for x in completed.values() if not x.get("error")]
                acc = sum(1 for x in valid if x.get(field)) / max(len(valid), 1) * 100
                print(f"  [{name}] {len(completed)}/{len(items)} acc={acc:.1f}% errors={sum(1 for x in completed.values() if x.get('error'))} {time.time()-t0:.0f}s")
    return results_file


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--benchmarks", nargs="+", default=["gsm8k", "ifeval"])
    p.add_argument("--model", default="k2-horizon-36b")
    p.add_argument("--base-url", default="http://localhost:5022/v1")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--max-samples-gsm8k", type=int, default=300)
    p.add_argument("--max-samples-ifeval", type=int, default=200)
    args = p.parse_args()

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    client = OpenAI(base_url=args.base_url, api_key="dummy", timeout=300)

    if "gsm8k" in args.benchmarks:
        print("== GSM8K ==")
        ds = load_gsm8k()
        items = list(range(min(args.max_samples_gsm8k, len(ds))))
        # run_bench indexes into ds via i; pass the dataset sliced by max index
        run_bench("gsm8k", client, args.model, args.output_dir, ds, gsm8k_one, args.workers)
    if "ifeval" in args.benchmarks:
        print("== IFEval ==")
        ds = load_ifeval()
        run_bench("ifeval", client, args.model, args.output_dir, ds, ifeval_one, args.workers)


if __name__ == "__main__":
    main()
