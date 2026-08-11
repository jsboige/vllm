#!/usr/bin/env python3
"""Batterie de validation phase 2 — Qwen3.6-35B-A3B + TurboQuant k8v4 sur vLLM STOCK.

Rejoue sur le VRAI modele (MoE, TP=2, EP=2, 262K) ce que la phase 1 n'a pu tester
que sur un proxy 9B dense. Chaque test imprime PASS/FAIL + chiffres.

Usage:
    VLLM_API_KEY_MEDIUM=... python validate.py [--port 5002] [--quick]

--quick saute les tests longs (262K, soak concurrent).
"""
import argparse
import base64
import json
import os
import struct
import sys
import threading
import time
import urllib.error
import urllib.request
import zlib

PORT = 5002
MODEL = "qwen3.6-35b-a3b"
KEY = os.environ.get("VLLM_API_KEY_MEDIUM", "")
RESULTS = []


# ---------------------------------------------------------------- helpers
class ApiError(Exception):
    """HTTPError avec le CORPS de la reponse — sans lui, un 500 est indiscernable
    d'un autre (leçon du 2026-08-11 : le ModuleNotFoundError xxhash ressemblait
    au crash TurboQuant que l'on chassait)."""


def post(payload, timeout=600, path="/v1/chat/completions"):
    req = urllib.request.Request(
        f"http://localhost:{PORT}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), time.time() - t0
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise ApiError(f"HTTP {e.code} — {body}") from None


def record(name, ok, detail):
    RESULTS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
    return ok


def filler(approx_tokens, tag):
    """Prompt unique (pas de contamination du prefix cache entre tests)."""
    words = (
        "the quick brown fox jumps over a lazy dog while parsing tensor shapes and "
        "allocating workspace buffers for continuation prefill across attention "
        "layers in a hybrid gated delta network with quantized key value entries "
    ).split()
    out = [f"[UNIQUE-{tag}]"]
    i = 0
    while len(out) < int(approx_tokens * 0.75):
        if i % 17 == 0:
            out.append(f"[seg-{i // 17}]")
        out.append(words[i % len(words)])
        i += 1
    return " ".join(out)


def png_quadrants():
    """PNG 64x64 en 4 quadrants (rouge/vert/bleu/blanc), construit sans dependance."""
    w = h = 64
    rows = b""
    for y in range(h):
        row = b"\x00"
        for x in range(w):
            if y < h // 2:
                row += b"\xff\x00\x00" if x < w // 2 else b"\x00\xff\x00"
            else:
                row += b"\x00\x00\xff" if x < w // 2 else b"\xff\xff\xff"
        rows += row

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(rows))
           + chunk(b"IEND", b""))
    return base64.b64encode(png).decode()


# ---------------------------------------------------------------- tests
def t_smoke():
    b, dt = post({"model": MODEL, "max_tokens": 24, "temperature": 0,
                  "messages": [{"role": "user", "content": "Dis simplement: OK"}],
                  "chat_template_kwargs": {"enable_thinking": False}}, 120)
    txt = b["choices"][0]["message"].get("content") or ""
    return record("smoke", bool(txt.strip()), f"{dt:.2f}s -> {txt.strip()[:40]!r}")


def t_prefill(tokens, tag, timeout=900):
    """LE test : prefill long chunke -> chemin _continuation_prefill (vllm#41726)."""
    try:
        b, dt = post({"model": MODEL, "max_tokens": 16, "temperature": 0,
                      "messages": [{"role": "user", "content":
                                    filler(tokens, tag) + "\n\nEn un mot, quel animal ?"}],
                      "chat_template_kwargs": {"enable_thinking": False}}, timeout)
    except Exception as e:
        return record(f"prefill-{tag}", False, f"{type(e).__name__}: {str(e)[:200]}")
    pt = b["usage"]["prompt_tokens"]
    return record(f"prefill-{tag}", True, f"{pt} tok en {dt:.1f}s -> {pt/dt:.0f} tok/s prefill")


def t_survival():
    """Un wedge/mort du moteur se voit ICI, pas sur la requete longue."""
    try:
        b, dt = post({"model": MODEL, "max_tokens": 16, "temperature": 0,
                      "messages": [{"role": "user", "content": "Dis simplement: VIVANT"}],
                      "chat_template_kwargs": {"enable_thinking": False}}, 120)
    except Exception as e:
        return record("survie", False, f"moteur mort/wedge: {type(e).__name__}")
    return record("survie", True, f"{dt:.2f}s -> {(b['choices'][0]['message'].get('content') or '').strip()[:30]!r}")


def t_vision():
    try:
        b, dt = post({"model": MODEL, "max_tokens": 80, "temperature": 0,
                      "messages": [{"role": "user", "content": [
                          {"type": "text", "text": "Quelles couleurs vois-tu ? Liste-les."},
                          {"type": "image_url", "image_url":
                           {"url": f"data:image/png;base64,{png_quadrants()}"}}]}],
                      "chat_template_kwargs": {"enable_thinking": False}}, 240)
    except Exception as e:
        return record("vision", False, f"{type(e).__name__}: {str(e)[:90]}")
    txt = (b["choices"][0]["message"].get("content") or "").lower()
    hits = sum(c in txt for c in ("roug", "vert", "bleu", "blanc"))
    return record("vision", hits >= 2, f"{dt:.1f}s, {hits}/4 couleurs -> {txt.strip()[:70]!r}")


