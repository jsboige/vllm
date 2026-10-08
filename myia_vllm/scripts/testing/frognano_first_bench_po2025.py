#!/usr/bin/env python3
"""frognano_first_bench_po2025.py — banc de première charge du siège po-2025 (issue #70).

BOURNÉ PAR CONSTRUCTION (~2-3 min GPU) : 1 complétion simple + N=4 + N=8 concurrentes
de 128 tokens. AUCUNE charge soutenue — le gouverneur thermique SYSTEM n'est pas encore
posé (registre Q2) ; le banc échantillonne temp/VRAM via nvidia-smi autour de chaque phase.

Usage (host) :  python frognano_first_bench_po2025.py [--url http://localhost:5003]
Sortie : résumé console + JSON horodaté dans myia_vllm/_logs/.
Clé lue dans myia_vllm/.env (VLLM_API_KEY_MINI) — jamais en argument, jamais affichée.
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ENV_PATH = os.path.join(REPO, "myia_vllm", ".env")
LOG_DIR = os.path.join(REPO, "myia_vllm", "_logs")
MODEL = "frognano-4b"


def load_key() -> str:
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"VLLM_API_KEY_MINI=(\S+)", line.strip())
            if m:
                return m.group(1)
    sys.exit("VLLM_API_KEY_MINI introuvable dans myia_vllm/.env")


def gpu_state() -> dict:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"], text=True, timeout=10).split(",")[0:4]
        return {"temp_c": int(out[0]), "util_pct": int(out[1]),
                "vram_used_mib": int(out[2]), "vram_total_mib": int(out[3])}
    except Exception as e:  # nvidia-smi absent/lent = non bloquant
        return {"error": str(e)}


def post(url: str, key: str, payload: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def wait_health(base: str, key: str, deadline_s: int = 900) -> None:
    t0 = time.time()
    while time.time() - t0 < deadline_s:
        try:
            req = urllib.request.Request(base + "/health")
            with urllib.request.urlopen(req, timeout=5) as r:
                if r.status == 200:
                    print(f"[health] UP en {time.time()-t0:.0f}s d'attente")
                    return
        except Exception:
            pass
        time.sleep(10)
    sys.exit("[health] moteur non sain après {deadline_s}s".format(deadline_s=deadline_s))


def one_completion(base: str, key: str, max_tokens: int = 128) -> dict:
    payload = {"model": MODEL, "max_tokens": max_tokens, "temperature": 0.6,
               "messages": [{"role": "user", "content":
                             "Écris une fonction Python `is_leap(year)` avec docstring, puis 3 assertions."}]}
    t0 = time.time()
    r = post(base + "/v1/chat/completions", key, payload)
    dt = time.time() - t0
    usage = r.get("usage", {})
    ct = usage.get("completion_tokens", 0)
    return {"e2e_s": round(dt, 2), "completion_tokens": ct,
            "tok_s": round(ct / dt, 1) if dt > 0 else 0,
            "finish": r.get("choices", [{}])[0].get("finish_reason"),
            "has_reasoning": bool(r.get("choices", [{}])[0].get("message", {}).get("reasoning"))}


def phase(label: str, base: str, key: str, n: int) -> dict:
    print(f"\n=== {label} (N={n}) — avant: {gpu_state()}")
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=n) as ex:
        results = list(ex.map(lambda _: one_completion(base, key), range(n)))
    dt = time.time() - t0
    tot = sum(r["completion_tokens"] for r in results)
    ok = sum(1 for r in results if r["finish"] == "stop")
    agg = round(tot / dt, 1) if dt > 0 else 0
    print(f"    agrégat {agg} tok/s | {ok}/{n} finish=stop | apres: {gpu_state()}")
    return {"n": n, "wall_s": round(dt, 2), "aggregate_tok_s": agg, "ok_stop": ok,
            "total_tokens": tot, "per_request": results}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:5003")
    args = ap.parse_args()
    key = load_key()
    os.makedirs(LOG_DIR, exist_ok=True)

    print(f"[bench] cible {args.url} — modèle servi attendu '{MODEL}'")
    wait_health(args.url, key)
    idle = gpu_state()

    report = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "url": args.url, "gpu_idle": idle}
    print("\n=== Phase 1 : complétion unique (warm-up)")
    report["single"] = one_completion(args.url, key)
    print(f"    {report['single']}")
    report["n4"] = phase("Phase 2 : concurrence", args.url, key, 4)
    report["n8"] = phase("Phase 3 : concurrence", args.url, key, 8)
    report["gpu_after"] = gpu_state()

    out = os.path.join(LOG_DIR, f"frognano_first_bench_{time.strftime('%Y%m%d_%H%M%S')}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n[bench] rapport: {out}")
    print(f"[bench] idle {idle.get('temp_c')}C -> max constaté dans phases; final {report['gpu_after'].get('temp_c')}C")


if __name__ == "__main__":
    main()
