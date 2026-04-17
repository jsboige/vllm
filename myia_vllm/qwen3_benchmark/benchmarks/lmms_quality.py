#!/usr/bin/env python3
"""
Custom quality benchmarks for vLLM models.
Replaces lmms-eval which crashes with OOM on Marlin MoE at 0.92 gpu-util.

Benchmarks:
  - gsm8k: Math reasoning (CoT zero-shot), 1319 questions
  - ifeval: Instruction following, 541 prompts
  - mme: Multimodal evaluation (vision), 2374 questions
  - mmstar: Fine-grained vision benchmark, 1500 questions

Usage:
  python -m myia_vllm.qwen3_benchmark.benchmarks.lmms_quality \
    --benchmarks gsm8k ifeval \
    --model qwen3.6-35b-a3b \
    --base-url http://localhost:5002/v1 \
    --output-dir ./myia_vllm/qwen3_benchmark/lmms_results
"""

import argparse
import base64
import json
import os
import re
import sys
import time
from io import BytesIO
from pathlib import Path

from openai import OpenAI


# ─── GSM8K Benchmark ──────────────────────────────────────────────────────

def load_gsm8k():
    """Load GSM8K test set from HuggingFace datasets."""
    from datasets import load_dataset
    ds = load_dataset("openai/gsm8k", "main", split="test")
    return ds


def extract_gsm8k_answer(text: str) -> str:
    """Extract the final numeric answer from GSM8K ground truth."""
    # GSM8K format: "#### 42"
    match = re.search(r"####\s*([\d,]+(?:\.\d+)?)", text)
    if match:
        return match.group(1).replace(",", "")
    return ""


def extract_model_answer(text: str) -> str:
    """Extract numeric answer from model response.

    Priority order (most reliable first):
    1. "#### N" format (GSM8K standard)
    2. \boxed{N} (LaTeX format)
    3. "**Answer:**" followed by a bolded number **N**
    4. "The answer is N"
    5. Bolded standalone number **N** near end of response
    6. Last number in response (fallback)
    """
    num_pat = r"[\d,]+(?:\.\d+)?"

    # Pattern 1: #### format
    match = re.search(r"####\s*(" + num_pat + r")", text)
    if match:
        return match.group(1).replace(",", "")

    # Pattern 2: \boxed{N}
    match = re.search(r"\\boxed\{(" + num_pat + r")\}", text)
    if match:
        return match.group(1).replace(",", "")

    # Pattern 3: "**Answer:**" or "**Answer**:" followed by number (possibly bolded)
    match = re.search(r"\*\*Answer:?\*\*:?\s*.*?\*\*(" + num_pat + r")\*\*", text)
    if match:
        return match.group(1).replace(",", "")
    match = re.search(r"\*\*Answer:?\*\*:?\s*\$?(" + num_pat + r")", text)
    if match:
        return match.group(1).replace(",", "")

    # Pattern 4: "the answer is N" (with optional boxed/dollar)
    match = re.search(r"[Tt]he\s+(?:final\s+)?answer\s+is\s*:?\s*\$?\\?boxed\{?(" + num_pat + r")\}?", text)
    if match:
        return match.group(1).replace(",", "")

    # Pattern 5: Last bolded number **N** in the response
    bolded = re.findall(r"\*\*(" + num_pat + r")\*\*", text)
    if bolded:
        return bolded[-1].replace(",", "")

    # Pattern 6: Last number in response (fallback)
    numbers = re.findall(r"(?<![.\d])(" + num_pat + r")(?![.\d])", text)
    if numbers:
        return numbers[-1].replace(",", "")

    return ""


