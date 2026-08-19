#!/usr/bin/env python3
"""Batterie de validation Qwen3.8-27B AWQ-INT4 + MTP-3 + fp8 KV (stack stock v0.27.1).

Adaptee de stock_tq_phase2/validate.py. Differences:
  - MODEL = qwen3.8-27b
  - t_mtp_acceptance : le piege #3 du quant de reference — une head MTP dont les
    poids n'ont pas charge produit 0% d'acceptance et est PLUS LENTE que sans
    MTP (~33 vs 58 t/s). On lit les compteurs spec-decode de /metrics.
  - t_canary : generations a prompts fixes + detection de boucles degeneres
    (le mode de defaillance TQ x spec-dec est SILENCIEUX et passe tous les
    health checks). Obligatoire pour TOUTE config speculative, y compris fp8.
  - t_single_stream : debit mono-flux pour l'A/B meme-soiree vs le MoE 3.6.

Usage:
    VLLM_API_KEY_MEDIUM=... python validate38.py [--port 5002] [--quick]
"""
import argparse
import base64
import json
import os
import re
import struct
import sys
import threading
import time
import urllib.error
import urllib.request
import zlib

PORT = 5002
MODEL = "qwen3.8-27b"
KEY = os.environ.get("VLLM_API_KEY_MEDIUM", "")
RESULTS = []


# ---------------------------------------------------------------- helpers
class ApiError(Exception):
    """HTTPError avec le CORPS de la reponse (lecon 2026-08-11: sans le corps,
    un 500 ModuleNotFoundError est indiscernable d'un crash moteur)."""


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


def get_metrics():
    req = urllib.request.Request(f"http://localhost:{PORT}/metrics")
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode()


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
    """PNG 64x64 en 4 quadrants (rouge/vert/bleu/blanc), sans dependance."""
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


def fourgram_repeat_ratio(text):
    """Ratio de 4-grammes repetes. ~1.0 = boucle degeneree (le bug TQ x spec-dec
    silencieux). Sain en francais/anglais: typiquement < 0.15 sur 200 tokens."""
    toks = text.split()
    if len(toks) < 8:
        return 0.0
    grams = [" ".join(toks[i:i + 4]) for i in range(len(toks) - 3)]
    return 1.0 - len(set(grams)) / len(grams)


# ---------------------------------------------------------------- tests
def t_smoke():
    b, dt = post({"model": MODEL, "max_tokens": 24, "temperature": 0,
                  "messages": [{"role": "user", "content": "Dis simplement: OK"}],
                  "chat_template_kwargs": {"enable_thinking": False}}, 120)
    txt = b["choices"][0]["message"].get("content") or ""
    return record("smoke", bool(txt.strip()), f"{dt:.2f}s -> {txt.strip()[:40]!r}")


def t_mtp_acceptance():
    """Le piege #3: head MTP non chargee = 0% acceptance = PLUS LENT que sans MTP.
    Compteurs lus APRES les premieres generations (appeler apres smoke+canary)."""
    try:
        m = get_metrics()
        acc = re.search(r'vllm:spec_decode_num_accepted_tokens_total\{[^}]*\}\s+([0-9.e+]+)', m)
        dft = re.search(r'vllm:spec_decode_num_draft(?:ed)?_tokens_total\{[^}]*\}\s+([0-9.e+]+)', m)
        if not acc or not dft:
            return record("mtp-acceptance", False,
                          "compteurs spec-decode ABSENTS de /metrics — le drafter "
                          "n'est pas actif (speculative-config ignoree ?)")
        a, d = float(acc.group(1)), float(dft.group(1))
        if d < 50:
            return record("mtp-acceptance", False,
                          f"pas assez de drafts pour juger ({d:.0f}) — relancer apres le bench")
        rate = a / d
        return record("mtp-acceptance", rate > 0.4,
                      f"acceptance {rate:.2f} ({a:.0f}/{d:.0f}) — reference AWQ ~0.60-0.70, "
                      f"official FP8/NVFP4 0.75-0.90; <0.4 = head cassee (trap #3)")
    except Exception as e:
        return record("mtp-acceptance", False, f"{type(e).__name__}: {str(e)[:120]}")


