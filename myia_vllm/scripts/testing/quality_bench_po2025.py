#!/usr/bin/env python3
"""quality_bench_po2025.py — banc qualité large du siège mini (issue #70, Q5).

Répond à Q5 : « la qualité du checkpoint NVFP4 servi repose sur 5 prompts A/B —
faut-il une passe large ? ». Le banc génère N tâches DÉTERMINISTES (graine fixe)
dont la réponse est CALCULÉE par la machine, pas jugée par un modèle : chaque
prompt est noté par exécution (comparaison exacte / parsing JSON / comptage),
jamais par appréciation. Deux modèles sur les mêmes prompt ⇒ comparaison
appariée (NVFP4 servi vs BF16 rollback).

Catégories (8 × 15 = 120 par défaut) :
  arith      — arithmétique entière, réponse = un nombre
  extract    — extraction de champs d'un dossier en JSON
  transform  — transformation de chaîne (majuscules)
  count      — comptage de caractères dans un texte fourni
  json       — sortie JSON à schéma imposé
  grounded   — question factuelle sur un texte fourni (le fait y est)
  constraint — contrainte de forme (phrase de exactement N mots)
  sort       — tri numérique croissant

Usage :
  python quality_bench_po2025.py --label nvfp4          # prod actuelle :5003
  python quality_bench_po2025.py --label bf16 --url http://localhost:5003
Sortie : JSON horodaté dans myia_vllm/_logs/, résumé console par catégorie.
Clé lue dans myia_vllm/.env (VLLM_API_KEY_MINI) — jamais en argument.
"""
import argparse
import json
import os
import random
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ENV_PATH = os.path.join(REPO, "myia_vllm", ".env")
LOG_DIR = os.path.join(REPO, "myia_vllm", "_logs")

SEED = 20261104
PER_CAT = 15
MAX_TOKENS = 320


def load_key() -> str:
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"VLLM_API_KEY_MINI=(\S+)", line.strip())
            if m:
                return m.group(1)
    sys.exit("VLLM_API_KEY_MINI introuvable dans myia_vllm/.env")


def build_tasks() -> list:
    """Génère les tâches et leurs oracles — tout calculé ici, jamais par le modèle."""
    rnd = random.Random(SEED)
    tasks = []

    for i in range(PER_CAT):  # arith
        a, b, c = rnd.randint(11, 99), rnd.randint(2, 9), rnd.randint(1, 50)
        expr, val = f"{a} * {b} + {c}", a * b + c
        tasks.append(dict(cat="arith", prompt=f"Calcule {expr}. Réponds uniquement par le nombre.",
                          oracle=str(val)))

    noms = ["Dupont", "Martin", "Bernard", "Petit", "Durand", "Leroy", "Moreau", "Simon"]
    for i in range(PER_CAT):  # extract
        cmd, nom = rnd.randint(1000, 9999), rnd.choice(noms)
        montant = rnd.randint(10, 990)
        date = f"2026-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}"
        tasks.append(dict(
            cat="extract",
            prompt=("Extrais les champs de ce dossier et réponds UNIQUEMENT par un JSON avec les clés "
                    f"commande (nombre), client (chaîne), montant (nombre entier, sans devise) :\n"
                    f"« Commande {cmd}, client : {nom}, montant : {montant} EUR, date : {date}. »"),
            oracle=json.dumps({"commande": cmd, "client": nom, "montant": montant}, ensure_ascii=False)))

    mots = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]
    for i in range(PER_CAT):  # transform
        phrase = " ".join(rnd.choice(mots) for _ in range(4))
        tasks.append(dict(cat="transform", prompt=f"Écris cette phrase en MAJUSCULES, sans rien ajouter : « {phrase} »",
                          oracle=phrase.upper()))

    for i in range(PER_CAT):  # count
        lettre = rnd.choice("abcdefghilmnoprstu")
        texte = "".join(rnd.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(60))
        tasks.append(dict(cat="count",
                          prompt=(f"Combien de fois la lettre « {lettre} » apparaît-elle dans ce texte ? "
                                  f"Réponds uniquement par un nombre.\nTexte : {texte}"),
                          oracle=str(texte.count(lettre))))

    for i in range(PER_CAT):  # json
        n = rnd.randint(1, 9)
        tasks.append(dict(cat="json",
                          prompt=(f"Réponds UNIQUEMENT par un JSON valide avec exactement deux clés : "
                                  f"\"status\" valant \"ok\" et \"n\" valant {n}. Aucun texte autour."),
                          oracle=json.dumps({"status": "ok", "n": n})))

    villes = {"Lyon": "Rhône", "Nantes": "Loire-Atlantique", "Lille": "Nord", "Brest": "Finistère",
              "Nice": "Alpes-Maritimes", "Reims": "Marne"}
    for i in range(PER_CAT):  # grounded
        v = rnd.choice(list(villes))
        tasks.append(dict(cat="grounded",
                          prompt=(f"Texte : « La préfecture du département {villes[v]} est {v}. » "
                                  f"Quelle ville est la préfecture du département {villes[v]} ? "
                                  "Réponds uniquement par le nom de la ville."),
                          oracle=v))

    for i in range(PER_CAT):  # constraint
        n = rnd.randint(4, 7)
        tasks.append(dict(cat="constraint",
                          prompt=(f"Réponds par une phrase de exactement {n} mots sur la mer. "
                                  "Aucun autre texte."),
                          oracle=str(n)))

    for i in range(PER_CAT):  # sort
        nums = rnd.sample(range(10, 99), 5)
        tasks.append(dict(cat="sort",
                          prompt=("Classe ces nombres par ordre croissant et réponds uniquement par la liste, "
                                  f"séparée par des virgules : {', '.join(map(str, nums))}"),
                          oracle=",".join(map(str, sorted(nums)))))

    return tasks


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).strip("«»\"' .")