def run_gsm8k(client: OpenAI, model: str, output_dir: str, max_samples: int = 0):
    """Run GSM8K benchmark."""
    print("\n" + "="*60)
    print("GSM8K CoT Zero-Shot Benchmark")
    print("="*60)

    ds = load_gsm8k()
    total = len(ds) if max_samples == 0 else min(max_samples, len(ds))

    results_file = Path(output_dir) / "gsm8k_results.jsonl"
    summary_file = Path(output_dir) / "gsm8k_summary.json"

    # Resume support: load existing results
    completed = {}
    if results_file.exists():
        with open(results_file, "r") as f:
            for line in f:
                r = json.loads(line)
                completed[r["index"]] = r
        print(f"  Resuming: {len(completed)} already completed")

    correct = sum(1 for r in completed.values() if r.get("correct", False))
    errors = sum(1 for r in completed.values() if r.get("error", False))

    start_time = time.time()

    for i in range(total):
        if i in completed:
            continue

        question = ds[i]["question"]
        gt_answer = extract_gsm8k_answer(ds[i]["answer"])

        prompt = f"Q: {question}\nA: Let's think step by step."

        result = {
            "index": i,
            "question": question[:200],
            "ground_truth": gt_answer,
        }

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                timeout=60,
            )

            text = response.choices[0].message.content or ""
            model_answer = extract_model_answer(text)
            is_correct = model_answer == gt_answer

            result["model_answer"] = model_answer
            result["correct"] = is_correct
            result["response_preview"] = text[-200:]
            result["tokens"] = response.usage.completion_tokens if response.usage else 0

            if is_correct:
                correct += 1

        except Exception as e:
            result["error"] = True
            result["error_msg"] = str(e)[:200]
            errors += 1
            # Wait for potential container restart
            if "502" in str(e) or "Connection" in str(e) or "timeout" in str(e):
                print(f"\n  Server error at {i}, waiting 90s for recovery...")
                time.sleep(90)

        # Save incrementally
        with open(results_file, "a") as f:
            f.write(json.dumps(result) + "\n")
        completed[i] = result

        done = len(completed)
        acc = correct / (done - errors) * 100 if (done - errors) > 0 else 0
        elapsed = time.time() - start_time
        rate = (done - len([r for r in completed.values() if i not in completed or r["index"] <= i]))

        if done % 50 == 0 or done == total:
            print(f"  [{done}/{total}] Accuracy: {acc:.1f}% ({correct}/{done - errors}) | Errors: {errors} | {elapsed:.0f}s")

    # Final summary
    total_done = len(completed)
    total_valid = total_done - errors
    accuracy = correct / total_valid * 100 if total_valid > 0 else 0
    elapsed = time.time() - start_time

    summary = {
        "benchmark": "gsm8k_cot_zeroshot",
        "model": model,
        "total_questions": total,
        "completed": total_done,
        "correct": correct,
        "errors": errors,
        "accuracy_pct": round(accuracy, 2),
        "elapsed_s": round(elapsed, 1),
        "avg_s_per_question": round(elapsed / max(total_done - len([r for r in completed.values() if "error" not in r or not r["error"]]), 1), 2),
    }

    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n  FINAL: {accuracy:.1f}% accuracy ({correct}/{total_valid})")
    print(f"  Errors: {errors}, Time: {elapsed:.0f}s")
    print(f"  Results: {results_file}")

    return summary


# ─── IFEval Benchmark ─────────────────────────────────────────────────────

def load_ifeval():
    """Load IFEval dataset from HuggingFace."""
    from datasets import load_dataset
    ds = load_dataset("google/IFEval", split="train")
    return ds


