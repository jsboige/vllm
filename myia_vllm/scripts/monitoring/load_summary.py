#!/usr/bin/env python3
"""Quick load summary from /logs/error_sources.jsonl — last 24h histogram + UA breakdown."""
import json, time, collections, datetime, sys

PATH = "/logs/error_sources.jsonl"
buckets = collections.Counter()
ua = collections.Counter()
status_c = collections.Counter()
model_c = collections.Counter()
total = 0
now = time.time()
since = now - 86400
total_bytes = 0

with open(PATH) as f:
    for l in f:
        try:
            d = json.loads(l)
        except Exception:
            continue
        if d.get("ts", 0) < since:
            continue
        total += 1
        h = datetime.datetime.utcfromtimestamp(d["ts"]).strftime("%m-%d %H")
        buckets[h] += 1
        ua[(d.get("user_agent") or "?")[:30]] += 1
        status_c[d.get("status")] += 1
        model_c[d.get("model") or "?"] += 1
        total_bytes += int(d.get("body_bytes") or 0)

print(f"Last 24h: {total} requests, {total_bytes/1024/1024:.1f} MB body total")
print("Per hour (UTC):")
for h, c in sorted(buckets.items())[-24:]:
    bar = "#" * min(c // 5, 60)
    print(f"  {h}h  {c:5d}  {bar}")
print("Status:", dict(status_c))
print("Models:", dict(model_c))
print("Top UA:")
for u, c in ua.most_common(8):
    print(f"  {c:5d}  {u}")
