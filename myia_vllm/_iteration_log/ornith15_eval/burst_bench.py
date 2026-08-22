#!/usr/bin/env python3
"""Burst-mode comparative bench (Ornith-1.5 eval, 2026-08-22).

Design constraint: real users share the endpoint — every burst is SHORT
(<= ~90 s wall) and bursts are separated by >= --gap seconds of silence so
live traffic flows between them. Each burst prints one RESULT line; per-burst
numbers (not session means) are the comparison unit, bracketed by 3.6 bursts.

Usage:
  python burst_bench.py <tag> [--mode canary|single|n16|think] \
      [--bursts N] [--gap 120] [--model NAME]

Modes:
  canary  behavioral gates (run FIRST after boot, before real conclusions):
          fr-prose quality (4-gram), /no_think honored, enable_thinking:false
          honored, trivial-prompt thinking length (the Ornith-1.0 killer),
          tool-call XML via qwen3_coder.
  single  3 sequential 200-tok no-think gens -> tok/s each (one burst).
  n16     16 concurrent x 150 tok -> aggregate tok/s (one burst, ~3-10 s).
  think   2 x 200-tok thinking gens -> reasoning chars + tok/s (one burst).

Env: VLLM_API_KEY_MEDIUM (read from keyring via .env by the caller).
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import sys
import time
import urllib.request

BASE = "http://localhost:5002"
KEY = os.environ.get("VLLM_API_KEY_MEDIUM", "")


def post(payload, timeout=180):
    req = urllib.request.Request(
        BASE + "/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    return d, time.time() - t0


def gen(model, prompt, max_tokens=200, think=None, no_think=False, temp=0.7, tools=None):
    content = prompt + ("\n/no_think" if no_think else "")
    p = {"model": model, "messages": [{"role": "user", "content": content}],
         "max_tokens": max_tokens, "temperature": temp}
    if think is not None:
        p["chat_template_kwargs"] = {"enable_thinking": think}
    if tools:
        p["tools"] = tools
        p["tool_choice"] = "auto"
    return post(p)


def r4g(text):
    w = re.findall(r"\w+", text.lower())
    if len(w) < 4:
        return 0.0
    g = [" ".join(w[i:i+4]) for i in range(len(w) - 3)]
    return 1.0 - len(set(g)) / len(g) if g else 0.0


def canary(model):
    res = []

    def add(name, ok, detail):
        res.append((name, ok, detail))
        print(f"  canary.{name}: {'OK' if ok else 'FAIL'} ({detail})")

    d, dt = gen(model, "Explique en 5 phrases pourquoi le ciel est bleu.", 400, think=False)
    txt = d["choices"][0]["message"].get("content") or ""
    add("fr-prose", len(txt) > 200 and r4g(txt) < 0.3, f"r4g={r4g(txt):.2f} {len(txt)}ch {dt:.1f}s")

    d, dt = gen(model, "Quelle est la capitale de la France ? Réponds en une phrase.", 300, no_think=True)
    msg = d["choices"][0]["message"]
    txt = msg.get("content") or ""
    reason = msg.get("reasoning") or ""
    add("no_think", len(reason) < 200 and len(txt) > 10, f"reason={len(reason)}ch content={len(txt)}ch")

    d, dt = gen(model, "Quelle est la capitale de la France ? Réponds en une phrase.", 300, think=False)
    msg = d["choices"][0]["message"]
    add("enable_thinking_false", len(msg.get("reasoning") or "") < 200 and len(msg.get("content") or "") > 10,
        f"reason={len(msg.get('reasoning') or '')}ch")

    d, dt = gen(model, "Combien font 2+2 ? Réponds juste le chiffre.", 300, think=True)
    msg = d["choices"][0]["message"]
    rlen = len(msg.get("reasoning") or "")
    add("trivial_think_len", rlen < 3000, f"reasoning={rlen}ch (1.0 killer: 3-5K on trivial)")

    tools = [{"type": "function", "function": {"name": "get_weather",
               "description": "Get weather",
               "parameters": {"type": "object", "properties": {"city": {"type": "string"}},
                              "required": ["city"]}}}]
    d, dt = gen(model, "Quel temps fait-il à Paris ? Utilise l'outil.", 300, think=False, tools=tools)
    tc = d["choices"][0]["message"].get("tool_calls")
    add("tool_call", bool(tc), f"{'tool_calls ok ' + str(dt) + 's' if tc else 'no tool_calls'}")

    n_ok = sum(1 for _, ok, _ in res if ok)
    return n_ok, len(res)


def burst_single(model):
    out = []
    for _ in range(3):
        d, dt = gen(model, "Écris un paragraphe sur les réseaux de neurones.", 200, think=False)
        tok = d["usage"]["completion_tokens"]
        out.append(tok / dt)
    return out


def burst_n16(model):
    t0 = time.time()
    tot = 0
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        futs = [ex.submit(gen, model, f"Écris un court paragraphe sur le sujet {i}.", 150, think=False)
                for i in range(16)]
        for f in futs:
            d, _ = f.result()
            tot += d["usage"]["completion_tokens"]
    return tot / (time.time() - t0)


def burst_think(model):
    out = []
    for _ in range(2):
        d, dt = gen(model, "Résous : un train va à 120 km/h sur 300 km, combien de temps ? Détaille.", 300, think=True)
        msg = d["choices"][0]["message"]
        out.append((len(msg.get("reasoning") or ""), d["usage"]["completion_tokens"] / dt))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--mode", default="canary", choices=["canary", "single", "n16", "think"])
    ap.add_argument("--bursts", type=int, default=3)
    ap.add_argument("--gap", type=int, default=120)
    ap.add_argument("--model", default=os.environ.get("AB_MODEL"))
    args = ap.parse_args()
    model = args.model
    assert model, "--model or AB_MODEL required"
    assert KEY, "VLLM_API_KEY_MEDIUM not set"

    print(f"=== BURST {args.tag} model={model} mode={args.mode} t={time.strftime('%H:%M:%S')} ===")
    for b in range(args.bursts):
        t0 = time.time()
        if args.mode == "canary":
            ok, n = canary(model)
            print(f"RESULT|{args.tag}|canary|burst{b}|{ok}/{n}")
        elif args.mode == "single":
            v = burst_single(model)
            print(f"RESULT|{args.tag}|single|burst{b}|{v[0]:.0f}/{v[1]:.0f}/{v[2]:.0f}")
        elif args.mode == "n16":
            v = burst_n16(model)
            print(f"RESULT|{args.tag}|n16|burst{b}|{v:.0f}")
        elif args.mode == "think":
            v = burst_think(model)
            print(f"RESULT|{args.tag}|think|burst{b}|r{v[0][0]}ch@{v[0][1]:.0f} r{v[1][0]}ch@{v[1][1]:.0f} t/s")
        dt = time.time() - t0
        if b < args.bursts - 1:
            print(f"  (burst {b} took {dt:.0f}s — gap {args.gap}s)", flush=True)
            time.sleep(args.gap)


if __name__ == "__main__":
    main()
