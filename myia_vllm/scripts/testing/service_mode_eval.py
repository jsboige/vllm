#!/usr/bin/env python3
"""Mesure SERVICE-MODE du harnais voltron (adoption, 18/11).

Rejoue le banc real_task_bench (40 tâches réelles) À TRAVERS le service HTTP
(127.0.0.1:5029) : chaque tâche est convertie en CONTRAT d'appelant, la
réponse du service est :
  1. notée pour son propre gate (ok du service — ce que voit l'appelant),
  2. évaluée contre l'ORACLE du banc (la vérité plus forte : famille exacte,
     pas seulement dans la taxonomie ; etc.).

Donne le chiffre honnête pour la doc d'adoption : « le service rend ok=X %
et ses réponses passent la vérité-terrain à Y % ».

Usage:
  python service_mode_eval.py [--limit N] [--families a,b] [--out fichier.json]
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
import real_task_bench as rb

SERVICE = "http://127.0.0.1:5029"
CLASSES = ["weight-shape", "engine-init", "path-mangling",
           "benign-boot", "bench-fail", "container-died"]


def post(path, payload, timeout=400):
    req = urllib.request.Request(SERVICE + path,
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def to_contract(t):
    """Tâche banc → (contrat service, fn d'évaluation de la réponse)."""
    if t["cat"] == "err-classify":
        src = t["oracle"]["source"]
        contract = {"type": "classify", "data": src, "classes": CLASSES}

        def ev(out):
            got = rb.extract_json_obj(out) or {}
            return rb.check_classify(json.dumps({"famille": got.get("classe"),
                                                 "ligne_cle": got.get("ligne_cle")}),
                                     t["oracle"])
        return contract, ev

    if t["cat"] == "num-fidelity":
        must = t["oracle"]["must_contain"]
        contract = {"type": "numbers", "data": t["oracle"]["source"],
                    "report_prompt": ("Rédige un rapport d'UNE à deux phrases, en français, "
                                      "citant ces champs avec leurs valeurs exactes "
                                      "(recopiées verbatim)."),
                    "numbers": must}
        return contract, lambda out: rb.check_num_fidelity(out, t["oracle"])

    if t["cat"] == "fail-extract":
        src = t["prompt"].split("DONNÉES:\n", 1)[1]
        label = t["prompt"].split("\n\nRéponds en JSON exact", 1)[0]
        # le label GARDÉ INTÉGRAL (avec son «-> JSON {...») : c'est l'ancre de
        # FORME (liste vs dict, booléens vs «non») — la retirer a coûté 4 tâches
        # (v3 6/12 vs v2 10/12, mesuré 18/11). Les placeholders qu'il contient
        # se traitent côté prompt service (règle placeholder), pas en amputant.
        contract = {"type": "extract", "data": src, "instruction": label,
                    "fields": list(t["oracle"].keys()), "verbatim": False}
        # verbatim=False : les valeurs légitimes sont des nombres/booléens/noms
        # reconstruits (acc 0.7 en float), pas des sous-chaînes de la source.
        # instruction : porte la SÉMANTIQUE de la tâche (« la plus basse
        # accuracy », « nom du fichier ») — sans elle le service rend des
        # valeurs verbatim mais sémantiquement hors-sujet (mesuré 18/11).
        return contract, lambda out: rb.check_json_eq(out, t["oracle"])

    if t["cat"] == "cfg-diff":
        # reconstruire a/b depuis le bloc source de l'oracle
        parts = t["report_oracle"]["source"].split("=== config ")
        ja = json.loads(parts[1].split(" ===\n", 1)[1].rsplit("\n\n=== config", 1)[0])
        jb = json.loads(parts[2].split(" ===\n", 1)[1])
        contract = {"type": "diff", "a": json.dumps(ja), "b": json.dumps(jb)}
        # le gate service (report) == l'oracle banc pour cette famille
        return contract, lambda out: rb.CHECKERS["report"](out, t["report_oracle"])

    raise ValueError(t["cat"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--families", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    fams = set(args.families.split(",")) if args.families else None

    tasks = rb.build_tasks()
    if fams:
        tasks = [t for t in tasks if t["cat"] in fams]
    if args.limit:
        tasks = tasks[:args.limit]

    rows = []
    for i, t in enumerate(tasks):
        contract, ev = to_contract(t)
        t0 = time.time()
        r = post("/v1/task", contract)
        bench_ok, bench_detail = ev(r["answer"])
        rows.append(dict(cat=t["cat"], svc_ok=r["ok"], stage=r["stage"],
                         turns=r["turns"], bench_ok=bench_ok,
                         bench_detail=bench_detail[:120],
                         dt=round(time.time() - t0, 1),
                         answer=r["answer"][:300]))
        print(f"[{i+1}/{len(tasks)}] {t['cat']:<13} svc={'OK ' if r['ok'] else 'FAIL'}"
              f"({r['stage']},t{r['turns']}) bench={'OK ' if bench_ok else 'FAIL'}"
              f" {r['dt_s']}s {bench_detail[:70]}", flush=True)

    n = len(rows)
    svc = sum(r["svc_ok"] for r in rows)
    bench = sum(r["bench_ok"] for r in rows)
    by = {}
    for r in rows:
        c = by.setdefault(r["cat"], {"n": 0, "svc": 0, "bench": 0, "turns": 0})
        c["n"] += 1
        c["svc"] += int(r["svc_ok"])
        c["bench"] += int(r["bench_ok"])
        c["turns"] += r["turns"]
    summary = dict(at=datetime.now(timezone.utc).isoformat(), n=n,
                   svc_ok=svc, svc_acc=round(svc / n, 4) if n else None,
                   bench_ok=bench, bench_acc=round(bench / n, 4) if n else None,
                   appels=sum(r["turns"] for r in rows),
                   by_cat={k: {**v, "svc_acc": round(v["svc"] / v["n"], 3),
                               "bench_acc": round(v["bench"] / v["n"], 3)}
                           for k, v in sorted(by.items())})
    print("\n== SERVICE-MODE :", f"svc {svc}/{n} = {summary['svc_acc']:.1%}",
          f"| vérité banc {bench}/{n} = {summary['bench_acc']:.1%}",
          f"| {summary['appels']} appels ({summary['appels']/n:.2f}/tâche)")
    for k, v in summary["by_cat"].items():
        print(f"   {k:<13} svc {v['svc']}/{v['n']} bench {v['bench']}/{v['n']}")

    out = args.out or (r"D:\vllm-data\bench\service_mode_"
                       + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dict(summary=summary, rows=rows), f, ensure_ascii=False, indent=1)
    print("JSON:", out)


if __name__ == "__main__":
    main()