def t_tools():
    tools = [{"type": "function", "function": {
        "name": "get_weather", "description": "Meteo d'une ville",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string", "description": "nom de la ville"}},
            "required": ["city"]}}}]
    try:
        b, dt = post({"model": MODEL, "max_tokens": 200, "temperature": 0, "tools": tools,
                      "messages": [{"role": "user", "content": "Quel temps fait-il a Lyon ?"}],
                      "chat_template_kwargs": {"enable_thinking": False}}, 180)
    except Exception as e:
        return record("tool-calling", False, f"{type(e).__name__}: {str(e)[:90]}")
    tc = b["choices"][0]["message"].get("tool_calls") or []
    if not tc:
        return record("tool-calling", False, f"{dt:.1f}s, aucun tool_call")
    fn = tc[0]["function"]
    return record("tool-calling", fn["name"] == "get_weather",
                  f"{dt:.1f}s -> {fn['name']}({str(fn.get('arguments'))[:40]})")


def t_thinking():
    # max_tokens genereux : a 300 le raisonnement est tronque AVANT la reponse et
    # le test echoue pour une raison qui n'a rien a voir avec le moteur (08-11).
    try:
        b, dt = post({"model": MODEL, "max_tokens": 1200, "temperature": 0,
                      "messages": [{"role": "user", "content": "Combien font 17*23 ? Raisonne."}],
                      "chat_template_kwargs": {"enable_thinking": True}}, 300)
    except Exception as e:
        return record("thinking", False, f"{type(e).__name__}: {str(e)[:200]}")
    m = b["choices"][0]["message"]
    reasoning = m.get("reasoning") or ""
    content = m.get("content") or ""
    fin = b["choices"][0].get("finish_reason")
    ok = bool(reasoning.strip()) and "391" in (reasoning + content)
    return record("thinking", ok,
                  f"{dt:.1f}s, reasoning={len(reasoning)} car, content={len(content)} car, "
                  f"finish={fin}, 391 {'trouve' if '391' in (reasoning+content) else 'ABSENT'}")


def t_preserve_thinking():
    """Le defaut serveur est preserve_thinking=true : un historique contenant un
    bloc de raisonnement doit etre accepte sans erreur."""
    try:
        b, dt = post({"model": MODEL, "max_tokens": 600, "temperature": 0, "messages": [
            {"role": "user", "content": "Pense a un nombre entre 1 et 10."},
            {"role": "assistant", "content": "J'ai choisi 7.",
             "reasoning": "Je vais prendre 7, un nombre au milieu de la plage."},
            {"role": "user", "content": "Lequel avais-tu choisi ? Reponds par le chiffre seul."}]}, 240)
    except Exception as e:
        return record("preserve_thinking", False, f"{type(e).__name__}: {str(e)[:200]}")
    m = b["choices"][0]["message"]
    txt = m.get("content") or ""
    reasoning = m.get("reasoning") or ""
    # le raisonnement mange le budget avant le contenu si max_tokens est trop bas
    return record("preserve_thinking", "7" in (txt + reasoning),
                  f"{dt:.1f}s, reasoning={len(reasoning)} car -> {txt.strip()[:50]!r}")


def t_concurrent(n=16, max_tokens=200):
    """Debit agregat — la raison d'etre de TurboQuant (baseline Genesis: 829 tok/s a N=16)."""
    out, lock = [], threading.Lock()

    def worker(i):
        try:
            b, dt = post({"model": MODEL, "max_tokens": max_tokens, "temperature": 0.7,
                          "messages": [{"role": "user", "content":
                                        f"Ecris un paragraphe technique detaille (sujet {i}) sur les caches KV quantifies."}],
                          "chat_template_kwargs": {"enable_thinking": False}}, 600)
            with lock:
                out.append(b["usage"]["completion_tokens"])
        except Exception:
            with lock:
                out.append(0)

    th = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    t0 = time.time()
    for t in th:
        t.start()
    for t in th:
        t.join()
    el = time.time() - t0
    tot = sum(out)
    ok = tot > 0 and all(o > 0 for o in out)
    return record(f"concurrent-N{n}", ok,
                  f"{tot} tok en {el:.1f}s -> {tot/el:.0f} tok/s agrege "
                  f"({sum(1 for o in out if o == 0)} echec(s))")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5002)
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    global PORT
    PORT = a.port
    if not KEY:
        print("VLLM_API_KEY_MEDIUM absent de l'environnement")
        return 2

    print(f"=== validation phase 2 — stock v0.27.0 + TurboQuant k8v4 ({time.strftime('%H:%M:%SZ', time.gmtime())}) ===")
    print("\n-- fonctionnel --")
    t_smoke()
    t_vision()
    t_tools()
    t_thinking()
    t_preserve_thinking()

    print("\n-- prefill long (le crash de 2026-05-06) --")
    t_prefill(30000, "30k")
    t_survival()
    t_prefill(95000, "95k", timeout=1200)     # classe du client lourd connu
    t_survival()
    if not a.quick:
        # 250K depassait la fenetre une fois le template applique (400) : le filler
        # sur-estime (les [seg-N] valent plusieurs tokens). 235K laisse la marge.
        t_prefill(235000, "235k", timeout=2400)  # proche de la fenetre 262K
        t_survival()

    print("\n-- debit --")
    t_concurrent(16)
    if not a.quick:
        t_concurrent(16)  # 2e passe, moteur chaud

    print("\n=== RESUME ===")
    bad = [r for r in RESULTS if not r[1]]
    for n, ok, d in RESULTS:
        print(f"  {'PASS' if ok else 'FAIL'}  {n:<22} {d}")
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} PASS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