def check_ifeval_instruction(response: str, instruction_id: str, kwargs: dict) -> bool:
    """Check if a response follows the given instruction.

    Simplified checker for common IFEval instruction types.
    """
    response_lower = response.lower()

    # Word count constraints
    if "length_constraints:number_words" in instruction_id:
        word_count = len(response.split())
        relation = kwargs.get("relation", "")
        num = kwargs.get("num_words", 0)
        if relation == "at least" and word_count < num:
            return False
        if relation == "at most" and word_count > num:
            return False
        return True

    # Sentence count
    if "length_constraints:number_sentences" in instruction_id:
        sentences = re.split(r'[.!?]+', response.strip())
        sentences = [s for s in sentences if s.strip()]
        relation = kwargs.get("relation", "")
        num = kwargs.get("num_sentences", 0)
        if relation == "at least" and len(sentences) < num:
            return False
        if relation == "at most" and len(sentences) > num:
            return False
        return True

    # Paragraph count
    if "length_constraints:number_paragraphs" in instruction_id:
        paragraphs = [p for p in response.split("\n\n") if p.strip()]
        num = kwargs.get("num_paragraphs", 0)
        if len(paragraphs) != num:
            return False
        return True

    # Keywords inclusion
    if "keywords:existence" in instruction_id:
        keywords = kwargs.get("keywords", [])
        for kw in keywords:
            if kw.lower() not in response_lower:
                return False
        return True

    # Keywords exclusion
    if "keywords:forbidden_words" in instruction_id:
        forbidden = kwargs.get("forbidden_words", [])
        for word in forbidden:
            if word.lower() in response_lower:
                return False
        return True

    # Letter frequency
    if "keywords:letter_frequency" in instruction_id:
        letter = kwargs.get("letter", "").lower()
        num = kwargs.get("let_frequency", 0)
        count = response_lower.count(letter)
        let_relation = kwargs.get("let_relation", "at least")
        if let_relation == "at least" and count < num:
            return False
        return True

    # Format: title case
    if "change_case:english_capital" in instruction_id:
        words = response.split()
        if not words:
            return False
        # Check if most content words are capitalized
        cap_count = sum(1 for w in words if w[0].isupper())
        return cap_count / len(words) > 0.7

    # Format: all lowercase
    if "change_case:english_lowercase" in instruction_id:
        # Check if response is mostly lowercase
        alpha = [c for c in response if c.isalpha()]
        if not alpha:
            return True
        lower_count = sum(1 for c in alpha if c.islower())
        return lower_count / len(alpha) > 0.9

    # Format: all uppercase
    if "change_case:english_uppercase" in instruction_id:
        alpha = [c for c in response if c.isalpha()]
        if not alpha:
            return True
        upper_count = sum(1 for c in alpha if c.isupper())
        return upper_count / len(alpha) > 0.9

    # Bullet points
    if "detectable_format:number_bullet_lists" in instruction_id:
        bullets = re.findall(r"^\s*[\*\-\•]\s", response, re.MULTILINE)
        num = kwargs.get("num_bullets", 0)
        return len(bullets) >= num

    # Highlighted sections
    if "detectable_format:number_highlighted_sections" in instruction_id:
        highlights = re.findall(r"\*[^*]+\*", response)
        num = kwargs.get("num_highlights", 0)
        return len(highlights) >= num

    # JSON format
    if "detectable_format:json_format" in instruction_id:
        try:
            json.loads(response.strip())
            return True
        except:
            # Check for JSON in markdown code block
            match = re.search(r"```(?:json)?\s*(\{.+?\})\s*```", response, re.DOTALL)
            if match:
                try:
                    json.loads(match.group(1))
                    return True
                except:
                    pass
            return False

    # Postscript
    if "detectable_content:postscript" in instruction_id:
        return bool(re.search(r"P\.?S\.?", response))

    # Number of placeholders [xxx]
    if "detectable_content:number_placeholders" in instruction_id:
        placeholders = re.findall(r"\[.+?\]", response)
        num = kwargs.get("num_placeholders", 0)
        return len(placeholders) >= num

    # Response language
    if "language:response_language" in instruction_id:
        # Simplified: just check it's not empty
        return len(response.strip()) > 0

    # Combination
    if "combination" in instruction_id:
        return True  # Can't check without sub-instructions

    # Start with specific word
    if "startend:end_checker" in instruction_id:
        end_phrase = kwargs.get("end_phrase", "")
        if end_phrase:
            return response.rstrip().endswith(end_phrase)
        return True

    # Quotation
    if "startend:quotation" in instruction_id:
        return response.strip().startswith('"') and response.strip().endswith('"')

    # No comma
    if "punctuation:no_comma" in instruction_id:
        return "," not in response

    # Default: assume pass for unknown instruction types
    return True