def t_canary():
    """Generations a prompts fixes: reponses saines, pas de boucle degeneree.
    Le mode de defaillance TQ x spec-dec (vllm#40831/#40880, fixes Genesis-only)
    est SILENCIEUX et passe tous les health checks — c'est CE test qui l'attrape."""
    prompts = [
        ("fr-explique", "Explique en deux phrases ce qu'est un cache KV."),
        ("en-sun", "Write exactly one sentence about the sun."),
        ("math", "Quel est le resultat de 12*11 ? Reponds par le nombre seul."),
    ]
    worst = 0.0
    for tag, p in prompts:
        b, dt = post({"model": MODEL, "max_tokens": 300, "temperature": 0.7,
                      "messages": [{"role": "user", "content": p}],
                      "chat_template_kwargs": {"enable_thinking": False}}, 240)
        m = b["choices"][0]["message"]
        txt = (m.get("content") or "") + " " + (m.get("reasoning") or "")
        ratio = fourgram_repeat_ratio(txt)
        worst = max(worst, ratio)
        sane = len(txt.strip()) > 30 and ratio < 0.5
        if tag == "math":
            sane = sane and "132" in txt
        if not sane:
            return record("canary", False,
                          f"[{tag}] degenere? ratio4g={ratio:.2f} -> {txt.strip()[:120]!r}")
    return record("canary", True, f"3 prompts sains (max ratio4g={worst:.2f}, seuil 0.5)")


def t_prefill(tokens, tag, timeout=900):
    """Prefill long chunke — le chemin continuation-prefill historique."""
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
    # 3.8: thinking hybride + reasoning_effort. Effort LOW pour garder le test court.
    try:
        b, dt = post({"model": MODEL, "max_tokens": 1500, "temperature": 0,
                      "messages": [{"role": "user", "content": "Combien font 17*23 ? Raisonne."}],
                      "chat_template_kwargs": {"enable_thinking": True,
                                               "reasoning_effort": "low"}}, 300)
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
    return record("preserve_thinking", "7" in (txt + reasoning),
                  f"{dt:.1f}s, reasoning={len(reasoning)} car -> {txt.strip()[:50]!r}")


def t_single_stream(rounds=3, max_tokens=300):
    """Debit mono-flux — la metrique que MTP est cense ameliorer (ref 2x3090:
    57.9 t/s sans MTP, 84 t/s avec, sur le quant W4A16 de Todd; nos 4090 > 3090)."""
    rates = []
    for r in range(rounds):
        b, dt = post({"model": MODEL, "max_tokens": max_tokens, "temperature": 0.7,
                      "messages": [{"role": "user", "content":
                                    f"Describe in detail how PagedAttention works (pass {r})."}],
                      "chat_template_kwargs": {"enable_thinking": False}}, 300)
        rates.append(b["usage"]["completion_tokens"] / dt)
    best = max(rates)
    return record("single-stream", best > 40,
                  f"{'/'.join(f'{r:.0f}' for r in rates)} t/s (mieux: {best:.0f}) — "
                  f"ref 2x3090+MTP: 84; MoE 3.6 prod: 120-124")


def t_concurrent(n=16, max_tokens=200):
    """Debit agregat. A/B meme-soiree OBLIGATOIRE: le MoE 3.6 a fait 956 tok/s
    (08-14) sur cette meme batterie — mais les chiffres d'un autre jour ne
    comptent pas (lecon 08-11: la machine varie de ~45%)."""
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

    print(f"=== validation Qwen3.8-27B AWQ+MTP-3 + fp8 — stock v0.27.1 ({time.strftime('%H:%M:%SZ', time.gmtime())}) ===")
    print("\n-- fonctionnel --")
    t_smoke()
    t_canary()
    t_vision()
    t_tools()
    t_thinking()
    t_preserve_thinking()
    t_mtp_acceptance()   # apres les premieres generations ci-dessus

    print("\n-- prefill long --")
    t_prefill(30000, "30k")
    t_survival()
    t_prefill(95000, "95k", timeout=1200)
    t_survival()
    if not a.quick:
        t_prefill(235000, "235k", timeout=2400)
        t_survival()

    print("\n-- debit --")
    t_single_stream()
    t_concurrent(16)
    if not a.quick:
        t_concurrent(16)  # 2e passe, moteur chaud
        t_mtp_acceptance()  # relecture a chaud, compteurs substantiels

    print("\n=== RESUME ===")
    bad = [r for r in RESULTS if not r[1]]
    for n, ok, d in RESULTS:
        print(f"  {'PASS' if ok else 'FAIL'}  {n:<22} {d}")
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} PASS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
