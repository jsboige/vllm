#!/usr/bin/env python3
"""
Multi-service vLLM monitoring for agent workloads.

Continuously polls /metrics on multiple vLLM endpoints and produces:
- Real-time terminal dashboard (multi-service, color-coded)
- CSV log with rich per-request metrics for later analysis

Designed for monitoring Roo agent workloads on GLM-4.7-Flash (medium)
and Qwen3-VL-8B (mini) simultaneously.

Usage:
    python monitor_agents.py                          # Monitor medium (5002) only
    python monitor_agents.py --services medium mini   # Monitor both
    python monitor_agents.py --log monitoring.csv     # Log to CSV
    python monitor_agents.py --interval 5             # Poll every 5s
    python monitor_agents.py --duration 3600          # Run for 1 hour then stop
    python monitor_agents.py --quiet                  # CSV only, no terminal output
"""

import argparse
import csv
import re
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx

# Service definitions
SERVICES = {
    "medium": {"port": 5002, "model": "glm-4.7-flash", "label": "GLM-4.7"},
    "mini": {"port": 5001, "model": "qwen3-vl-8b-thinking", "label": "Qwen3-VL"},
}

# CSV columns
CSV_COLUMNS = [
    "timestamp", "service", "model",
    # Request state
    "running_reqs", "waiting_reqs", "peak_running",
    # Throughput (delta rates)
    "gen_tps", "prompt_tps",
    # KV cache
    "kv_cache_pct",
    # Per-request latency (delta from histograms)
    "last_ttft_s", "last_e2e_s", "last_itl_ms", "last_tpot_ms",
    # Per-request sizes (delta from histograms)
    "last_prompt_tokens", "last_gen_tokens",
    # Queue & phases (delta from histograms)
    "last_queue_time_s", "last_prefill_time_s", "last_decode_time_s",
    # Prefix cache
    "prefix_cache_hit_pct", "prefix_tokens_cached",
    # Preemptions
    "preemptions_total",
    # Counters
    "total_requests", "total_gen_tokens", "total_prompt_tokens",
    # Process
    "process_rss_mb",
]


def parse_metrics(text: str) -> dict:
    """Parse Prometheus text format into a flat dict."""
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
    """Get first metric matching a partial key pattern."""
    for key, val in metrics.items():
        if pattern in key:
            return val
    return default


def get_histogram(metrics: dict, prefix: str) -> tuple[float, float]:
    """Get (_sum, _count) from a histogram, ignoring _created variants."""
    total = 0.0
    count = 0.0
    for key, val in metrics.items():
        if f"{prefix}_sum" in key and "created" not in key:
            total = val
        if f"{prefix}_count" in key and "created" not in key:
            count = val
    return total, count


@dataclass
class ServiceState:
    """Tracks previous poll state for delta calculations."""
    name: str
    port: int
    model: str
    label: str
    prev_metrics: dict = field(default_factory=dict)
    prev_time: float = 0.0
    # Histogram state for per-request deltas
    prev_ttft: tuple = (0.0, 0.0)
    prev_e2e: tuple = (0.0, 0.0)
    prev_itl: tuple = (0.0, 0.0)
    prev_tpot: tuple = (0.0, 0.0)
    prev_prompt_tok: tuple = (0.0, 0.0)
    prev_gen_tok: tuple = (0.0, 0.0)
    prev_queue: tuple = (0.0, 0.0)
    prev_prefill: tuple = (0.0, 0.0)
    prev_decode: tuple = (0.0, 0.0)
    # Tracking
    peak_running: int = 0
    total_polls: int = 0
    errors: int = 0
    alive: bool = False


def delta_avg(current: tuple, previous: tuple) -> tuple[float | None, float]:
    """Calculate average of new entries in a histogram.
    Returns (avg_value_or_None, new_count)."""
    new_count = current[1] - previous[1]
    if new_count > 0:
        return (current[0] - previous[0]) / new_count, new_count
    return None, 0