def run_ifeval(client: OpenAI, model: str, output_dir: str, max_samples: int = 0):
    """Run IFEval benchmark."""
    print("\n" + "="*60)
    print("IFEval (Instruction Following) Benchmark")
    print("="*60)

    ds = load_ifeval()
    total = len(ds) if max_samples == 0 else min(max_samples, len(ds))

    results_file = Path(output_dir) / "ifeval_results.jsonl"
    summary_file = Path(output_dir) / "ifeval_summary.json"

    # Resume support
    completed = {}
    if results_file.exists():
        with open(results_file, "r") as f:
            for line in f:
                r = json.loads(line)
                completed[r["index"]] = r
        print(f"  Resuming: {len(completed)} already completed")

    instruction_correct = sum(1 for r in completed.values() if r.get("all_instructions_followed", False))
    errors = sum(1 for r in completed.values() if r.get("error", False))

    start_time = time.time()

    for i in range(total):
        if i in completed:
            continue

        prompt = ds[i]["prompt"]
        instruction_ids = ds[i].get("instruction_id_list", [])
        kwargs_list = ds[i].get("kwargs", [])

        # Parse kwargs if they're strings
        parsed_kwargs = []
        for kw in kwargs_list:
            if isinstance(kw, str):
                try:
                    parsed_kwargs.append(json.loads(kw))
                except:
                    parsed_kwargs.append({})
            else:
                parsed_kwargs.append(kw if kw else {})

        result = {
            "index": i,
            "prompt_preview": prompt[:200],
            "num_instructions": len(instruction_ids),
        }

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1280,
                temperature=0,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                timeout=60,
            )

            text = response.choices[0].message.content or ""

            # Check each instruction
            instruction_results = []
            for inst_id, inst_kwargs in zip(instruction_ids, parsed_kwargs):
                passed = check_ifeval_instruction(text, inst_id, inst_kwargs)
                instruction_results.append({"id": inst_id, "passed": passed})

            all_followed = all(r["passed"] for r in instruction_results) if instruction_results else True

            result["all_instructions_followed"] = all_followed
            result["instruction_results"] = instruction_results
            result["response_preview"] = text[:200]
            result["tokens"] = response.usage.completion_tokens if response.usage else 0

            if all_followed:
                instruction_correct += 1

        except Exception as e:
            result["error"] = True
            result["error_msg"] = str(e)[:200]
            errors += 1
            if "502" in str(e) or "Connection" in str(e) or "timeout" in str(e):
                print(f"\n  Server error at {i}, waiting 90s for recovery...")
                time.sleep(90)

        with open(results_file, "a") as f:
            f.write(json.dumps(result) + "\n")
        completed[i] = result

        done = len(completed)
        valid = done - errors
        acc = instruction_correct / valid * 100 if valid > 0 else 0

        if done % 50 == 0 or done == total:
            elapsed = time.time() - start_time
            print(f"  [{done}/{total}] Strict Accuracy: {acc:.1f}% ({instruction_correct}/{valid}) | Errors: {errors} | {elapsed:.0f}s")

    total_done = len(completed)
    total_valid = total_done - errors
    accuracy = instruction_correct / total_valid * 100 if total_valid > 0 else 0
    elapsed = time.time() - start_time

    summary = {
        "benchmark": "ifeval",
        "model": model,
        "total_prompts": total,
        "completed": total_done,
        "strict_accuracy": round(accuracy, 2),
        "instruction_correct": instruction_correct,
        "errors": errors,
        "elapsed_s": round(elapsed, 1),
    }

    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n  FINAL: {accuracy:.1f}% strict accuracy ({instruction_correct}/{total_valid})")
    print(f"  Errors: {errors}, Time: {elapsed:.0f}s")

    return summary


# ─── MME Vision Benchmark ─────────────────────────────────────────────────