def first_int(s: str):
    m = re.search(r"-?\d+", s or "")
    return int(m.group(0)) if m else None


def extract_json(s: str):
    m = re.search(r"\{.*\}", s or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def score(cat: str, out: str, oracle: str):
    """Retourne (ok, detail). Toute la notation est mécanique."""
    if cat == "arith":
        return (first_int(out) == int(oracle)), f"attendu {oracle} / lu {first_int(out)}"
    if cat == "extract":
        o = json.loads(oracle)
        got = extract_json(out) or {}
        ok = all(str(got.get(k)).strip().lower() == str(o[k]).strip().lower() for k in o)
        return ok, f"attendu {oracle} / lu {json.dumps(got, ensure_ascii=False)[:160]}"
    if cat == "transform":
        return norm(out).upper() == oracle, f"attendu {oracle!r} / lu {norm(out)[:80]!r}"
    if cat == "count":
        return (first_int(out) == int(oracle)), f"attendu {oracle} / lu {first_int(out)}"
    if cat == "json":
        o = json.loads(oracle)
        got = extract_json(out)
        ok = isinstance(got, dict) and got.get("status") == "ok" and str(got.get("n")) == str(o["n"])
        return ok, f"attendu {oracle} / lu {(json.dumps(got) if got else out)[:120]}"
    if cat == "grounded":
        return oracle.lower() in (out or "").lower(), f"attendu {oracle!r} / lu {norm(out)[:80]!r}"
    if cat == "constraint":
        words = [w for w in re.split(r"\s+", norm(out)) if w]
        return len(words) == int(oracle), f"attendu {oracle} mots / lu {len(words)} ({norm(out)[:80]!r})"
    if cat == "sort":
        got = re.findall(r"-?\d+", out or "")
        return ",".join(got[:5]) == oracle, f"attendu {oracle} / lu {','.join(got[:5])}"
    return False, "catégorie inconnue"


def ask(base: str, key: str, model: str, prompt: str) -> str:
    payload = {"model": model, "max_tokens": MAX_TOKENS, "temperature": 0.0,
               "chat_template_kwargs": {"enable_thinking": False},
               "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(base + "/v1/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        body = json.loads(r.read())
    msg = body["choices"][0]["message"]
    content = msg.get("content") or ""
    if not content and msg.get("reasoning_content"):
        content = msg["reasoning_content"]
    return content


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:5003")
    ap.add_argument("--model", default="frognano-4b")
    ap.add_argument("--label", required=True, help="étiquette du run (nvfp4, bf16, ...)")
    ap.add_argument("--limit", type=int, default=0, help="0 = tout")
    args = ap.parse_args()

    key = load_key()
    tasks = build_tasks()
    if args.limit:
        tasks = tasks[: args.limit]

    results = []
    t_start = time.time()
    for i, t in enumerate(tasks, 1):
        t0 = time.time()
        try:
            out = ask(args.url, key, args.model, t["prompt"])
            ok, detail = score(t["cat"], out, t["oracle"])
            err = None
        except Exception as e:  # un échec d'appel est noté, jamais masqué
            out, ok, detail, err = "", False, "appel en échec", repr(e)
        results.append(dict(i=i, cat=t["cat"], ok=ok, detail=detail, err=err,
                            out=out[:400], dt=round(time.time() - t0, 2)))
        print(f"[{i}/{len(tasks)}] {t['cat']:<10} {'OK ' if ok else 'FAIL'} {detail[:110]}", flush=True)

    cats = {}
    for r in results:
        c = cats.setdefault(r["cat"], {"n": 0, "ok": 0})
        c["n"] += 1
        c["ok"] += int(r["ok"])

    total = len(results)
    ok_total = sum(int(r["ok"]) for r in results)
    summary = {
        "label": args.label,
        "url": args.url,
        "model": args.model,
        "at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(time.time() - t_start, 1),
        "n": total,
        "ok": ok_total,
        "acc": round(ok_total / total, 4) if total else None,
        "by_cat": {k: {"n": v["n"], "ok": v["ok"], "acc": round(v["ok"] / v["n"], 4)}
                   for k, v in sorted(cats.items())},
        "results": results,
    }
    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(LOG_DIR, f"quality_bench_{args.label}_{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)

    print(f"\n== {args.label} : {ok_total}/{total} = {summary['acc']:.3f} en {summary['elapsed_s']} s")
    for k, v in summary["by_cat"].items():
        print(f"   {k:<10} {v['ok']}/{v['n']} = {v['acc']:.3f}")
    print(f"-> {path}")


if __name__ == "__main__":
    main()
