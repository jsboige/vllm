#!/usr/bin/env python3
"""Harnais conversationnel v2 — tâches réelles (mandat user 17-18/11 : « rendre le
modèle utile », fiabilisation par conversation agentique sous gates).

Phases (chaînage pour UNE fenêtre GPU — une seule instance 1.7B à la fois) :
  A  worker      : voltron tente (1 appel t0), puis réparation CONVERSATIONNELLE
                   dirigée (≤ k rounds : la conversation porte la réponse précédente
                   + le delta signé du gate — jamais la réponse attendue)
  B  critic      : 2xmerge (engine séparé) reçoit tâche + transcription + erreur du
                   gate et produit la réponse corrigée — re-gatée
  C  coordinator : swift-1.5-27b via hub claudish (ZAI_API_KEY en env runtime),
                   même contrat, re-gaté

Toutes les sorties passent par les oracles mécaniques de real_task_bench —
personne n'est cru, pas même le coordinateur.

Usage:
  python voltron_harness_v2.py --phase a --url http://127.0.0.1:5028 --model voltron-1-mini
  python voltron_harness_v2.py --phase b --url http://127.0.0.1:5028 --model lfm3-2xmerge
  python voltron_harness_v2.py --phase c            (hub, pas de GPU)
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import real_task_bench as rb  # noqa: E402

HUB_URL = "http://192.168.0.50:3000"  # chat() ajoute /v1/chat/completions
HUB_MODEL = "swift-1.5-27b"
STATE_DIR = r"D:\vllm-data\bench\v2_state"
MAX_REPAIR_ROUNDS = 2


# ---------------------------------------------------------------- transport

def chat(url, model, messages, max_tokens=400, timeout=120, api_key=None):
    payload = {"model": model, "messages": messages,
               "max_tokens": max_tokens, "temperature": 0.0}
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions",
                                 data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    return d["choices"][0]["message"]["content"] or ""


def hub_key():
    """Clé client du hub : env runtime uniquement, jamais écrite dans un fichier."""
    k = os.environ.get("ZAI_API_KEY")
    if not k:
        raise SystemExit("ZAI_API_KEY absent de l'environnement (phase c)")
    return k


# ---------------------------------------------------------------- feedback dirigé (delta, jamais la réponse)

def json_diff_hint(got, expected):
    if not isinstance(got, dict):
        return "ta réponse n'était pas un objet JSON parsable ; réponds uniquement le JSON."
    hints = []
    for k, v in expected.items():
        if k not in got:
            hints.append(f"clé manquante : '{k}'")
        elif got[k] != v:
            hints.append(f"clé '{k}' : valeur erronée")
    for k in got:
        if k not in expected:
            hints.append(f"clé en trop : '{k}'")
    return "corrections : " + " ; ".join(hints) if hints else "valeurs à corriger"


def build_feedback(task, out, ok, detail):
    """Message de réparation : porte l'erreur du gate, jamais la solution."""
    if task["checker"] == "num_fidelity":
        return (f"Le vérificateur a rejeté ta réponse : {detail}. "
                f"Recite exactement les champs demandés depuis les DONNÉES, et "
                f"supprime tout nombre qui n'y figure pas. Réponds uniquement le rapport corrigé.")
    if task["checker"] == "json_eq":
        got = rb.extract_json_obj(out) or {}
        return (f"Le vérificateur a rejeté ton JSON : {json_diff_hint(got, task['oracle'])}. "
                f"Relis les DONNÉES et renvoie uniquement le JSON corrigé, exact au format demandé.")
    if task["checker"] == "classify":
        return ("La famille indiquée est incorrecte ou ta ligne_cle ne cite pas la ligne "
                "diagnostique. Re-examine le LOG : weight-shape = forme de tenseurs au "
                "chargement, engine-init = échec d'initialisation du moteur, path-mangling = "
                "chemin Unix réécrit en chemin Windows, benign-boot = démarrage normal, "
                "bench-fail = échec d'une tâche de banc, container-died = conteneur mort. "
                "Renvoie uniquement le JSON corrigé.")
    return f"Réponse rejetée : {detail}. Corrige et renvoie uniquement la réponse."


def gate(task, out):
    ok, detail = rb.CHECKERS[task["checker"]](out, task["oracle"])
    return ok, detail


# ---------------------------------------------------------------- phases

def run_phase_a(url, model, limit=0):
    tasks = rb.build_tasks()
    if limit:
        tasks = tasks[:limit]
    results = []
    for i, t in enumerate(tasks):
        msgs = [{"role": "user", "content": t["prompt"]}]
        t0 = time.time()
        out = chat(url, model, msgs)
        ok, detail = gate(t, out)
        turns = 1
        transcript = list(msgs) + [{"role": "assistant", "content": out}]
        while not ok and turns <= MAX_REPAIR_ROUNDS:
            fb = build_feedback(t, out, ok, detail)
            transcript.append({"role": "user", "content": fb})
            out = chat(url, model, transcript)
            ok, detail = gate(t, out)
            transcript.append({"role": "assistant", "content": out})
            turns += 1
        results.append(dict(i=i, cat=t["cat"], ok=ok, turns=turns,
                            detail=detail, dt=round(time.time() - t0, 2),
                            transcript=transcript))
        print(f"[{i}/{len(tasks)}] {t['cat']:<13} {'OK ' if ok else 'FAIL'} "
              f"tours={turns} {detail[:90]}", flush=True)
    return results


def load_residuals(path):
    return json.load(open(path, encoding="utf-8"))