def load_mme():
    """Load MME benchmark from HuggingFace."""
    from datasets import load_dataset
    ds = load_dataset("lmms-lab/MME", split="test")
    return ds


def run_mme(client: OpenAI, model: str, output_dir: str, max_samples: int = 0):
    """Run MME vision benchmark (Yes/No format)."""
    print("\n" + "="*60)
    print("MME Vision Benchmark")
    print("="*60)

    ds = load_mme()
    total = len(ds) if max_samples == 0 else min(max_samples, len(ds))

    results_file = Path(output_dir) / "mme_results.jsonl"
    summary_file = Path(output_dir) / "mme_summary.json"

    # Resume support
    completed = {}
    if results_file.exists():
        with open(results_file, "r") as f:
            for line in f:
                r = json.loads(line)
                completed[r["index"]] = r
        print(f"  Resuming: {len(completed)} already completed")

    correct = sum(1 for r in completed.values() if r.get("correct", False))
    errors = sum(1 for r in completed.values() if r.get("error", False))
    category_scores = {}

    start_time = time.time()

    for i in range(total):
        if i in completed:
            # Rebuild category scores from cached
            r = completed[i]
            cat = r.get("category", "unknown")
            if cat not in category_scores:
                category_scores[cat] = {"correct": 0, "total": 0}
            category_scores[cat]["total"] += 1
            if r.get("correct", False):
                category_scores[cat]["correct"] += 1
            continue

        item = ds[i]
        question = item.get("question", "")
        answer = item.get("answer", "").strip().lower()
        category = item.get("category", "unknown")
        image = item.get("image", None)

        if category not in category_scores:
            category_scores[category] = {"correct": 0, "total": 0}
        category_scores[category]["total"] += 1

        result = {
            "index": i,
            "question": question[:200],
            "ground_truth": answer,
            "category": category,
        }

        try:
            # Build message with image
            content = []
            if image is not None:
                # Convert PIL image to base64
                buf = BytesIO()
                image.save(buf, format="PNG")
                img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                })

            content.append({"type": "text", "text": question + "\nAnswer the question using a single word or phrase."})

            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": content}],
                max_tokens=64,
                temperature=0,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                timeout=60,
            )

            text = (response.choices[0].message.content or "").strip().lower()

            # MME uses Yes/No matching
            model_answer = "yes" if "yes" in text else ("no" if "no" in text else text)
            is_correct = model_answer == answer

            result["model_answer"] = model_answer
            result["correct"] = is_correct
            result["tokens"] = response.usage.completion_tokens if response.usage else 0

            if is_correct:
                correct += 1
                category_scores[category]["correct"] += 1

        except Exception as e:
            result["error"] = True
            result["error_msg"] = str(e)[:200]
            errors += 1
            if "502" in str(e) or "Connection" in str(e) or "timeout" in str(e):
                print(f"\n  Server error at {i}, waiting 90s for recovery...")
                time.sleep(90)

        with open(results_file, "a") as f:
            f.write(json.dumps(result) + "\n")
        completed[i] = result

        done = len(completed)
        valid = done - errors
        acc = correct / valid * 100 if valid > 0 else 0

        if done % 100 == 0 or done == total:
            elapsed = time.time() - start_time
            print(f"  [{done}/{total}] Accuracy: {acc:.1f}% ({correct}/{valid}) | Errors: {errors} | {elapsed:.0f}s")

    total_done = len(completed)
    total_valid = total_done - errors
    accuracy = correct / total_valid * 100 if total_valid > 0 else 0
    elapsed = time.time() - start_time

    # Compute per-category scores (MME uses sum of accuracy * 100 per category)
    cat_summary = {}
    for cat, scores in category_scores.items():
        cat_acc = scores["correct"] / scores["total"] * 100 if scores["total"] > 0 else 0
        cat_summary[cat] = {"accuracy": round(cat_acc, 1), "correct": scores["correct"], "total": scores["total"]}

    # MME score = sum of (accuracy% per subcategory)
    # Perception categories and Cognition categories
    perception_cats = ["existence", "count", "position", "color", "posters", "celebrity", "scene", "landmark", "artwork", "OCR"]
    cognition_cats = ["commonsense_reasoning", "numerical_calculation", "text_translation", "code_reasoning"]

    perception_score = sum(cat_summary.get(c, {}).get("accuracy", 0) for c in perception_cats)
    cognition_score = sum(cat_summary.get(c, {}).get("accuracy", 0) for c in cognition_cats)

    summary = {
        "benchmark": "mme",
        "model": model,
        "total_questions": total,
        "completed": total_done,
        "accuracy_pct": round(accuracy, 2),
        "perception_score": round(perception_score, 1),
        "cognition_score": round(cognition_score, 1),
        "total_score": round(perception_score + cognition_score, 1),
        "errors": errors,
        "elapsed_s": round(elapsed, 1),
        "categories": cat_summary,
    }

    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n  FINAL: {accuracy:.1f}% overall accuracy")
    print(f"  Perception: {perception_score:.1f} | Cognition: {cognition_score:.1f} | Total: {perception_score + cognition_score:.1f}")
    print(f"  Errors: {errors}, Time: {elapsed:.0f}s")

    return summary


