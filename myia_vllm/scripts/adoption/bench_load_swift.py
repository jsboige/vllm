#!/usr/bin/env python3
"""Driver de fenetre de charge pour swift-1.5-27b (ai-01), pilote depuis po-2025.

Fenetre GO user + claudish 02/11/2026 (thread Q-73). Protocole :
  paliers N=2 (reference) -> N=4 -> N=6, trafic synthetique PAR-DESSUS le trafic
  reel, prompts au profil swift (40-90 K tokens, prefix partage ~30 K, decodage
  ~1200), arret automatique sur les deux garde-fous claudish :
    (1) p95 e2e > 240 s (roulant, 20 dernieres requetes du driver)
    (2) num_requests_waiting > 0 en continu pendant > 60 s (sonde /metrics 15 s)

La cle ne passe JAMAIS en argument CLI : --key-file ou --key-env.

Sorties : JSONL par requete + resume par palier sur stdout + fichier --out.
"""

import argparse
import json
import os
import random
import sys
import threading
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------- corpus synthetique

_WORDS = (
    "systeme mesure moteur cache memoire requete fichier processus donnee reseau "
    "contexte modele sequence token temperature fichier journal alerte seuil "
    "capacite charge concurrence latence file attente prefill decodage bloc "
    "pression variance profil fenetre garde seuil automne hiver projet equipe "
    "analyse synthese structure document section chapitre reference archive"
).split()


def _block(seed, n_words):
    rng = random.Random(seed)
    return " ".join(rng.choice(_WORDS) for _ in range(n_words))


def build_prompt(target_tokens, shared_block, idx):
    """Prefix partage (realisme prefix-cache) + queue unique numerotee.

    Estimation ~1 token / 1,35 mot francais ; la verite est dans ptok rendu.
    """
    approx_words = int(target_tokens * 1.35)
    shared_words = shared_block.count(" ") + 1
    tail_words = max(200, approx_words - shared_words)
    tail = _block(1000 + idx, tail_words)
    return (
        "Tu es un assistant technique. Voici un long dossier de contexte pour "
        "ta mission d'analyse du systeme.\n\n" + shared_block +
        f"\n\nEXTRAIT NUMERO {idx} (unique a cette requete) :\n" + tail +
        "\n\nTache : resume le dossier ci-dessus en une analyse structuree."
    )


# ---------------------------------------------------------------- une requete