class AgentMonitor:
    def __init__(
        self,
        services: list[str],
        host: str,
        interval: float,
        log_file: str | None,
        duration: float | None,
        quiet: bool,
    ):
        self.host = host
        self.interval = interval
        self.log_file = log_file
        self.duration = duration
        self.quiet = quiet
        self.csv_writer = None
        self.csv_fh = None
        self.start_time = None
        self.running = True

        self.states: list[ServiceState] = []
        for name in services:
            svc = SERVICES[name]
            self.states.append(ServiceState(
                name=name, port=svc["port"],
                model=svc["model"], label=svc["label"],
            ))

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        self.running = False

    def start(self):
        self.start_time = time.time()

        # Open CSV
        if self.log_file:
            self.csv_fh = open(self.log_file, "w", newline="", encoding="utf-8")
            self.csv_writer = csv.DictWriter(self.csv_fh, fieldnames=CSV_COLUMNS)
            self.csv_writer.writeheader()
            self.csv_fh.flush()

        # Health check all services
        for state in self.states:
            url = f"http://{self.host}:{state.port}/health"
            try:
                resp = httpx.get(url, timeout=5)
                state.alive = resp.status_code == 200
            except Exception:
                state.alive = False
            status = "OK" if state.alive else "UNREACHABLE"
            if not self.quiet:
                print(f"  [{state.label}] {url} -> {status}")

        alive_count = sum(1 for s in self.states if s.alive)
        if alive_count == 0:
            print("ERROR: No services reachable. Exiting.")
            sys.exit(1)

        if not self.quiet:
            self._print_header()

        # Main loop
        while self.running:
            for state in self.states:
                if state.alive:
                    self._poll(state)
            if self.duration and (time.time() - self.start_time) >= self.duration:
                break
            time.sleep(self.interval)

        self._print_summary()
        if self.csv_fh:
            self.csv_fh.close()

    def _print_header(self):
        svc_names = " + ".join(s.label for s in self.states if s.alive)
        print(f"\nMonitoring: {svc_names}  |  Interval: {self.interval}s")
        print(f"{'=' * 120}")
        hdr = (
            f"{'Time':>8} {'Svc':>5} | "
            f"{'Run':>3} {'Wait':>4} | "
            f"{'KV%':>5} | "
            f"{'Gen t/s':>8} {'Pfill t/s':>10} | "
            f"{'TTFT':>7} {'E2E':>7} {'ITL':>6} | "
            f"{'Cache%':>6} {'Preempt':>7} | "
            f"{'Reqs':>5}"
        )
        print(hdr)
        print(f"{'-' * 120}")

    def _poll(self, state: ServiceState):
        try:
            resp = httpx.get(
                f"http://{self.host}:{state.port}/metrics", timeout=5
            )
            if resp.status_code != 200:
                state.errors += 1
                return
        except Exception:
            state.errors += 1
            return

        now = time.time()
        m = parse_metrics(resp.text)
        state.total_polls += 1

        # --- Gauges ---
        running = get_metric(m, "num_requests_running")
        waiting = get_metric(m, "num_requests_waiting")
        kv_pct = get_metric(m, "kv_cache_usage_perc") * 100
        preemptions = get_metric(m, "num_preemptions_total")
        rss_bytes = get_metric(m, "process_resident_memory_bytes")
        rss_mb = rss_bytes / (1024 * 1024) if rss_bytes else 0

        state.peak_running = max(state.peak_running, int(running))

        # --- Throughput rates (delta / dt) ---
        gen_tps = 0.0
        prompt_tps = 0.0
        if state.prev_metrics and state.prev_time:
            dt = now - state.prev_time
            if dt > 0:
                gen_now = get_metric(m, "generation_tokens_total")
                gen_prev = get_metric(state.prev_metrics, "generation_tokens_total")
                gen_tps = max(0, (gen_now - gen_prev) / dt)

                prompt_now = get_metric(m, "prompt_tokens_total")
                prompt_prev = get_metric(state.prev_metrics, "prompt_tokens_total")
                prompt_tps = max(0, (prompt_now - prompt_prev) / dt)

        # --- Histogram deltas (per-request averages for new requests) ---
        ttft_cur = get_histogram(m, "time_to_first_token_seconds")
        e2e_cur = get_histogram(m, "e2e_request_latency_seconds")
        itl_cur = get_histogram(m, "inter_token_latency_seconds")
        tpot_cur = get_histogram(m, "request_time_per_output_token_seconds")
        prompt_tok_cur = get_histogram(m, "request_prompt_tokens")
        gen_tok_cur = get_histogram(m, "request_generation_tokens")
        queue_cur = get_histogram(m, "request_queue_time_seconds")
        prefill_cur = get_histogram(m, "request_prefill_time_seconds")
        decode_cur = get_histogram(m, "request_decode_time_seconds")

        last_ttft, _ = delta_avg(ttft_cur, state.prev_ttft)
        last_e2e, _ = delta_avg(e2e_cur, state.prev_e2e)
        last_itl, _ = delta_avg(itl_cur, state.prev_itl)
        last_tpot, _ = delta_avg(tpot_cur, state.prev_tpot)
        last_prompt_tok, _ = delta_avg(prompt_tok_cur, state.prev_prompt_tok)
        last_gen_tok, _ = delta_avg(gen_tok_cur, state.prev_gen_tok)
        last_queue, _ = delta_avg(queue_cur, state.prev_queue)
        last_prefill, _ = delta_avg(prefill_cur, state.prev_prefill)
        last_decode, _ = delta_avg(decode_cur, state.prev_decode)

        # Update histogram state
        state.prev_ttft = ttft_cur
        state.prev_e2e = e2e_cur
        state.prev_itl = itl_cur
        state.prev_tpot = tpot_cur
        state.prev_prompt_tok = prompt_tok_cur
        state.prev_gen_tok = gen_tok_cur
        state.prev_queue = queue_cur
        state.prev_prefill = prefill_cur
        state.prev_decode = decode_cur

        # --- Prefix cache ---
        cache_queries = get_metric(m, "prefix_cache_queries_total")
        cache_hits = get_metric(m, "prefix_cache_hits_total")
        cache_pct = (cache_hits / cache_queries * 100) if cache_queries > 0 else 0.0
        tokens_cached = get_metric(m, "prompt_tokens_cached_total")

        # --- Counters ---
        total_reqs = get_metric(
            m, 'request_success_total{engine="0"'
        )
        total_gen = get_metric(m, "generation_tokens_total")
        total_prompt = get_metric(m, "prompt_tokens_total")

        # --- Terminal output ---
        if not self.quiet:
            ts = datetime.now().strftime("%H:%M:%S")
            gen_s = f"{gen_tps:>7.1f}" if gen_tps > 0.5 else "      -"
            pfill_s = f"{prompt_tps:>9.0f}" if prompt_tps > 10 else "        -"
            ttft_s = f"{last_ttft:>6.2f}s" if last_ttft is not None else "     -"
            e2e_s = f"{last_e2e:>6.1f}s" if last_e2e is not None else "     -"
            itl_s = f"{last_itl * 1000:>5.0f}m" if last_itl is not None else "    -"
            preempt_s = f"{preemptions:>5.0f}" if preemptions > 0 else "    -"

            # Activity indicator
            ind = " "
            if running > 0:
                if gen_tps > 40:
                    ind = "*"
                elif gen_tps > 10:
                    ind = "~"
                elif prompt_tps > 100:
                    ind = "P"
                else:
                    ind = "."

            print(
                f"{ts} {state.label:>5} | "
                f"{running:>3.0f} {waiting:>4.0f} | "
                f"{kv_pct:>4.1f}% | "
                f"{gen_s} t/s {pfill_s} t/s | "
                f"{ttft_s} {e2e_s} {itl_s} | "
                f"{cache_pct:>5.1f}% {preempt_s} | "
                f"{total_reqs:>5.0f} {ind}"
            )

        # --- CSV logging ---
        if self.csv_writer:
            row = {
                "timestamp": datetime.now().isoformat(),
                "service": state.name,
                "model": state.model,
                "running_reqs": int(running),
                "waiting_reqs": int(waiting),
                "peak_running": state.peak_running,
                "gen_tps": f"{gen_tps:.1f}",
                "prompt_tps": f"{prompt_tps:.0f}",
                "kv_cache_pct": f"{kv_pct:.1f}",
                "last_ttft_s": f"{last_ttft:.3f}" if last_ttft is not None else "",
                "last_e2e_s": f"{last_e2e:.3f}" if last_e2e is not None else "",
                "last_itl_ms": f"{last_itl * 1000:.1f}" if last_itl is not None else "",
                "last_tpot_ms": f"{last_tpot * 1000:.1f}" if last_tpot is not None else "",
                "last_prompt_tokens": f"{last_prompt_tok:.0f}" if last_prompt_tok is not None else "",
                "last_gen_tokens": f"{last_gen_tok:.0f}" if last_gen_tok is not None else "",
                "last_queue_time_s": f"{last_queue:.3f}" if last_queue is not None else "",
                "last_prefill_time_s": f"{last_prefill:.3f}" if last_prefill is not None else "",
                "last_decode_time_s": f"{last_decode:.3f}" if last_decode is not None else "",
                "prefix_cache_hit_pct": f"{cache_pct:.1f}",
                "prefix_tokens_cached": f"{tokens_cached:.0f}",
                "preemptions_total": int(preemptions),
                "total_requests": int(total_reqs),
                "total_gen_tokens": int(total_gen),
                "total_prompt_tokens": int(total_prompt),
                "process_rss_mb": f"{rss_mb:.0f}",
            }
            self.csv_writer.writerow(row)
            self.csv_fh.flush()

        state.prev_metrics = m
        state.prev_time = now

    def _print_summary(self):
        elapsed = time.time() - self.start_time
        mins = elapsed / 60
        print(f"\n{'=' * 120}")
        print(f"Session: {mins:.1f} min")
        for s in self.states:
            if not s.alive:
                continue
            print(
                f"  [{s.label}] Polls: {s.total_polls} | "
                f"Peak concurrent: {s.peak_running} | "
                f"Poll errors: {s.errors}"
            )
        if self.log_file:
            print(f"  CSV: {self.log_file}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Multi-service vLLM agent workload monitor"
    )
    parser.add_argument(
        "--services", nargs="+", default=["medium"],
        choices=list(SERVICES.keys()),
        help="Services to monitor (default: medium)",
    )
    parser.add_argument("--host", default="localhost", help="vLLM host")
    parser.add_argument(
        "--interval", type=float, default=3,
        help="Poll interval in seconds (default: 3)",
    )
    parser.add_argument("--log", type=str, help="Log metrics to CSV file")
    parser.add_argument(
        "--duration", type=float,
        help="Stop after N seconds (default: run forever)",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress terminal output, only write CSV",
    )
    args = parser.parse_args()

    if args.quiet and not args.log:
        print("ERROR: --quiet requires --log")
        sys.exit(1)

    monitor = AgentMonitor(
        services=args.services,
        host=args.host,
        interval=args.interval,
        log_file=args.log,
        duration=args.duration,
        quiet=args.quiet,
    )
    monitor.start()


if __name__ == "__main__":
    main()