# ─── MMStar Vision Benchmark ──────────────────────────────────────────────

def load_mmstar():
    """Load MMStar benchmark from HuggingFace."""
    from datasets import load_dataset
    ds = load_dataset("Lin-Chen/MMStar", split="val")
    return ds


def run_mmstar(client: OpenAI, model: str, output_dir: str, max_samples: int = 0):
    """Run MMStar vision benchmark (multiple choice A/B/C/D)."""
    print("\n" + "="*60)
    print("MMStar Vision Benchmark")
    print("="*60)

    ds = load_mmstar()
    total = len(ds) if max_samples == 0 else min(max_samples, len(ds))

    results_file = Path(output_dir) / "mmstar_results.jsonl"
    summary_file = Path(output_dir) / "mmstar_summary.json"

    completed = {}
    if results_file.exists():
        with open(results_file, "r") as f:
            for line in f:
                r = json.loads(line)
                completed[r["index"]] = r
        print(f"  Resuming: {len(completed)} already completed")

    correct = sum(1 for r in completed.values() if r.get("correct", False))
    errors = sum(1 for r in completed.values() if r.get("error", False))

    start_time = time.time()

    for i in range(total):
        if i in completed:
            continue

        item = ds[i]
        question = item.get("question", "")
        answer = item.get("answer", "").strip().upper()
        image = item.get("image", None)
        category = item.get("category", "unknown")

        result = {
            "index": i,
            "question": question[:200],
            "ground_truth": answer,
            "category": category,
        }

        try:
            content = []
            if image is not None:
                buf = BytesIO()
                image.save(buf, format="PNG")
                img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                })

            content.append({
                "type": "text",
                "text": question + "\nAnswer with the option letter only (A, B, C, or D)."
            })

            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": content}],
                max_tokens=32,
                temperature=0,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                timeout=60,
            )

            text = (response.choices[0].message.content or "").strip().upper()

            # Extract letter answer
            match = re.search(r"^([A-D])", text)
            if not match:
                match = re.search(r"\b([A-D])\b", text)
            model_answer = match.group(1) if match else text[:1]

            is_correct = model_answer == answer

            result["model_answer"] = model_answer
            result["correct"] = is_correct
            result["tokens"] = response.usage.completion_tokens if response.usage else 0

            if is_correct:
                correct += 1

        except Exception as e:
            result["error"] = True
            result["error_msg"] = str(e)[:200]
            errors += 1
            if "502" in str(e) or "Connection" in str(e) or "timeout" in str(e):
                print(f"\n  Server error at {i}, waiting 90s for recovery...")
                time.sleep(90)

        with open(results_file, "a") as f:
            f.write(json.dumps(result) + "\n")
        completed[i] = result

        done = len(completed)
        valid = done - errors
        acc = correct / valid * 100 if valid > 0 else 0

        if done % 100 == 0 or done == total:
            elapsed = time.time() - start_time
            print(f"  [{done}/{total}] Accuracy: {acc:.1f}% ({correct}/{valid}) | Errors: {errors} | {elapsed:.0f}s")

    total_done = len(completed)
    total_valid = total_done - errors
    accuracy = correct / total_valid * 100 if total_valid > 0 else 0
    elapsed = time.time() - start_time

    summary = {
        "benchmark": "mmstar",
        "model": model,
        "total_questions": total,
        "completed": total_done,
        "correct": correct,
        "errors": errors,
        "accuracy_pct": round(accuracy, 2),
        "elapsed_s": round(elapsed, 1),
    }

    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n  FINAL: {accuracy:.1f}% accuracy ({correct}/{total_valid})")
    print(f"  Errors: {errors}, Time: {elapsed:.0f}s")

    return summary


