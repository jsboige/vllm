#!/usr/bin/env python3
"""
Live performance monitor for vLLM endpoints.

Polls /metrics every N seconds and displays a real-time dashboard
in the terminal with key performance indicators.

Shows INDIVIDUAL per-request TTFT (not misleading cumulative average).

Usage:
    python monitor_live.py                    # Monitor GLM (default)
    python monitor_live.py --port 5001        # Monitor mini
    python monitor_live.py --interval 5       # Poll every 5s
    python monitor_live.py --log monitor.csv  # Log to CSV
"""

import argparse
import csv
import re
import sys
import time
from datetime import datetime

import httpx


def parse_metrics(text: str) -> dict:
    """Parse Prometheus metrics into a dict of key values."""
    metrics = {}
    for line in text.split("\n"):
        if line.startswith("#") or not line.strip():
            continue
        match = re.match(r'^([^\s{]+)(?:\{([^}]*)\})?\s+(.+)$', line)
        if match:
            name = match.group(1)
            labels = match.group(2) or ""
            value = match.group(3)
            key = f"{name}{{{labels}}}" if labels else name
            try:
                metrics[key] = float(value)
            except ValueError:
                pass
    return metrics


def get_metric(metrics: dict, pattern: str, default=0.0) -> float:
    """Get a metric value by partial key match."""
    for key, val in metrics.items():
        if pattern in key:
            return val
    return default


def get_histogram_sum_count(metrics: dict, prefix: str) -> tuple:
    """Get raw _sum and _count from a histogram metric."""
    total = 0.0
    count = 0.0
    for key, val in metrics.items():
        if f"{prefix}_sum" in key and "created" not in key:
            total = val
        if f"{prefix}_count" in key and "created" not in key:
            count = val
    return total, count


class LiveMonitor:
    def __init__(self, base_url: str, interval: float, log_file: str = None):
        self.base_url = base_url
        self.interval = interval
        self.log_file = log_file
        self.csv_writer = None
        self.csv_file = None
        self.prev_metrics = None
        self.prev_time = None
        # Track TTFT histogram for per-request calculation
        self.prev_ttft_sum = 0.0
        self.prev_ttft_count = 0.0

    def start(self):
        if self.log_file:
            self.csv_file = open(self.log_file, "w", newline="", encoding="utf-8")
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow([
                "timestamp", "running_reqs", "waiting_reqs", "kv_cache_pct",
                "gen_tps", "prompt_tps", "last_ttft_s",
                "total_requests", "prefix_cache_hit_pct",
            ])

        print(f"Monitoring {self.base_url}/metrics every {self.interval}s")
        hdr = (
            f"{'Time':>8} | {'Run':>3} {'Wait':>4} | {'KV%':>5} | "
            f"{'Gen tok/s':>10} {'Pfill tok/s':>12} | "
            f"{'Last TTFT':>10} | {'Cache%':>6} | {'Reqs':>5}"
        )
        print(f"{'=' * 90}")
        print(hdr)
        print(f"{'-' * 90}")

        try:
            while True:
                self._poll()
                time.sleep(self.interval)
        except KeyboardInterrupt:
            print(f"\n{'=' * 90}")
            print("Monitoring stopped.")
        finally:
            if self.csv_file:
                self.csv_file.close()

    def _poll(self):
        try:
            resp = httpx.get(f"{self.base_url}/metrics", timeout=5)
            if resp.status_code != 200:
                print(f"  HTTP {resp.status_code}")
                return
        except Exception as e:
            print(f"  ERROR: {e}")
            return

        now = time.time()
        metrics = parse_metrics(resp.text)

        running = get_metric(metrics, "num_requests_running")
        waiting = get_metric(metrics, "num_requests_waiting")
        kv_pct = get_metric(metrics, "kv_cache_usage_perc") * 100

        # Calculate delta rates
        gen_tps = 0.0
        prompt_tps = 0.0
        if self.prev_metrics and self.prev_time:
            dt = now - self.prev_time
            if dt > 0:
                gen_delta = get_metric(metrics, "generation_tokens_total") - get_metric(self.prev_metrics, "generation_tokens_total")
                prompt_delta = get_metric(metrics, "prompt_tokens_total") - get_metric(self.prev_metrics, "prompt_tokens_total")
                gen_tps = gen_delta / dt
                prompt_tps = prompt_delta / dt

        # Per-request TTFT (delta from histogram)
        ttft_sum, ttft_count = get_histogram_sum_count(metrics, "time_to_first_token_seconds")
        last_ttft = None
        new_reqs = ttft_count - self.prev_ttft_count
        if new_reqs > 0:
            last_ttft = (ttft_sum - self.prev_ttft_sum) / new_reqs
            self.prev_ttft_sum = ttft_sum
            self.prev_ttft_count = ttft_count

        # Prefix cache hit rate
        queries = get_metric(metrics, "prefix_cache_queries_total")
        hits = get_metric(metrics, "prefix_cache_hits_total")
        cache_pct = (hits / queries * 100) if queries > 0 else 0.0

        total_reqs = get_metric(metrics, 'request_success_total{engine="0",finished_reason="stop"')

        # Format output
        ts = datetime.now().strftime("%H:%M:%S")
        gen_str = f"{gen_tps:>7.1f}" if gen_tps > 0 else "      -"
        pfill_str = f"{prompt_tps:>9.1f}" if prompt_tps > 0 else "        -"
        ttft_str = f"{last_ttft:>8.2f}s" if last_ttft is not None else "        -"

        # Indicators
        if running > 0:
            indicator = "*" if gen_tps > 40 else "~" if gen_tps > 20 else "P" if prompt_tps > 0 else "G"
        else:
            indicator = " "

        print(
            f"{ts} | {running:>3.0f} {waiting:>4.0f} | {kv_pct:>4.1f}% | "
            f"{gen_str} t/s {pfill_str} t/s | "
            f"{ttft_str} | {cache_pct:>5.1f}% | {total_reqs:>5.0f} {indicator}"
        )

        if self.csv_writer:
            self.csv_writer.writerow([
                datetime.now().isoformat(), running, waiting, f"{kv_pct:.1f}",
                f"{gen_tps:.1f}", f"{prompt_tps:.1f}",
                f"{last_ttft:.3f}" if last_ttft is not None else "",
                total_reqs, f"{cache_pct:.1f}",
            ])
            self.csv_file.flush()

        self.prev_metrics = metrics
        self.prev_time = now


def main():
    parser = argparse.ArgumentParser(description="Live vLLM performance monitor")
    parser.add_argument("--port", type=int, default=5002, help="vLLM port (default: 5002)")
    parser.add_argument("--host", type=str, default="localhost", help="vLLM host")
    parser.add_argument("--interval", type=float, default=3, help="Poll interval in seconds")
    parser.add_argument("--log", type=str, help="Log metrics to CSV file")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"

    # Quick health check
    try:
        resp = httpx.get(f"{base_url}/health", timeout=5)
        if resp.status_code != 200:
            print(f"Service unhealthy at {base_url}")
            sys.exit(1)
    except Exception as e:
        print(f"Cannot connect to {base_url}: {e}")
        sys.exit(1)

    monitor = LiveMonitor(base_url, args.interval, args.log)
    monitor.start()


if __name__ == "__main__":
    main()
