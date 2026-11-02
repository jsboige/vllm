"""Fiche de capacite servie - FrogNano-4B (po-2025:5003).

Mesure le debit et la latence sur une delegation REALISTE (extraction verbatim
de lignes WARN dans un journal), pas sur un prompt synthetique. Ecrit
bench_capacity_out.json dans le repertoire courant.

La sortie de chaque niveau est comparée au corpus attendu (voir
verify_quality.py, ou recompter a la main : le prompt demande les lignes
contenant WARN, le corpus en contient un nombre connu).

Usage:
    python bench_capacity.py [--concurrency 1,8,16] [--base URL] [--model NAME]

La cle est lue dans myia_vllm/.env (VLLM_API_KEY_MINI), jamais en argument.
"""
import json
import re
import statistics
import sys
import threading
import time
from pathlib import Path

import requests

DEFAULT_BASE = "http://localhost:5003/v1/chat/completions"
DEFAULT_MODEL = "frognano-4b"
# myia_vllm/scripts/adoption/bench_capacity.py -> myia_vllm/.env
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def read_key(env_path=ENV_PATH):
    if not env_path.exists():
        raise SystemExit(f"cle introuvable: {env_path} absent")
    txt = env_path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"^VLLM_API_KEY_MINI\s*=\s*(\S+)", txt, re.M)
    if not m:
        raise SystemExit(f"VLLM_API_KEY_MINI absent de {env_path}")
    return m.group(1)


def build_prompt(n_lines=32):
    """Corpus de la MEME FORME que _logs/gpu-governor.log, WARN toutes les 8 lignes."""
    lines = []
    for i in range(n_lines):
        hh = 5 + i
        day = "2026-11-01" if hh < 24 else "2026-11-02"
        hh = hh % 24
        if i % 8 == 3:
            lines.append(
                f"{day} {hh:02d}:02:03 WARN RAM basse free={7000 - i * 170}MB temp=31C mode=normal"
            )
        else:
            lines.append(
                f"{day} {hh:02d}:02:03 HEARTBEAT temp=31C free={7000 - i * 170}MB mode=normal"
            )
    corpus = "\n".join(lines)
    prompt = (
        "Tu es le Controleur d'alertes. Recopie VERBATIM, une ligne par ligne, toutes "
        "les lignes du corpus ci-dessous qui contiennent le mot WARN. N'ajoute aucun "
        "commentaire, ne compte pas, ne resume pas, ne reformate pas. Si aucune ligne "
        "ne contient WARN, reponds uniquement VIDE.\n\nCORPUS ("
        f"{n_lines} lignes) :\n---\n{corpus}\n---"
    )
    return prompt, lines


def one_call(key, prompt, idx, results, base, model, max_tokens=192):
    t0 = time.time()
    ttft = None
    completion = ""
    usage = {}
    try:
        r = requests.post(
            base,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.0,
                "stream": True,
                "stream_options": {"include_usage": True},
            },
            timeout=180,
            stream=True,
        )
        r.raise_for_status()
        for raw in r.iter_lines():
            if not raw:
                continue
            chunk = raw.decode("utf-8", "ignore")
            if not chunk.startswith("data: "):
                continue
            payload = chunk[6:].strip()
            if payload == "[DONE]":
                break
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if obj.get("usage"):
                usage = obj["usage"]
            for ch in obj.get("choices") or []:
                piece = (ch.get("delta") or {}).get("content") or ""
                if piece:
                    if ttft is None:
                        ttft = time.time() - t0
                    completion += piece
    except Exception as exc:  # noqa: BLE001
        results[idx] = {"error": str(exc)[:120]}
        return
    results[idx] = {
        "ttft": ttft,
        "total": time.time() - t0,
        "ptok": usage.get("prompt_tokens"),
        "ctok": usage.get("completion_tokens"),
        "text": completion,
    }


def run_level(key, prompt, n, base, model):
    results = [None] * n
    threads = [
        threading.Thread(target=one_call, args=(key, prompt, i, results, base, model))
        for i in range(n)
    ]
    t0 = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.time() - t0
    ok = [r for r in results if r and "error" not in r]
    errs = [r for r in results if r and "error" in r]
    if not ok:
        return {"n": n, "wall": wall, "errors": len(errs), "detail": errs[:1]}
    ctoks = sum(r["ctok"] or 0 for r in ok)
    ptoks = sum(r["ptok"] or 0 for r in ok)
    return {
        "n": n,
        "wall": wall,
        "ok": len(ok),
        "errors": len(errs),
        "ptok": ptoks,
        "ctok": ctoks,
        "agg_tps": ctoks / wall if wall else 0,
        "ttft_med": statistics.median(r["ttft"] for r in ok if r["ttft"]),
        "ttft_max": max((r["ttft"] for r in ok if r["ttft"]), default=0),
        "lat_med": statistics.median(r["total"] for r in ok),
        "lat_max": max(r["total"] for r in ok),
        "per_req_tps": statistics.median(
            (r["ctok"] or 0) / r["total"] for r in ok if r["total"]
        ),
        "sample": ok[0]["text"],
    }


def main():
    argv = sys.argv

    def arg(name, default):
        return argv[argv.index(name) + 1] if name in argv else default

    levels = [int(x) for x in arg("--concurrency", "1,8,16").split(",")]
    base = arg("--base", DEFAULT_BASE)
    model = arg("--model", DEFAULT_MODEL)
    key = read_key()
    prompt, corpus_lines = build_prompt()
    warn_expected = sum(1 for ln in corpus_lines if "WARN" in ln)

    print(f"corpus: {len(corpus_lines)} lignes, {warn_expected} attendues contenant WARN")
    print(f"prompt: {len(prompt)} caracteres | base={base} model={model}\n")

    # warm-up (premier appel = JIT/torch.compile si le moteur vient de demarrer)
    warm = [None]
    one_call(key, prompt, 0, warm, base, model, max_tokens=32)
    print(f"warm-up: {warm[0].get('total', 0):.2f}s (non compte)\n")

    rows = []
    for n in levels:
        res = run_level(key, prompt, n, base, model)
        res["warn_expected"] = warn_expected
        rows.append(res)
        if res.get("ok"):
            print(
                f"N={n:<3} wall={res['wall']:6.2f}s  agg={res['agg_tps']:7.1f} tok/s  "
                f"per-req={res['per_req_tps']:6.1f} tok/s  "
                f"TTFT med={res['ttft_med']:.2f}s max={res['ttft_max']:.2f}s  "
                f"lat med={res['lat_med']:5.2f}s max={res['lat_max']:5.2f}s  "
                f"ok={res['ok']}/{n} err={res['errors']}  "
                f"ptok={res['ptok']} ctok={res['ctok']}  "
                f"verbatim={'OUI' if res['sample'].count('WARN') == warn_expected else 'NON'}"
            )
        else:
            print(f"N={n:<3} ECHEC wall={res['wall']:.2f}s err={res['errors']} {res.get('detail')}")

    with open("bench_capacity_out.json", "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)
    print("\n-> bench_capacity_out.json")


if __name__ == "__main__":
    main()