def one_request(sess, base, key, model, prompt, max_tokens, timeout, idx):
    t0 = time.time()
    ttft = None
    usage = {}
    err = None
    try:
        r = sess.post(
            base,
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.7,
                "stream": True,
                "stream_options": {"include_usage": True},
            },
            timeout=timeout,
            stream=True,
        )
        r.raise_for_status()
        for raw in r.iter_lines():
            if not raw:
                continue
            try:
                obj = json.loads(raw.decode("utf-8")[6:] if raw.startswith(b"data: ") else raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if obj.get("usage"):
                usage = obj["usage"]
            if ttft is None:
                for ch in obj.get("choices") or []:
                    if (ch.get("delta") or {}).get("content"):
                        ttft = time.time() - t0
                        break
    except Exception as e:  # noqa: BLE001 - le driver doit survivre a tout
        err = repr(e)[:300]
    return {
        "i": idx, "t0": t0, "e2e": time.time() - t0,
        "ttft": ttft, "ptok": usage.get("prompt_tokens"),
        "ctok": usage.get("completion_tokens"), "err": err,
    }


# ---------------------------------------------------------------- sonde /metrics

def poll_metrics(sess, metrics_url):
    """Gauges/counters moteur : waiting, kv_usage, preemptions (best effort)."""
    out = {"waiting": 0, "kv": None, "preempt": None, "ok": False}
    try:
        r = sess.get(metrics_url, timeout=10)
        if r.status_code != 200:
            return out
        out["ok"] = True
        for line in r.text.splitlines():
            if line.startswith("vllm:num_requests_waiting"):
                out["waiting"] = float(line.rsplit(" ", 1)[1])
            elif line.startswith("vllm:kv_cache_usage_perc") and not line.startswith("#"):
                out["kv"] = float(line.rsplit(" ", 1)[1])
            elif line.startswith("vllm:num_preemptions_total") and out["preempt"] is None:
                out["preempt"] = float(line.rsplit(" ", 1)[1])
    except Exception:  # noqa: BLE001
        pass
    return out


def percentile(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = min(len(s) - 1, max(0, int(round(p / 100.0 * (len(s) - 1)))))
    return s[k]


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base",
                    default="https://api.medium.text-generation-webui.myia.io/v1/chat/completions")
    ap.add_argument("--metrics-url",
                    default="https://api.medium.text-generation-webui.myia.io/metrics")
    ap.add_argument("--model", default="swift-1.5-27b")
    ap.add_argument("--key-file")
    ap.add_argument("--key-env")
    ap.add_argument("--paliers", default="2:5,4:10,6:10",
                    help="N:minutes par palier, separe par virgules")
    ap.add_argument("--prompt-tokens", default="40000,55000,70000,85000")
    ap.add_argument("--shared-prefix-tokens", type=int, default=30000)
    ap.add_argument("--max-tokens", type=int, default=1200)
    ap.add_argument("--p95-abort", type=float, default=240.0)
    ap.add_argument("--wait-abort-s", type=float, default=60.0)
    ap.add_argument("--req-timeout", type=float, default=600.0)
    ap.add_argument("--out", default="bench_load_swift_out.jsonl")
    args = ap.parse_args()

    if args.key_file:
        key = Path(args.key_file).read_text(encoding="utf-8").strip()
    elif args.key_env:
        key = os.environ[args.key_env]
    else:
        sys.exit("cle requise : --key-file ou --key-env (jamais en argument brut)")
    if not key:
        sys.exit("cle vide")

    import hashlib
    print(f"cle chargee, empreinte sha256[:12]={hashlib.sha256(key.encode()).hexdigest()[:12]}")
    print(f"cible: {args.base} | modele: {args.model}")
    print(f"paliers: {args.paliers} | tailles prompt: {args.prompt_tokens} tokens | "
          f"prefix partage {args.shared_prefix_tokens} | max_tokens {args.max_tokens}")
    print(f"gardes: p95 e2e > {args.p95_abort}s (roulant 20) | waiting>0 en continu > {args.wait_abort_s}s\n")

    sizes = [int(x) for x in args.prompt_tokens.split(",")]
    shared_block = _block(42, int(args.shared_prefix_tokens * 1.35))
    sess = requests.Session()
    recs = []
    lock = threading.Lock()
    stop = threading.Event()

    # ---- sonde de garde (thread daemon)
    wait_since = None
    probe = {"ts": [], "waiting": [], "kv": [], "preempt": []}

    def guard():
        nonlocal wait_since
        while not stop.is_set():
            m = poll_metrics(sess, args.metrics_url)
            now = time.time()
            with lock:
                probe["ts"].append(now)
                probe["waiting"].append(m["waiting"])
                probe["kv"].append(m["kv"])
                probe["preempt"].append(m["preempt"])
                recent = [r for r in recs if now - r["t0"] < 900]
                e2es = sorted(r["e2e"] for r in recent if not r["err"])[-20:]
                p95 = percentile(e2es, 95) if e2es else None
            if m["waiting"] > 0:
                if wait_since is None:
                    wait_since = now
                elif now - wait_since > args.wait_abort_s:
                    print(f"[GARDE] ABORT : num_requests_waiting>0 depuis "
                          f"{now - wait_since:.0f}s > {args.wait_abort_s}s")
                    stop.set()
                    return
            else:
                wait_since = None
            if p95 is not None and len(e2es) >= 5 and p95 > args.p95_abort:
                print(f"[GARDE] ABORT : p95 e2e roulant {p95:.0f}s > {args.p95_abort}s")
                stop.set()
                return
            stop.wait(15)

    # ---- preflights non authentifies
    h = sess.get(args.metrics_url.replace("/metrics", "/health"), timeout=10)
    print(f"preflight /health: {h.status_code}")
    m0 = poll_metrics(sess, args.metrics_url)
    print(f"preflight /metrics ok={m0['ok']} waiting={m0['waiting']} "
          f"kv={m0['kv']} preempt={m0['preempt']}\n")

    g = threading.Thread(target=guard, daemon=True)
    g.start()

    idx = 0
    summary = []
    palier_list = args.paliers.split(",")
    for p_i, palier in enumerate(palier_list):
        n, minutes = (int(x) for x in palier.split(":"))
        if stop.is_set():
            print(f"palier N={n} SAUTE (garde declenchee)")
            break
        p_t0 = time.time()
        p_end = p_t0 + minutes * 60
        m_pre = poll_metrics(sess, args.metrics_url)
        print(f"=== palier N={n} pendant {minutes} min "
              f"(debut {time.strftime('%H:%M:%S', time.gmtime(p_t0))}Z) ===")

        def worker(wid):
            nonlocal idx
            while not stop.is_set() and time.time() < p_end:
                with lock:
                    idx += 1
                    my = idx
                target = sizes[my % len(sizes)]
                rec = one_request(sess, args.base, key, args.model,
                                  build_prompt(target, shared_block, my),
                                  args.max_tokens, args.req_timeout, my)
                rec.update({"palier": n, "worker": wid, "target_ptok": target})
                with lock:
                    recs.append(rec)
                if rec["err"]:
                    print(f"  [w{wid}] req#{my} ERREUR {rec['err'][:120]}")
                else:
                    print(f"  [w{wid}] req#{my} ptok={rec['ptok']} ctok={rec['ctok']} "
                          f"ttft={rec['ttft']:.1f}s e2e={rec['e2e']:.1f}s")

        threads = [threading.Thread(target=worker, args=(w,)) for w in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        m_post = poll_metrics(sess, args.metrics_url)

        with lock:
            precs = [r for r in recs if r["palier"] == n and not r["err"]]
        e2es = [r["e2e"] for r in precs]
        ttfts = [r["ttft"] for r in precs if r["ttft"]]
        ptoks = [r["ptok"] for r in precs if r["ptok"]]
        waits = probe["waiting"]
        preempt_delta = None
        if m_pre["preempt"] is not None and m_post["preempt"] is not None:
            preempt_delta = m_post["preempt"] - m_pre["preempt"]
        row = {
            "palier": n, "minutes": minutes, "ok": len(precs),
            "err": sum(1 for r in recs if r["palier"] == n and r["err"]),
            "p50_e2e": percentile(e2es, 50), "p95_e2e": percentile(e2es, 95),
            "p99_e2e": percentile(e2es, 99), "max_e2e": max(e2es) if e2es else None,
            "p50_ttft": percentile(ttfts, 50), "max_ttft": max(ttfts) if ttfts else None,
            "mean_ptok": sum(ptoks) / len(ptoks) if ptoks else None,
            "max_waiting": max(waits) if waits else None,
            "preempt_delta": preempt_delta,
            "kv_max": max((k for k in probe["kv"] if k is not None), default=None),
            "aborted": stop.is_set(),
        }
        summary.append(row)
        def _f(v):
            return f"{v:.1f}" if isinstance(v, (int, float)) else "n/a"

        print(f"=== palier N={n} RESUME : ok={row['ok']} err={row['err']} "
              f"p50/p95/p99 e2e={_f(row['p50_e2e'])}/{_f(row['p95_e2e'])}/"
              f"{_f(row['p99_e2e'])}s preempt_delta={row['preempt_delta']} "
              f"max_waiting={row['max_waiting']}\n")
        if stop.is_set():
            break
        if p_i < len(palier_list) - 1:
            time.sleep(120)  # interlude entre paliers, pas apres le dernier

    stop.set()
    with open(args.out, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    print("\n===== RESUME FINAL =====")
    for row in summary:
        print(json.dumps(row))
    print(f"\n{len(recs)} requetes ecrites dans {args.out}")


if __name__ == "__main__":
    main()
