#!/usr/bin/env python3
"""Re-score GSM8K results with improved answer extraction."""

import json
import re
import sys
from pathlib import Path

num_pat = r"[\d,]+(?:\.\d+)?"

def extract_v2(text: str) -> str:
    """Improved answer extraction (v2)."""
    # Pattern 1: #### format
    match = re.search(r"####\s*(" + num_pat + r")", text)
    if match: return match.group(1).replace(",", "")
    # Pattern 2: \boxed{N}
    match = re.search(r"\\boxed\{(" + num_pat + r")\}", text)
    if match: return match.group(1).replace(",", "")
    # Pattern 3: **Answer:** ... **N**
    match = re.search(r"\*\*Answer:?\*\*:?\s*.*?\*\*(" + num_pat + r")\*\*", text)
    if match: return match.group(1).replace(",", "")
    match = re.search(r"\*\*Answer:?\*\*:?\s*\$?(" + num_pat + r")", text)
    if match: return match.group(1).replace(",", "")
    # Pattern 4: the answer is N
    match = re.search(r"[Tt]he\s+(?:final\s+)?answer\s+is\s*:?\s*\$?\\?boxed\{?(" + num_pat + r")\}?", text)
    if match: return match.group(1).replace(",", "")
    # Pattern 5: Last bolded number
    bolded = re.findall(r"\*\*(" + num_pat + r")\*\*", text)
    if bolded: return bolded[-1].replace(",", "")
    # Pattern 6: Last number (fallback)
    numbers = re.findall(r"(?<![.\d])(" + num_pat + r")(?![.\d])", text)
    if numbers: return numbers[-1].replace(",", "")
    return ""


def main():
    results_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("myia_vllm/qwen3_benchmark/lmms_results/qwen3.5-35b-a3b/gsm8k_results.jsonl")

    correct_v1 = 0
    correct_v2 = 0
    total = 0
    errors = 0
    changes = []

    with open(results_file) as f:
        for line in f:
            r = json.loads(line)
            total += 1
            if r.get("error"):
                errors += 1
                continue

            gt = r["ground_truth"]
            v1_correct = r.get("correct", False)
            if v1_correct:
                correct_v1 += 1

            preview = r.get("response_preview", "")
            v2_ans = extract_v2(preview)
            v2_correct = v2_ans == gt
            if v2_correct:
                correct_v2 += 1

            if v2_correct != v1_correct:
                changes.append({
                    "index": r["index"],
                    "gt": gt,
                    "v1": r.get("model_answer", "?"),
                    "v2": v2_ans,
                    "v1_correct": v1_correct,
                    "v2_correct": v2_correct,
                })

    valid = total - errors
    print(f"Total: {total} | Errors: {errors} | Valid: {valid}")
    print(f"v1 accuracy: {correct_v1}/{valid} = {correct_v1/valid*100:.1f}%")
    print(f"v2 accuracy: {correct_v2}/{valid} = {correct_v2/valid*100:.1f}%")
    print(f"\nChanges ({len(changes)}):")
    for c in changes[:20]:
        direction = "+" if c["v2_correct"] else "-"
        print(f"  {direction} #{c['index']}: gt={c['gt']}, v1={c['v1']} ({'OK' if c['v1_correct'] else 'WRONG'}) -> v2={c['v2']} ({'OK' if c['v2_correct'] else 'WRONG'})")


if __name__ == "__main__":
    main()
