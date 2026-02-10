#!/usr/bin/env python3
"""
Analyze monitoring CSV data from monitor_agents.py.

Produces a summary report with:
- Request rates and activity patterns
- TTFT / E2E latency percentiles (p50, p95, p99)
- Throughput statistics
- KV cache pressure analysis
- Prefix cache effectiveness
- Preemption events
- Busy vs idle time analysis
- Per-service breakdown

Usage:
    python analyze_monitoring.py monitoring.csv
    python analyze_monitoring.py monitoring.csv --service medium
    python analyze_monitoring.py monitoring.csv --last 60    # Last 60 min only
    python analyze_monitoring.py monitoring.csv --output report.md
"""

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


def percentile(values: list[float], p: float) -> float:
    """Calculate the p-th percentile of a list of values."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * (p / 100)
    f = int(k)
    c = f + 1
    if c >= len(sorted_v):
        return sorted_v[-1]
    return sorted_v[f] + (k - f) * (sorted_v[c] - sorted_v[f])


def load_csv(path: str, service_filter: str = None, last_minutes: float = None) -> list[dict]:
    """Load and optionally filter CSV data."""
    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if service_filter and row.get("service") != service_filter:
                continue
            rows.append(row)

    if last_minutes and rows:
        # Parse last timestamp and filter
        try:
            last_ts = datetime.fromisoformat(rows[-1]["timestamp"])
            cutoff = last_ts - timedelta(minutes=last_minutes)
            rows = [r for r in rows if datetime.fromisoformat(r["timestamp"]) >= cutoff]
        except (ValueError, KeyError):
            pass

    return rows


def analyze_service(rows: list[dict], service_name: str) -> dict:
    """Analyze rows for a single service."""
    if not rows:
        return {}

    # Parse timestamps
    timestamps = []
    for r in rows:
        try:
            timestamps.append(datetime.fromisoformat(r["timestamp"]))
        except (ValueError, KeyError):
            timestamps.append(None)

    first_ts = next((t for t in timestamps if t), None)
    last_ts = next((t for t in reversed(timestamps) if t), None)
    duration_min = (last_ts - first_ts).total_seconds() / 60 if first_ts and last_ts else 0

    # Collect numeric values
    def collect(key: str) -> list[float]:
        vals = []
        for r in rows:
            v = r.get(key, "")
            if v and v != "":
                try:
                    vals.append(float(v))
                except ValueError:
                    pass
        return vals

    ttft_vals = collect("last_ttft_s")
    e2e_vals = collect("last_e2e_s")
    itl_vals = collect("last_itl_ms")
    tpot_vals = collect("last_tpot_ms")
    gen_tps_vals = collect("gen_tps")
    prompt_tps_vals = collect("prompt_tps")
    kv_vals = collect("kv_cache_pct")
    running_vals = collect("running_reqs")
    waiting_vals = collect("waiting_reqs")
    prompt_tok_vals = collect("last_prompt_tokens")
    gen_tok_vals = collect("last_gen_tokens")
    queue_vals = collect("last_queue_time_s")
    prefill_vals = collect("last_prefill_time_s")
    decode_vals = collect("last_decode_time_s")

    # Request count
    total_reqs_vals = collect("total_requests")
    total_reqs = int(max(total_reqs_vals)) if total_reqs_vals else 0
    first_reqs = int(total_reqs_vals[0]) if total_reqs_vals else 0
    reqs_during = total_reqs - first_reqs

    # Preemptions
    preempt_vals = collect("preemptions_total")
    preemptions = int(max(preempt_vals)) if preempt_vals else 0

    # Cache
    cache_pct_vals = collect("prefix_cache_hit_pct")

    # Activity analysis
    busy_polls = sum(1 for v in running_vals if v > 0)
    total_polls = len(running_vals)
    busy_pct = (busy_polls / total_polls * 100) if total_polls > 0 else 0

    # Peak concurrency
    peak_running = int(max(running_vals)) if running_vals else 0
    peak_waiting = int(max(waiting_vals)) if waiting_vals else 0

    # KV cache pressure
    kv_above_50 = sum(1 for v in kv_vals if v > 50)
    kv_above_80 = sum(1 for v in kv_vals if v > 80)
    kv_peak = max(kv_vals) if kv_vals else 0

    # Active throughput (only when generating)
    active_gen = [v for v in gen_tps_vals if v > 0.5]

    # Hourly request rate
    reqs_per_hour = (reqs_during / duration_min * 60) if duration_min > 0 else 0

    # Build activity timeline (requests per 5-min window)
    timeline = defaultdict(int)
    for i, r in enumerate(rows):
        if timestamps[i] and running_vals and i < len(running_vals) and running_vals[i] > 0:
            bucket = timestamps[i].strftime("%H:%M")
            # Round down to 5-min
            minute = int(bucket.split(":")[1])
            bucket = f"{bucket.split(':')[0]}:{minute // 5 * 5:02d}"
            timeline[bucket] += 1

    return {
        "service": service_name,
        "model": rows[0].get("model", "?") if rows else "?",
        "duration_min": duration_min,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "total_polls": total_polls,
        "total_requests": total_reqs,
        "requests_during": reqs_during,
        "reqs_per_hour": reqs_per_hour,
        # Latency percentiles
        "ttft_p50": percentile(ttft_vals, 50),
        "ttft_p95": percentile(ttft_vals, 95),
        "ttft_p99": percentile(ttft_vals, 99),
        "ttft_count": len(ttft_vals),
        "e2e_p50": percentile(e2e_vals, 50),
        "e2e_p95": percentile(e2e_vals, 95),
        "e2e_p99": percentile(e2e_vals, 99),
        "e2e_count": len(e2e_vals),
        "itl_p50": percentile(itl_vals, 50),
        "itl_p95": percentile(itl_vals, 95),
        "tpot_p50": percentile(tpot_vals, 50),
        "tpot_p95": percentile(tpot_vals, 95),
        # Throughput
        "gen_tps_avg": sum(active_gen) / len(active_gen) if active_gen else 0,
        "gen_tps_peak": max(active_gen) if active_gen else 0,
        "gen_tps_p50": percentile(active_gen, 50),
        # Prompt size
        "prompt_tok_p50": percentile(prompt_tok_vals, 50),
        "prompt_tok_p95": percentile(prompt_tok_vals, 95),
        "prompt_tok_max": max(prompt_tok_vals) if prompt_tok_vals else 0,
        "gen_tok_p50": percentile(gen_tok_vals, 50),
        "gen_tok_p95": percentile(gen_tok_vals, 95),
        # Queue
        "queue_p50": percentile(queue_vals, 50),
        "queue_p95": percentile(queue_vals, 95),
        "prefill_p50": percentile(prefill_vals, 50),
        "prefill_p95": percentile(prefill_vals, 95),
        "decode_p50": percentile(decode_vals, 50),
        "decode_p95": percentile(decode_vals, 95),
        # Activity
        "busy_pct": busy_pct,
        "peak_running": peak_running,
        "peak_waiting": peak_waiting,
        # KV cache
        "kv_peak": kv_peak,
        "kv_above_50_polls": kv_above_50,
        "kv_above_80_polls": kv_above_80,
        # Prefix cache
        "cache_pct_avg": sum(cache_pct_vals) / len(cache_pct_vals) if cache_pct_vals else 0,
        "cache_pct_last": cache_pct_vals[-1] if cache_pct_vals else 0,
        # Preemptions
        "preemptions": preemptions,
        # Timeline
        "timeline": dict(sorted(timeline.items())),
    }


def format_report(analyses: list[dict]) -> str:
    """Format analysis results into a readable report."""
    lines = []
    lines.append("# vLLM Agent Monitoring Report")
    lines.append("")

    for a in analyses:
        if not a:
            continue

        lines.append(f"## {a['service'].upper()} ({a['model']})")
        lines.append("")
        lines.append(f"**Period**: {a['first_ts']:%Y-%m-%d %H:%M} - {a['last_ts']:%H:%M} ({a['duration_min']:.0f} min)")
        lines.append(f"**Polls**: {a['total_polls']} | **Requests served**: {a['requests_during']}")
        lines.append(f"**Request rate**: {a['reqs_per_hour']:.1f} req/hr")
        lines.append("")

        # Activity
        lines.append("### Activity")
        lines.append(f"- Busy: **{a['busy_pct']:.1f}%** of time")
        lines.append(f"- Peak concurrent: **{a['peak_running']}** running, {a['peak_waiting']} waiting")
        lines.append(f"- Preemptions: {a['preemptions']}")
        lines.append("")

        # Latency
        if a['ttft_count'] > 0:
            lines.append("### Latency (per-request)")
            lines.append("")
            lines.append("| Metric | p50 | p95 | p99 | Samples |")
            lines.append("|--------|-----|-----|-----|---------|")
            lines.append(
                f"| TTFT | {a['ttft_p50']:.2f}s | {a['ttft_p95']:.2f}s | "
                f"{a['ttft_p99']:.2f}s | {a['ttft_count']} |"
            )
            if a['e2e_count'] > 0:
                lines.append(
                    f"| E2E | {a['e2e_p50']:.1f}s | {a['e2e_p95']:.1f}s | "
                    f"{a['e2e_p99']:.1f}s | {a['e2e_count']} |"
                )
            lines.append(
                f"| ITL | {a['itl_p50']:.0f}ms | {a['itl_p95']:.0f}ms | - | - |"
            )
            lines.append(
                f"| TPOT | {a['tpot_p50']:.0f}ms | {a['tpot_p95']:.0f}ms | - | - |"
            )
            lines.append("")

        # Throughput
        if a['gen_tps_avg'] > 0:
            lines.append("### Throughput (when active)")
            lines.append(f"- Decode: **{a['gen_tps_avg']:.1f}** tok/s avg, "
                         f"{a['gen_tps_peak']:.1f} peak, {a['gen_tps_p50']:.1f} p50")
            lines.append("")

        # Request sizes
        if a['prompt_tok_p50'] > 0:
            lines.append("### Request Size Distribution")
            lines.append(f"- Prompt: {a['prompt_tok_p50']:.0f} tok (p50), "
                         f"{a['prompt_tok_p95']:.0f} (p95), "
                         f"{a['prompt_tok_max']:.0f} (max)")
            lines.append(f"- Generation: {a['gen_tok_p50']:.0f} tok (p50), "
                         f"{a['gen_tok_p95']:.0f} (p95)")
            lines.append("")

        # Phases
        if a['prefill_p50'] > 0 or a['decode_p50'] > 0:
            lines.append("### Request Phases")
            lines.append(f"- Queue wait: {a['queue_p50']:.3f}s (p50), {a['queue_p95']:.3f}s (p95)")
            lines.append(f"- Prefill: {a['prefill_p50']:.2f}s (p50), {a['prefill_p95']:.2f}s (p95)")
            lines.append(f"- Decode: {a['decode_p50']:.1f}s (p50), {a['decode_p95']:.1f}s (p95)")
            lines.append("")

        # KV Cache
        lines.append("### KV Cache Pressure")
        lines.append(f"- Peak: **{a['kv_peak']:.1f}%**")
        lines.append(f"- Polls >50%: {a['kv_above_50_polls']} | >80%: {a['kv_above_80_polls']}")
        lines.append("")

        # Prefix Cache
        lines.append("### Prefix Cache")
        lines.append(f"- Hit rate: **{a['cache_pct_avg']:.1f}%** avg, {a['cache_pct_last']:.1f}% latest")
        lines.append("")

        # Activity timeline
        if a['timeline']:
            lines.append("### Activity Timeline (busy polls per 5-min window)")
            for bucket, count in a['timeline'].items():
                bar = "#" * min(count, 60)
                lines.append(f"  {bucket} | {bar} ({count})")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Analyze vLLM monitoring CSV data")
    parser.add_argument("csv_file", help="Path to monitoring CSV file")
    parser.add_argument(
        "--service", type=str,
        help="Filter to a single service (medium, mini)",
    )
    parser.add_argument(
        "--last", type=float,
        help="Analyze only the last N minutes of data",
    )
    parser.add_argument(
        "--output", type=str,
        help="Save report to file (default: print to stdout)",
    )
    args = parser.parse_args()

    if not Path(args.csv_file).exists():
        print(f"File not found: {args.csv_file}")
        sys.exit(1)

    # Load data
    rows = load_csv(args.csv_file, args.service, args.last)
    if not rows:
        print("No data found matching filters.")
        sys.exit(1)

    # Group by service
    by_service = defaultdict(list)
    for r in rows:
        by_service[r.get("service", "unknown")].append(r)

    # Analyze each service
    analyses = []
    for svc_name, svc_rows in sorted(by_service.items()):
        analyses.append(analyze_service(svc_rows, svc_name))

    # Format report
    report = format_report(analyses)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report saved to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