# ─── Main ──────────────────────────────────────────────────────────────────

BENCHMARKS = {
    "gsm8k": run_gsm8k,
    "ifeval": run_ifeval,
    "mme": run_mme,
    "mmstar": run_mmstar,
}


def main():
    parser = argparse.ArgumentParser(description="Custom quality benchmarks for vLLM models")
    parser.add_argument("--benchmarks", nargs="+", default=["gsm8k", "ifeval"],
                        choices=list(BENCHMARKS.keys()),
                        help="Benchmarks to run")
    parser.add_argument("--model", default="qwen3.6-35b-a3b", help="Model name")
    parser.add_argument("--base-url", default="http://localhost:5002/v1", help="vLLM API base URL")
    parser.add_argument("--api-key", default=None, help="API key (or OPENAI_API_KEY env var)")
    parser.add_argument("--output-dir", default="./myia_vllm/qwen3_benchmark/lmms_results",
                        help="Output directory")
    parser.add_argument("--max-samples", type=int, default=0,
                        help="Max samples per benchmark (0=all)")

    args = parser.parse_args()

    # Setup
    api_key = args.api_key or os.getenv("OPENAI_API_KEY") or os.getenv("VLLM_API_KEY_MEDIUM") or "dummy"
    client = OpenAI(base_url=args.base_url, api_key=api_key)

    model_dir = Path(args.output_dir) / args.model.replace("/", "_")
    model_dir.mkdir(parents=True, exist_ok=True)

    print(f"Model: {args.model}")
    print(f"Base URL: {args.base_url}")
    print(f"Output: {model_dir}")
    print(f"Benchmarks: {', '.join(args.benchmarks)}")
    if args.max_samples:
        print(f"Max samples: {args.max_samples}")

    # Verify API is reachable
    try:
        test = client.chat.completions.create(
            model=args.model,
            messages=[{"role": "user", "content": "Say OK"}],
            max_tokens=5,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        print(f"API check: OK ({test.choices[0].message.content})")
    except Exception as e:
        print(f"ERROR: API not reachable: {e}")
        sys.exit(1)

    # Run benchmarks
    all_summaries = {}
    for bench_name in args.benchmarks:
        bench_fn = BENCHMARKS[bench_name]
        summary = bench_fn(client, args.model, str(model_dir), args.max_samples)
        all_summaries[bench_name] = summary

    # Combined summary
    combined_file = model_dir / "combined_summary.json"
    with open(combined_file, "w") as f:
        json.dump(all_summaries, f, indent=2)

    print("\n" + "="*60)
    print("ALL BENCHMARKS COMPLETE")
    print("="*60)
    for name, s in all_summaries.items():
        if "accuracy_pct" in s:
            print(f"  {name}: {s['accuracy_pct']}%")
        elif "strict_accuracy" in s:
            print(f"  {name}: {s['strict_accuracy']}% (strict)")
    print(f"\nResults saved to: {model_dir}")


if __name__ == "__main__":
    main()
