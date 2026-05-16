#!/usr/bin/env python3
"""Analyze prefix stability of captured claudish/Claude Code request payloads.

For each consecutive pair of real requests (filtered: >2KB, skips watchdog
pings), computes how far the rendered prompt prefix stays byte-identical.
A long stable prefix => prefix caching can hit. Early divergence => it can't.

Usage: python analyze_prefix_stability.py <capture_dir>
"""
import json
import sys
from pathlib import Path

CAP = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/claudish_capture")


def render(req: dict) -> str:
    """Flatten messages to the order/text the model actually sees."""
    parts = []
    for m in req.get("messages", []):
        role = m.get("role", "?")
        content = m.get("content", "")
        if isinstance(content, list):
            content = "".join(
                p.get("text", "") for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
        parts.append(f"<{role}>\n{content}")
    # tools are part of the served prompt too
    tools = req.get("tools")
    if tools:
        parts.append("<tools>\n" + json.dumps(tools, sort_keys=True))
    return "\n".join(parts)


def common_prefix_len(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def main():
    files = sorted(
        (f for f in CAP.glob("req_*.json") if f.stat().st_size > 2048),
        key=lambda f: int(f.stem.split("_")[2]),
    )
    print(f"{len(files)} real requests (>2KB)\n")
    reqs = []
    for f in files:
        try:
            reqs.append((f.name, json.loads(f.read_bytes())))
        except Exception as e:
            print(f"  skip {f.name}: {e}")

    print(f"{'pair':>22} {'lenA':>8} {'lenB':>8} {'common':>8} {'%A':>6} "
          f"{'msgsA':>6} {'msgsB':>6}  first-divergence")
    for (na, ra), (nb, rb) in zip(reqs, reqs[1:]):
        ta, tb = render(ra), render(rb)
        cpl = common_prefix_len(ta, tb)
        pct = 100.0 * cpl / max(len(ta), 1)
        ma = len(ra.get("messages", []))
        mb = len(rb.get("messages", []))
        # context around the divergence point
        snippet = ta[max(0, cpl - 40):cpl] + "|>>>|" + tb[cpl:cpl + 40]
        snippet = snippet.replace("\n", "\\n")
        sa = na.split("_")[1]
        sb = nb.split("_")[1]
        print(f"{sa+'->'+sb:>22} {len(ta):>8} {len(tb):>8} {cpl:>8} "
              f"{pct:>5.1f}% {ma:>6} {mb:>6}  {snippet}")


if __name__ == "__main__":
    main()
