#!/usr/bin/env python3
"""Banc de tâches réelles pour voltron & siblings LFM3 (po-2028:vllm, v2).

Toutes les tâches sont construites depuis des artefacts RÉELS du siège
(logs docker, sorties bench, configs, git log — copiés dans real_corpus/),
avec oracles mécaniques calculés au build. Familles:

  err-classify  : fenêtre de log -> famille d'incident (JSON)
  num-fidelity  : rapport citant des champs chiffrés -> zéro nombre inventé
  fail-extract  : extraction structurée -> JSON exact
  cfg-diff      : diff de configs -> JSON des clés divergentes

Même interface/schéma de sortie que quality_bench_po2025.py (--url --model --label).
"""
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

CORPUS = r"D:\vllm-data\bench\real_corpus"
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "myia_vllm", "_logs")

NUM_RE = re.compile(r"(?<![A-Za-z0-9_])\d+(?![A-Za-z0-9_])")  # pas le '3' de lfm3-2xmerge

# ---------------------------------------------------------------- corpus load

def read(name, a=None, b=None):
    with open(os.path.join(CORPUS, name), encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    return lines if a is None else lines[a:b]


def read_text(name):
    with open(os.path.join(CORPUS, name), encoding="utf-8", errors="replace") as f:
        return f.read()


def window(name, a, b):
    return "\n".join(read(name, a, b))


# ---------------------------------------------------------------- oracles

def extract_json_obj(s):
    """Dernier objet JSON COMPLET de la réponse (raw_decode équilibré, pas un
    regex greedy — un préambule textuel autour du JSON ne casse plus l'oracle)."""
    dec = json.JSONDecoder()
    for i in sorted((m.start() for m in re.finditer(r"\{", s)), reverse=True):
        try:
            obj, _ = dec.raw_decode(s, i)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


def extract_json_objs(s):
    """Tous les objets JSON complets de la réponse, dans l'ordre."""
    dec = json.JSONDecoder()
    objs = []
    for m in re.finditer(r"\{", s):
        try:
            obj, _ = dec.raw_decode(s, m.start())
            if isinstance(obj, dict):
                objs.append(obj)
        except json.JSONDecodeError:
            continue
    return objs


def extract_json_obj(s):
    """Dernier objet JSON COMPLET de la réponse (raw_decode équilibré, pas un
    regex greedy — un préambule textuel autour du JSON ne casse plus l'oracle)."""
    objs = extract_json_objs(s)
    return objs[-1] if objs else None


def merged_json_obj(out):
    """Union shallow des objets trouvés (un modèle qui rend un objet par
    entité au lieu d'un objet unique a quand même les bonnes valeurs)."""
    objs = extract_json_objs(out)
    if not objs:
        return None
    merged = {}
    for o in objs:
        merged.update(o)
    return merged


def check_json_eq(out, expected):
    objs = extract_json_objs(out)
    if not objs:
        return False, "pas de JSON dans la réponse"
    if any(o == expected for o in objs):
        return True, ""
    merged = merged_json_obj(out)
    if merged == expected:
        return True, ""
    return False, f"attendu {json.dumps(expected, ensure_ascii=False)[:160]} / lu {json.dumps(objs[-1], ensure_ascii=False)[:160]}"


def check_num_fidelity(out, payload):
    must, src_text = payload["must_contain"], payload["source"]
    missing = [v for v in must
               if not re.search(rf"(?<!\d){re.escape(v)}(?!\d)", out)]
    src_nums = set(NUM_RE.findall(src_text))
    out_nums = set(NUM_RE.findall(out))
    invented = sorted(out_nums - src_nums)
    if missing:
        return False, f"champs manquants: {missing}"
    if invented:
        return False, f"nombres absents de la source (invention): {invented}"
    return True, ""


def check_classify(out, expected):
    got = extract_json_obj(out) or {}
    fam = got.get("famille")
    if fam != expected["famille"]:
        return False, f"famille attendue {expected['famille']} / lue {fam}"
    key = str(got.get("ligne_cle", ""))
    if any(m in key for m in expected["markers"]):
        return True, ""
    # sinon : une ligne VERBATIM (>= 20 chars) de la fenêtre source vaut
    # diagnostique — le marqueur canonique n'est qu'UNE des lignes valides
    # (mesuré 18/11 : le 27B recopiait `assert ... == loaded_weight.shape`,
    # ligne réellement diagnostique, sans le marqueur d'une autre ligne)
    src = expected.get("source", "")
    stripped = key.strip().strip('"')
    if len(stripped) >= 15 and stripped in src:
        return True, ""
    return False, f"ligne_cle sans marqueur {expected['markers']} et non citée verbatim depuis la fenêtre"


def check_report(out, payload):
    """Rapport fidèle d'un diff fourni par outil : chaque clé divergente citée
    avec ses deux valeurs (None/true/false en forme json OU vernaculaire),
    zéro clé de config inventée."""
    diff = payload["diff"]
    missing = []

    def cited(v):
        forms = {json.dumps(v), str(v)}  # true/True, null/None, 124900
        if v is None:
            return True  # la mention de la clé suffit pour une absence
        if isinstance(v, bool):
            forms |= {"présent" if v else "absent", "present" if v else "absent"}
        if max((len(f) for f in forms), default=0) > 60:
            return True  # valeur non scalaire volumineuse : la mention de la clé
            # + le qualificatif de divergence suffisent (un rapport en prose ne
            # recopie pas 50 lignes d'objet — mesuré 18/11, le 1.7B disait
            # correctement "appears only in coder, not in merge")
        return any(re.search(rf"(?<![\w.]){re.escape(f)}(?![\w.])", out)
                   for f in forms if f)

    for k, (va, vb) in diff.items():
        if not (re.search(rf"(?<![\w]){re.escape(k)}(?![\w])", out)
                and cited(va) and cited(vb)):
            missing.append(k)
    if missing:
        return False, f"clés non citées ou valeurs absentes: {missing[:6]}"
    allowed = set(diff)
    src = payload.get("source", "")
    candidates = re.findall(r'"?([a-z][a-z0-9]*(?:_[a-z0-9]+){1,})"?', out)  # snake_case
    invented = sorted({c for c in candidates
                       if c not in allowed and len(c) > 5 and c not in src})
    if invented:
        return False, f"clés snake_case absentes du diff (invention): {invented[:6]}"
    return True, ""


CHECKERS = {"json_eq": check_json_eq, "num_fidelity": check_num_fidelity,
            "classify": check_classify, "report": check_report}

# ---------------------------------------------------------------- task builders

def build_classify():
    """12 fenêtres réelles labellisées -> famille + ligne clé."""
    fams = {
        "weight-shape": ["load_column_parallel_weight", "AssertionError"],
        "engine-init": ["Engine core initialization failed", "EngineCore failed to start"],
        "path-mangling": ["Repo id must be"],
        "benign-boot": ["Initializing", "Loading safetensors", "health OK"],
        "bench-fail": ["FAIL"],
        "container-died": ["CONTAINER-DIED"],
    }
    specs = [
        ("diag_lfm3-coder.log", 100, 109, "weight-shape"),
        ("diag_lfm3-coder.log", 181, 190, "weight-shape"),
        ("diag_lfm3-coder.log", 248, 255, "engine-init"),
        ("socle_run.log", 52, 58, "container-died"),
        ("boot_msys_fail.log", 24, 33, "path-mangling"),
        ("boot_msys_fail.log", 55, 64, "path-mangling"),
        ("diag_lfm3-coder.log", 28, 33, "engine-init"),  # corrigé 18/11 : la fenêtre
        # TERMINE par `EngineCore failed to start` — le label benign-boot initial
        # était indéfendable (le 27B avait raison contre l'oracle)
        ("socle_run.log", 0, 4, "benign-boot"),  # resserré : 0:5 chevauchait la
        # 1re ligne de bench ([112/120] sort OK), citée à tort comme ligne_cle
        ("socle_run.log", 4, 8, "bench-fail"),
        ("socle_run.log", 27, 32, "bench-fail"),
        ("socle_run.log", 12, 17, "bench-fail"),
        ("boot_msys_fail.log", 0, 5, "container-died"),
    ]
    tasks = []
    for i, (fn, a, b, fam) in enumerate(specs):
        txt = window(fn, a, b)
        prompt = (
            "Voici une fenêtre de log d'infrastructure. Classifie l'incident en UNE famille "
            "parmi : weight-shape, engine-init, path-mangling, benign-boot, bench-fail, container-died.\n"
            "- weight-shape : écart de forme de tenseurs au chargement des poids\n"
            "- engine-init : le moteur n'a pas démarré (échec d'initialisation)\n"
            "- path-mangling : un chemin Unix réécrit en chemin Windows\n"
            "- benign-boot : démarrage/opération normale, PAS un incident\n"
            "- bench-fail : échec d'une tâche de banc (fonctionnement normal du banc)\n"
            "- container-died : conteneur mort pendant le boot\n\n"
            f"Réponds en JSON exactement : {{\"famille\": \"...\", \"ligne_cle\": \"<la ligne "
            "du log la plus diagnostique, recopiée>\"}}\n\nLOG:\n" + txt)
        tasks.append(dict(cat="err-classify", prompt=prompt,
                          checker="classify",
                          oracle=dict(famille=fam, markers=fams[fam], source=txt)))
    return tasks


def build_fidelity():
    """12 rapports chiffrés : chaque champ demandé cité verbatim, zéro nombre inventé."""
    tasks = []
    smi = read_text("nvidia_smi_now.txt")
    data = next((l for l in smi.splitlines()
                 if l.strip() and not l.startswith("name")
                 and ("," in l)), "")
    if data:
        mem = re.search(r"(\d+) MiB", data).group(1)
        temp = re.search(r"MiB,\s*([\d.]+)", data).group(1)
        util = re.search(r"(\d+) %", data).group(1)
        tasks.append(("GPU mémoire (MiB) et température (°C)", [mem, temp], smi))
        tasks.append(("GPU utilisation (%) et température (°C)", [util, temp], smi))
        tasks.append(("GPU mémoire (MiB) et utilisation (%)", [mem, util], smi))
    # socle summaries
    socle = read_text("socle_run.log")
    for model, sc, acc, dur in [("lfm3-2xmerge", "84", "0.700", "23.4"),
                                 ("lfm3-fable51", "73", "0.608", "24.1")]:
        line = next((l for l in socle.splitlines() if model in l and "==" in l), "")
        tasks.append((f"score {model} (score total, acc, durée s)",
                      [sc, acc, dur], line))
    # bench JSON by_cat blocks
    for name, model in [("bench_2xmerge.json", "lfm3-2xmerge"),
                        ("bench_fable51.json", "lfm3-fable51"),
                        ("bench_voltron.json", "voltron")]:
        d = json.loads(read_text(name))
        bc = d["by_cat"]
        worst = min(bc, key=lambda k: bc[k]["acc"])
        block = json.dumps({"by_cat": {worst: bc[worst]}, "ok": d["ok"], "n": d["n"]},
                           ensure_ascii=False)
        tasks.append((f"{model} : pire catégorie (nom + acc) et total ok/n",
                      [worst, str(bc[worst]["acc"]), str(d["ok"]), str(d["n"])], block))
    # git log
    gl = read_text("gitlog_vllm.txt")
    hashes = re.findall(r"^([0-9a-f]{7,12}) ", gl, re.M)
    if len(hashes) >= 3:
        tasks.append(("le hash du commit le plus récent et celui du 3ᵉ commit",
                      [hashes[0], hashes[2]], gl))
        tasks.append((f"les 3 premiers hashes ({', '.join(hashes[:3])})",
                      hashes[:3], gl))
    out = []
    for label, must, src in tasks:
        prompt = (f"Rédige un rapport d'UNE à deux phrases, en français, citant ces champs : "
                  f"{label}. Recopie les valeurs EXACTEMENT (verbatim). "
                  f"N'invente aucun autre nombre.\n\nDONNÉES:\n{src}")
        out.append(dict(cat="num-fidelity", prompt=prompt, checker="num_fidelity",
                        oracle=dict(must_contain=[str(m) for m in must], source=src)))
    return out


def build_extract():
    """12 extractions structurées -> JSON exact."""
    tasks = []
    socle = read_text("socle_run.log")
    # scores par modèle depuis le log
    scores = {}
    for l in socle.splitlines():
        m = re.match(r"== (\S+) : (\d+)/120 = (\d+\.\d+) en (\d+\.\d+) s", l)
        if m:
            scores[m.group(1)] = {"score": int(m.group(2)), "acc": float(m.group(3)),
                                  "duree_s": float(m.group(4))}
    if scores:
        exp = {k: scores[k] for k in sorted(scores)}
        tasks.append(("extrais les scores de chaque modèle en JSON "
                      "{modele: {score, acc, duree_s}} (acc et durée en nombres)",
                      window("socle_run.log", 12, 42), exp))
    # bench JSONs: pire catégorie, cats parfaites, cats < 0.5
    for name, model in [("bench_2xmerge.json", "lfm3-2xmerge"),
                        ("bench_fable51.json", "lfm3-fable51"),
                        ("bench_coder.json", "lfm3-coder"),
                        ("bench_voltron.json", "voltron")]:
        d = json.loads(read_text(name))
        bc = d["by_cat"]
        worst = min(bc, key=lambda k: bc[k]["acc"])
        tasks.append((f"catégorie avec la plus basse accuracy -> JSON {{\"cat\": ..., \"acc\": ...}}",
                      json.dumps(bc, ensure_ascii=False), {"cat": worst, "acc": bc[worst]["acc"]}))
        perfect = sorted([k for k, v in bc.items() if v["ok"] == v["n"]])
        tasks.append((f"liste TRIÉE des catégories à 100 % (ok == n) -> JSON {{\"parfaites\": [...]}}",
                      json.dumps(bc, ensure_ascii=False), {"parfaites": perfect}))
    # diag: fichier d'où vient l'AssertionError
    tasks.append(("quel fichier Python contient la fonction `load_column_parallel_weight` "
                  "qui échoue -> JSON {\"fichier\": \"<nom du fichier .py>\"}",
                  window("diag_lfm3-coder.log", 100, 109), {"fichier": "parameter.py"}))
    # msys: chemin erroné passé au --model
    tasks.append(("quel chemin Windows erroné a été passé à la place de /model -> "
                  "JSON {\"chemin\": \"...\"}",
                  window("boot_msys_fail.log", 24, 33), {"chemin": "C:/Program Files/Git/model"}))
    # configs: quantization_config présent ?
    quants = {}
    for name, model in [("cfg_voltron.json", "voltron"), ("cfg_2xmerge.json", "lfm3-2xmerge"),
                        ("cfg_coder.json", "lfm3-coder")]:
        quants[model] = "quantization_config" in read_text(name)
    block = "\n\n".join(f"--- {m} ---\n" + read_text(f) for f, m in
                        [("cfg_voltron.json", "voltron"), ("cfg_2xmerge.json", "lfm3-2xmerge"),
                         ("cfg_coder.json", "lfm3-coder")])
    tasks.append(("pour chaque config, indique si la clé quantization_config est présente -> "
                  "JSON {modele: true/false}", block, quants))
    out = []
    for label, src, exp in tasks:
        prompt = (f"{label}\n\nRéponds en JSON exact, sans texte autour.\n\nDONNÉES:\n{src}")
        out.append(dict(cat="fail-extract", prompt=prompt, checker="json_eq", oracle=exp))
    return out


def build_cfgdiff():
    """6 paires de configs -> clés de premier niveau divergentes.

    Chaque tâche porte aussi un oracle `report` : le harnais v2.1, sur échec du
    diff brut, fournit le diff CALCULÉ PAR OUTIL au modèle et lui fait rédiger
    le rapport (vrai flux agentique : calcul à l'outil, rédaction au modèle)."""
    pairs = [("cfg_voltron.json", "voltron", "cfg_2xmerge.json", "lfm3-2xmerge"),
             ("cfg_2xmerge.json", "lfm3-2xmerge", "cfg_coder.json", "lfm3-coder"),
             ("cfg_2xmerge.json", "lfm3-2xmerge", "cfg_fable51.json", "lfm3-fable51"),
             ("cfg_coder.json", "lfm3-coder", "cfg_voltron.json", "voltron"),
             ("cfg_fable51.json", "lfm3-fable51", "cfg_coder.json", "lfm3-coder"),
             ("cfg_voltron.json", "voltron", "cfg_fable51.json", "lfm3-fable51")]
    out = []
    for fa, na, fb, nb in pairs:
        a = json.loads(read_text(fa))
        b = json.loads(read_text(fb))
        keys = sorted(set(a) | set(b))
        diff = {}
        for k in keys:
            va, vb = a.get(k), b.get(k)
            if va != vb:
                diff[k] = [va, vb]
        block = (f"=== config {na} ===\n{json.dumps(a, indent=1, ensure_ascii=False)}\n\n"
                 f"=== config {nb} ===\n{json.dumps(b, indent=1, ensure_ascii=False)}")
        src = block
        prompt = (f"Compare les DEUX configs suivantes. Liste les clés de PREMIER niveau dont "
                  f"la valeur diffère entre {na} et {nb}.\n"
                  f"Réponds en JSON : {{\"<cle>\": [<valeur dans {na}>, <valeur dans {nb}>]}} "
                  f"pour chaque clé divergente (clé absente = null). JSON exact, rien d'autre.\n\n"
                  f"{block}")
        # diff-outil pour le pivot harnais : même contenu, forme ligne par ligne
        tool_lines = "\n".join(
            f"- {k}: {json.dumps(v[0], ensure_ascii=False)} ({na}) vs "
            f"{json.dumps(v[1], ensure_ascii=False)} ({nb})" for k, v in diff.items())
        report_prompt = (f"Un outil a comparé les configs {na} et {nb}. Voici son diff exact :\n\n"
                         f"{tool_lines}\n\n"
                         f"Rédige un rapport en français de 2 à 5 phrases qui cite CHAQUE clé "
                         f"divergente avec ses deux valeurs. Pas de clé absente du diff, "
                         f"pas de valeur inventée.")
        out.append(dict(cat="cfg-diff", prompt=prompt, checker="json_eq", oracle=diff,
                        report_prompt=report_prompt,
                        report_oracle=dict(diff=diff, source=src)))
    return out


def build_tasks():
    return build_classify() + build_fidelity() + build_extract() + build_cfgdiff()


# ---------------------------------------------------------------- runner (même trame que quality_bench)

def chat(url, model, prompt, timeout=120):
    payload = json.dumps({"model": model,
                          "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": 400, "temperature": 0.0}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    return d["choices"][0]["message"]["content"] or ""


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:5028")
    ap.add_argument("--model", default="voltron-1-mini")
    ap.add_argument("--label", required=True)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    tasks = build_tasks()
    if args.limit:
        tasks = tasks[:args.limit]
    results = []
    t_start = time.time()
    for i, t in enumerate(tasks):
        t0 = time.time()
        out, ok, detail, e = "", False, "appel en échec", None
        try:
            out = chat(args.url, args.model, t["prompt"])
            ok, detail = CHECKERS[t["checker"]](out, t["oracle"])
        except Exception as exc:  # pas `as e` : le del implicite délierait e
            out, ok, detail, e = "", False, f"appel en échec: {exc!r}", repr(exc)
        results.append(dict(i=i, cat=t["cat"], ok=ok, detail=detail, err=e,
                            out=out[:400], dt=round(time.time() - t0, 2)))
        print(f"[{i}/{len(tasks)}] {t['cat']:<13} {'OK ' if ok else 'FAIL'} {detail[:110]}", flush=True)

    cats = {}
    for r in results:
        c = cats.setdefault(r["cat"], {"n": 0, "ok": 0})
        c["n"] += 1
        c["ok"] += int(r["ok"])
    total = len(results)
    ok_total = sum(int(r["ok"]) for r in results)
    summary = {
        "label": args.label, "url": args.url, "model": args.model,
        "at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(time.time() - t_start, 1), "n": total, "ok": ok_total,
        "acc": round(ok_total / total, 4) if total else None,
        "by_cat": {k: {"n": v["n"], "ok": v["ok"], "acc": round(v["ok"] / v["n"], 4)}
                   for k, v in sorted(cats.items())},
        "results": results,
    }
    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(LOG_DIR, f"real_bench_{args.label}_{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print(f"\n== {args.label} : {ok_total}/{total} = {summary['acc']:.3f} en {summary['elapsed_s']} s")
    for k, v in summary["by_cat"].items():
        print(f"   {k:<13} {v['ok']}/{v['n']} = {v['acc']:.3f}")
    print(f"-> {path}")


if __name__ == "__main__":
    main()