def run_phase_b(url, model, residuals_path):
    """Le sibling critique : reçoit la transcription, rend une réponse corrigée, re-gatée."""
    residuals = load_residuals(residuals_path)
    tasks = rb.build_tasks()
    out_all = []
    for r in residuals:
        t = tasks[r["i"]]
        transcript = r["transcript"]
        # dernières réponse + erreur du gate
        last_asst = next((m["content"] for m in reversed(transcript)
                          if m["role"] == "assistant"), "")
        prompt = (t["prompt"] + "\n\n=== RÉPONSE REJETÉE DU WORKER ===\n" + last_asst +
                  "\n\n=== ERREUR DU VÉRIFICATEUR ===\n" + r["detail"] +
                  "\n\nProduis la réponse CORRIGÉE, au format exact demandé, rien d'autre.")
        try:
            out = chat(url, model, [{"role": "user", "content": prompt}], max_tokens=500)
            ok, detail = gate(t, out)
        except Exception as e:
            out, ok, detail = "", False, f"appel échoué: {e!r}"
        out_all.append(dict(i=r["i"], cat=t["cat"], ok=ok, detail=detail, out=out[:400]))
        print(f"[{r['i']}] {t['cat']:<13} critic {'OK ' if ok else 'FAIL'} {detail[:90]}", flush=True)
    return out_all


def run_phase_c(residuals_path):
    """Coordinateur swift-27b via hub — re-gaté comme les autres.

    MESURÉ (18/11) : le prompt doit être SEC. Inclure les tentatives rejetées du
    1.7B pollue le 27B (0/6 cfg-diff pollué vs 3/6 sec) — le brouillon bavard d'un
    petit modèle est du bruit pour le grand. Budget 3000 : les réponses justes sont
    courtes (82 tok) mais les JSON cfg-diff légitimes dépassent 1200 (finish=length,
    JSON correct tronqué en préfixe)."""
    residuals = load_residuals(residuals_path)
    tasks = rb.build_tasks()
    key = hub_key()
    out_all = []
    for r in residuals:
        t = tasks[r["i"]]
        prompt = (t["prompt"] +
                  "\n\n(Les tentatives précédentes d'un modèle plus petit ont toutes été "
                  "rejetées par un vérificateur mécanique. Réponds au format exact "
                  "demandé, rien d'autre.)")
        try:
            out = chat(HUB_URL, HUB_MODEL, [{"role": "user", "content": prompt}],
                       max_tokens=3000, timeout=300, api_key=key)
            ok, detail = gate(t, out)
        except Exception as e:
            out, ok, detail = "", False, f"appel hub échoué: {e!r}"
        out_all.append(dict(i=r["i"], cat=t["cat"], ok=ok, detail=detail, out=out[:400]))
        print(f"[{r['i']}] {t['cat']:<13} coord {'OK ' if ok else 'FAIL'} {detail[:90]}", flush=True)
    return out_all


# ---------------------------------------------------------------- main

def save(path, obj):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(os.path.join(STATE_DIR, path), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    return os.path.join(STATE_DIR, path)


def summarize(label, results):
    n = len(results)
    ok = sum(int(r["ok"]) for r in results)
    turns = sum(r.get("turns", 1) for r in results)
    cats = {}
    for r in results:
        c = cats.setdefault(r["cat"], {"n": 0, "ok": 0})
        c["n"] += 1
        c["ok"] += int(r["ok"])
    return {"label": label, "at": datetime.now(timezone.utc).isoformat(),
            "n": n, "ok": ok, "acc": round(ok / n, 4) if n else None,
            "appels": turns, "appels_par_tache": round(turns / n, 2) if n else None,
            "by_cat": {k: {"n": v["n"], "ok": v["ok"], "acc": round(v["ok"] / v["n"], 4)}
                       for k, v in sorted(cats.items())}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=["a", "b", "c"])
    ap.add_argument("--url", default="http://127.0.0.1:5028")
    ap.add_argument("--model", default="voltron-1-mini")
    ap.add_argument("--residuals", default=None)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if args.phase == "a":
        results = run_phase_a(args.url, args.model, args.limit)
        summary = summarize(f"v2a-{args.model}", results)
        residuals = [r for r in results if not r["ok"]]
        p = save(f"residuals_after_a_{stamp}.json", residuals)
        print(f"\n== phase A {args.model} : {summary['ok']}/{summary['n']} = {summary['acc']:.3f}"
              f" en {summary['appels']} appels ({summary['appels_par_tache']}/tâche)")
        print(f"résiduels: {len(residuals)} -> {p}")
    elif args.phase == "b":
        results = run_phase_b(args.url, args.model, args.residuals)
        summary = summarize(f"v2b-{args.model}", results)
        residuals = [dict(i=r["i"], cat=r["cat"], detail=r["detail"], out=r["out"])
                     for r in results if not r["ok"]]
        p = save(f"residuals_after_b_{stamp}.json", residuals)
        print(f"\n== phase B {args.model} : {summary['ok']}/{summary['n']} sauvés par le critique")
        print(f"résiduels restants: {len(residuals)} -> {p}")
    else:
        results = run_phase_c(args.residuals)
        summary = summarize(f"v2c-{HUB_MODEL}", results)
        print(f"\n== phase C {HUB_MODEL} : {summary['ok']}/{summary['n']} sauvés par le coordinateur")
    save(f"summary_{args.phase}_{stamp}.json", summary)


if __name__ == "__main__":
    main()
