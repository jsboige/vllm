#!/usr/bin/env python3
"""Duo bench — one arm per run, paired offline by duo_analyze.py.

Mandate user 28/11 : « s'il est trop faible pour être utile, essayer de caler un
harnais sk-agent avec le modèle de po-2025, peut-être qu'à deux ils seront
meilleurs ». Two models of comparable strength, measured on the same tasks:

  voltron   the seat engine (127.0.0.1:5028, voltron-1.1-mini), 1 call per task
  frog      po-2025's mini tier (frognano-4b) through the fleet hub — the route
            the fleet already uses for the mini tier; never the direct :5003
            endpoint (it would move the hub transport key onto every client)

Each arm runs alone, in its own serving conditions, so nothing is compared
across two different engines in one process. The 2x2 (a_ok, b_ok) and the
cascade rules live in duo_analyze.py — no judgement of a model, only the
mechanical checkers of the bench (quality_bench_po2025 socle, real_task_bench
pack): nobody is believed, not even the pair.

Usage:
  python duo_bench.py --bench socle --arm voltron --out-dir D:/vllm-data/bench/duo_20261128
  python duo_bench.py --bench socle --arm frog --hub-key-file D:/Dev/roo-extensions/.env \
      --out-dir D:/vllm-data/bench/duo_20261128
  python duo_bench.py --bench pack --pack <pack.json> --arm voltron --out-dir ...
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quality_bench_po2025 as socle  # noqa: E402
import real_task_bench as packbench  # noqa: E402

HUB = "http://192.168.0.50:3000"  # chat() appends /v1/chat/completions
PACK_FORMAT = "voltron-real-task-pack"
PACK_VERSION = 1


# ---------------------------------------------------------------- key handling

def read_env_var(path, name):
    """Reads one variable out of a dotenv file. The value is returned, never printed."""
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(r"\s*%s\s*=\s*(\S+)\s*$" % re.escape(name), line)
            if m:
                return m.group(1).strip('"').strip("'")
    raise SystemExit("variable %s introuvable dans %s" % (name, path))


def hub_key(args):
    if os.environ.get("ZAI_API_KEY"):
        return os.environ["ZAI_API_KEY"]
    if args.hub_key_file:
        return read_env_var(args.hub_key_file, args.hub_key_var)
    raise SystemExit("clé client du hub absente : poser ZAI_API_KEY dans l'environnement "
                     "ou passer --hub-key-file/--hub-key-var")


# ---------------------------------------------------------------- transport

def chat(url, model, prompt, max_tokens=400, timeout=300, api_key=None,
         thinking=None):
    payload = {"model": model, "max_tokens": max_tokens, "temperature": 0.0,
               "messages": [{"role": "user", "content": prompt}]}
    if thinking in ("on", "off"):
        payload["chat_template_kwargs"] = {"enable_thinking": thinking == "on"}
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer %s" % api_key
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions",
                                 data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    choice = d["choices"][0]
    msg = choice["message"]
    content = msg.get("content") or ""
    if not content and msg.get("reasoning_content"):
        content = msg["reasoning_content"]
    return content, choice.get("finish_reason"), d.get("usage") or {}


def strip_thinking(text):
    """Keeps the final answer when the server leaves the reasoning trace in content."""
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.lstrip()


# ---------------------------------------------------------------- tasks

def load_tasks(bench, pack_path):
    if bench == "socle":
        return [dict(t, checker=None) for t in socle.build_tasks()]
    with open(pack_path, encoding="utf-8") as f:
        pack = json.load(f)
    if pack.get("format") != PACK_FORMAT or pack.get("version") != PACK_VERSION:
        raise SystemExit("pack %s : format/version inattendu (%r v%r)" % (
            pack_path, pack.get("format"), pack.get("version")))
    tasks = pack["tasks"]
    unknown = sorted({t.get("checker") for t in tasks} - set(packbench.CHECKERS))
    if unknown or len(tasks) != pack.get("n"):
        raise SystemExit("pack %s : %d tâches pour n=%s, checkers inconnus %s" % (
            pack_path, len(tasks), pack.get("n"), unknown))
    return tasks


def gate(task, out):
    if task.get("checker"):
        return packbench.CHECKERS[task["checker"]](out, task["oracle"])
    return socle.score(task["cat"], out, task["oracle"])


# ---------------------------------------------------------------- arms

ARMS = {
    "voltron": dict(url="http://127.0.0.1:5028", model="voltron-1.1-mini",
                    thinking="off", max_tokens=400, needs_key=False),
    "voltron-think": dict(url="http://127.0.0.1:5028", model="voltron-1.1-mini",
                          thinking="on", max_tokens=2048, needs_key=False),
    "frog": dict(url=HUB, model="frognano-4b", thinking="off",
                 max_tokens=400, needs_key=True),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", required=True, choices=("socle", "pack"))
    ap.add_argument("--arm", required=True, choices=sorted(ARMS))
    ap.add_argument("--pack", help="frozen pack, required with --bench pack")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-tokens", type=int, default=0, help="0 = arm default")
    ap.add_argument("--hub-key-file", default=None)
    ap.add_argument("--hub-key-var", default="CLAUDISH_PROXY_KEY")
    args = ap.parse_args()
    if args.bench == "pack" and not args.pack:
        ap.error("--pack requis avec --bench pack")

    arm = dict(ARMS[args.arm])
    if args.max_tokens:
        arm["max_tokens"] = args.max_tokens
    key = hub_key(args) if arm["needs_key"] else None
    tasks = load_tasks(args.bench, args.pack)
    if args.limit:
        tasks = tasks[:args.limit]

    results = []
    t_start = time.time()
    for i, t in enumerate(tasks):
        t0 = time.time()
        out, ok, detail, err = "", False, "appel en échec", None
        finish, usage = None, {}
        try:
            out, finish, usage = chat(arm["url"], arm["model"], t["prompt"],
                                      max_tokens=arm["max_tokens"],
                                      thinking=arm["thinking"], api_key=key)
            if arm["thinking"] == "on":
                out = strip_thinking(out)
            ok, detail = gate(t, out)
        except Exception as exc:  # noqa: BLE001 — the arm must survive one bad task
            err = repr(exc)
            detail = "appel en échec: %s" % repr(exc)
        results.append(dict(i=i, cat=t["cat"], ok=ok, detail=detail, err=err,
                            out=out[:2000], dt=round(time.time() - t0, 2),
                            finish_reason=finish,
                            completion_tokens=usage.get("completion_tokens")))
        print("[%d/%d] %-13s %s %s" % (i + 1, len(tasks), t["cat"],
                                       "OK  " if ok else "FAIL", detail[:100]), flush=True)

    cats = {}
    for r in results:
        c = cats.setdefault(r["cat"], {"n": 0, "ok": 0})
        c["n"] += 1
        c["ok"] += int(r["ok"])
    ok_total = sum(int(r["ok"]) for r in results)
    summary = {
        "label": "duo-%s-%s" % (args.bench, args.arm),
        "bench": args.bench, "pack": args.pack, "arm": args.arm,
        "url": arm["url"], "model": arm["model"],
        "thinking": arm["thinking"], "max_tokens": arm["max_tokens"],
        "at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(time.time() - t_start, 1),
        "n": len(results), "ok": ok_total,
        "acc": round(ok_total / len(results), 4) if results else None,
        "truncated": sum(1 for r in results if r["finish_reason"] == "length"),
        "errors": sum(1 for r in results if r["err"]),
        "by_cat": {k: {"n": v["n"], "ok": v["ok"], "acc": round(v["ok"] / v["n"], 4)}
                   for k, v in sorted(cats.items())},
        "results": results,
    }
    os.makedirs(args.out_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(args.out_dir, "duo_%s_%s_%s.json" % (args.bench, args.arm, stamp))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print("\n== %s : %d/%d = %.3f en %.1f s (coupées=%d, erreurs=%d)" % (
        summary["label"], ok_total, summary["n"], summary["acc"] or 0.0,
        summary["elapsed_s"], summary["truncated"], summary["errors"]))
    for k, v in summary["by_cat"].items():
        print("   %-13s %d/%d = %.3f" % (k, v["ok"], v["n"], v["acc"]))
    print("-> %s" % path)


if __name__ == "__main__":
    main()
