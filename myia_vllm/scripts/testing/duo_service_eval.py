#!/usr/bin/env python3
"""Duo at SERVICE level — the second-reader stage measured through the real chain.

The offline bench (duo_bench.py / duo_analyze.py) paired the two models task by
task and found that a gated cascade a->b reaches the oracle union's ceiling
(socle 93/120, real pack 32/40). That is ONE dry call per model. The service
runs something else: the local worker gets up to two directed repairs, then the
27B coordinator (expensive, on ai-01's production engine) takes everything the
worker could not close. The duo inserts between the two, so the questions are
the service's own:

  1. how many tasks does the caller see closed (svc_ok, the service gate), and
     how many are right against the bench oracle (bench_ok) ?
  2. how many coordinator calls does the duo save — the cost metric ?
  3. where b passes the service gate, is it right where c would have been ?
     A wrong b that passes the gate short-circuits c: the one risk.

Arms, same 40 tasks, same contracts as service_mode_eval.py, same engine, same
hub, one after the other:
  off          today's chain a -> c
  duo          a -> b -> c (b = frognano-4b through the fleet hub)
  duo-sans-c   DERIVED from `duo`, not replayed: the tasks returned by a or b

The patched server is loaded IN PROCESS (no second :5029). The adoption counter
and the job files point to a throwaway directory — a bench must not touch the
real usage — and Docker is forbidden: the live service stays the only master of
the engine, and a mute engine stops the arm.

Latency across arms is ORDER-CONFOUNDED: the second arm finds the coordinator's
prompts in the 27B prefix cache. Calls are counted, latency is reported.

Usage:
  python duo_service_eval.py --arms off,duo --out-dir D:/vllm-data/bench/duo_20261128
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import shutil
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import real_task_bench as rb  # noqa: E402
import service_mode_eval as sme  # noqa: E402

SERVER = os.environ.get("VOLTRON_SERVER_SRC") or os.path.join(HERE, "voltron_harness_server.py")
SERVICE_ENV = r"D:\vllm-data\bench\v2_service.env"  # what the launcher loads at start
KEY_FILE = r"D:\Dev\roo-extensions\.env"
KEY_VAR = "CLAUDISH_PROXY_KEY"
KINDS = ("engine", "duo", "coord")
ARMS = ("off", "duo")


# ---------------------------------------------------------------- key handling

def read_env_var(path, name):
    """Reads one variable out of a dotenv file. The value is returned, never printed."""
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(r"\s*%s\s*=\s*(\S+)\s*$" % re.escape(name), line)
            if m:
                return m.group(1).strip('"').strip("'")
    raise SystemExit("variable %s introuvable dans %s" % (name, path))


def read_env_file(path):
    out = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
            if m:
                out[m.group(1)] = m.group(2).strip('"').strip("'")
    return out


def hub_key():
    key = os.environ.get("ZAI_API_KEY") or read_env_var(KEY_FILE, KEY_VAR)
    if not key:
        raise SystemExit("cle client du hub absente (ZAI_API_KEY ou %s dans %s)"
                         % (KEY_VAR, KEY_FILE))
    return key


# ---------------------------------------------------------------- instrument

class Compteur:
    """The server's own `chat`, unchanged, counted and timed per reader."""

    def __init__(self, mod):
        self.mod, self.chat = mod, mod.chat
        self.reset()

    def reset(self):
        self.n = dict.fromkeys(KINDS, 0)
        self.s = dict.fromkeys(KINDS, 0.0)

    def kind(self, url, model):
        if url.rstrip("/") == self.mod.ENGINE_URL:
            return "engine"
        return "duo" if model == self.mod.DUO_MODEL else "coord"

    def __call__(self, url, model, messages, **kw):
        kind = self.kind(url, model)
        self.n[kind] += 1
        t0 = time.time()
        try:
            return self.chat(url, model, messages, **kw)
        finally:
            self.s[kind] += time.time() - t0


def load_server(svc_env, key):
    """The patched server, configured like the :5029 service (the launcher's env
    file), minus its counter and its job files."""
    spec = importlib.util.spec_from_file_location("duo_service_server", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # __name__ != __main__ -> pas de serveur
    mod.HUB_URL = svc_env["VOLTRON_HUB_URL"]
    mod.HUB_MODEL = svc_env["VOLTRON_HUB_MODEL"]
    mod.ENGINE_MODEL = svc_env["VOLTRON_ENGINE_MODEL"]
    mod.HUB_KEY = key
    mod.DUO_MODEL = ""
    scratch = tempfile.mkdtemp(prefix="duo_service_")
    mod.JOBS_DIR = os.path.join(scratch, "jobs")
    mod.USAGE_PATH = os.path.join(scratch, "usage.json")
    mod._docker_start = lambda: (False, "bench : docker interdit")
    counter = Compteur(mod)
    mod.chat = counter
    return mod, counter, scratch


# ---------------------------------------------------------------- arms

def run_arm(mod, counter, name, duo_model, tasks):
    """One arm = the synchronous path of /v1/task (`_run_sync`), task by task."""
    mod.DUO_MODEL = duo_model
    rows, why = [], ""
    t_arm = time.time()
    for i, t in enumerate(tasks):
        if not mod.engine_healthy(timeout=10):
            why = "moteur muet a la tache %d" % (i + 1)
            print("ARRET %s : %s — bras non mesurable au-dela" % (name, why), flush=True)
            break
        contract, ev = sme.to_contract(t)
        counter.reset()  # apres la sonde de vivacite : elle n'est pas un appel de tache
        t0 = time.time()
        r = mod._run_sync(copy.deepcopy(contract), "bench %s %d: " % (name, i))
        bench_ok, bench_detail = ev(r["answer"]) if r["answer"] else (False, "aucune reponse")
        rows.append(dict(i=i, cat=t["cat"], svc_ok=bool(r["ok"]), stage=r["stage"],
                         turns=r["turns"], bench_ok=bool(bench_ok),
                         bench_detail=bench_detail[:160], dt=round(time.time() - t0, 2),
                         calls=dict(counter.n),
                         call_s={k: round(v, 2) for k, v in counter.s.items()},
                         detail=r["detail"][:300], answer=r["answer"][:400]))
        print("[%2d/%d] %-12s svc=%-4s(%s,t%d) banc=%-4s %6.1fs appels e%d b%d c%d  %s" % (
            i + 1, len(tasks), t["cat"], "OK" if r["ok"] else "FAIL", r["stage"],
            r["turns"], "OK" if bench_ok else "FAIL", rows[-1]["dt"], counter.n["engine"],
            counter.n["duo"], counter.n["coord"],
            ("" if bench_ok else bench_detail[:60]).replace("\n", " ")), flush=True)
    return rows, dict(arret=why, duree_s=round(time.time() - t_arm, 1))


def summarize(name, rows):
    n = len(rows)
    if not n:
        return {"arm": name, "n": 0}
    stages, by_cat = {}, {}
    for r in rows:
        s = stages.setdefault(r["stage"], {"n": 0, "svc_ok": 0, "bench_ok": 0})
        s["n"] += 1
        s["svc_ok"] += int(r["svc_ok"])
        s["bench_ok"] += int(r["bench_ok"])
        c = by_cat.setdefault(r["cat"], {"n": 0, "svc_ok": 0, "bench_ok": 0,
                                         "duo": 0, "coord": 0})
        c["n"] += 1
        c["svc_ok"] += int(r["svc_ok"])
        c["bench_ok"] += int(r["bench_ok"])
        c["duo"] += r["calls"]["duo"]
        c["coord"] += r["calls"]["coord"]
    dts = sorted(r["dt"] for r in rows)
    return dict(
        arm=name, n=n,
        svc_ok=sum(r["svc_ok"] for r in rows),
        bench_ok=sum(r["bench_ok"] for r in rows),
        stages=stages,
        appels={k: sum(r["calls"][k] for r in rows) for k in KINDS},
        appels_s={k: round(sum(r["call_s"][k] for r in rows), 1) for k in KINDS},
        dt_s=dict(total=round(sum(dts), 1), median=round(statistics.median(dts), 2),
                  p90=round(dts[int(0.9 * (n - 1))], 2), max=dts[-1]),
        by_cat=by_cat)


def print_summary(s):
    print("\n== bras %s : service %d/%d | verite banc %d/%d" % (
        s["arm"], s["svc_ok"], s["n"], s["bench_ok"], s["n"]), flush=True)
    print("   etages      : " + "  ".join(
        "%s=%d (service %d, banc %d)" % (k, v["n"], v["svc_ok"], v["bench_ok"])
        for k, v in sorted(s["stages"].items())), flush=True)
    print("   appels      : moteur %d, second lecteur %d, coordinateur %d" % (
        s["appels"]["engine"], s["appels"]["duo"], s["appels"]["coord"]), flush=True)
    print("   temps d'appel: moteur %.0f s, second lecteur %.0f s, coordinateur %.0f s" % (
        s["appels_s"]["engine"], s["appels_s"]["duo"], s["appels_s"]["coord"]), flush=True)
    print("   latence     : total %.0f s, mediane %.1f s, p90 %.1f s, max %.1f s" % (
        s["dt_s"]["total"], s["dt_s"]["median"], s["dt_s"]["p90"], s["dt_s"]["max"]),
        flush=True)
    for k, v in sorted(s["by_cat"].items()):
        print("   %-12s service %d/%d  banc %d/%d  (b %d, c %d)" % (
            k, v["svc_ok"], v["n"], v["bench_ok"], v["n"], v["duo"], v["coord"]), flush=True)


# ---------------------------------------------------------------- cross

def croise(off, duo):
    """Task by task: what the duo changes, and what b did wherever it replaced c."""
    out = dict(
        n=len(off),
        banc_gagne=[r["i"] for o, r in zip(off, duo) if r["bench_ok"] and not o["bench_ok"]],
        banc_perdu=[r["i"] for o, r in zip(off, duo) if o["bench_ok"] and not r["bench_ok"]],
        service_gagne=[r["i"] for o, r in zip(off, duo) if r["svc_ok"] and not o["svc_ok"]],
        service_perdu=[r["i"] for o, r in zip(off, duo) if o["svc_ok"] and not r["svc_ok"]],
        coord_economises=sum(o["calls"]["coord"] - r["calls"]["coord"]
                            for o, r in zip(off, duo)))
    table, ids, hors = {}, {}, []
    for o, r in zip(off, duo):
        if r["stage"] != "b":
            continue
        if o["stage"] != "c":  # le worker avait passe en `off` : c n'a pas ete remplace
            hors.append(r["i"])
            continue
        k = "b_%s_c_%s" % ("juste" if r["bench_ok"] else "faux",
                           "juste" if o["bench_ok"] else "faux")
        table[k] = table.get(k, 0) + 1
        ids.setdefault(k, []).append(r["i"])
    out["b_remplace_c"] = table
    out["b_remplace_c_ids"] = ids
    out["b_sans_c_en_face"] = hors
    return out


def derive_sans_c(duo):
    """`duo` without its coordinator: the tasks a or b returned. DERIVED, not replayed."""
    garde = [r for r in duo if r["stage"] in ("a", "b")]
    return dict(n=len(duo), taches_rentrees=len(garde),
                svc_ok=sum(r["svc_ok"] for r in garde),
                bench_ok=sum(r["bench_ok"] for r in garde),
                non_traitees=len(duo) - len(garde))


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="off,duo")
    ap.add_argument("--duo-model", default="frognano-4b")
    ap.add_argument("--families", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arms if a not in ARMS]
    if unknown or not arms:
        ap.error("--arms : attendu une liste de %s, recu %s" % ("/".join(ARMS), args.arms))

    svc_env = read_env_file(SERVICE_ENV)
    key = hub_key()
    mod, counter, scratch = load_server(svc_env, key)
    try:
        tasks = rb.build_tasks()
        if args.families:
            fams = set(args.families.split(","))
            tasks = [t for t in tasks if t["cat"] in fams]
        if args.limit:
            tasks = tasks[:args.limit]
        with open(SERVER, "rb") as f:
            server_sha = hashlib.sha256(f.read()).hexdigest()[:12]
        corpus_sha = hashlib.sha256(
            json.dumps(tasks, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]

        print("serveur %s | moteur %s | second lecteur %s | coordinateur %s | hub %s" % (
            server_sha, mod.ENGINE_MODEL, args.duo_model, mod.HUB_MODEL, mod.HUB_URL),
            flush=True)
        print("cle hub sha256[:12]=%s | banc %d taches, corpus %s" % (
            hashlib.sha256(key.encode()).hexdigest()[:12], len(tasks), corpus_sha), flush=True)

        out = dict(at=datetime.now(timezone.utc).isoformat(), server_sha=server_sha,
                   corpus_sha=corpus_sha, engine_model=mod.ENGINE_MODEL,
                   duo_model=args.duo_model, coord_model=mod.HUB_MODEL,
                   arms={})
        for arm in arms:
            duo_model = args.duo_model if arm == "duo" else ""
            print("\n== bras %s (second lecteur : %s)" % (
                arm, duo_model or "absent"), flush=True)
            rows, etat = run_arm(mod, counter, arm, duo_model, tasks)
            s = summarize(arm, rows)
            out["arms"][arm] = dict(summary=s, etat=etat, rows=rows)
            print_summary(s)
            if etat["arret"]:
                print("ARRET : %s" % etat["arret"], flush=True)

        if all(a in out["arms"] for a in ARMS) and all(
                len(out["arms"][a]["rows"]) == len(tasks) for a in ARMS):
            off, duo = out["arms"]["off"]["rows"], out["arms"]["duo"]["rows"]
            out["croise"] = croise(off, duo)
            out["duo_sans_c"] = derive_sans_c(duo)
            print("\n== croise off -> duo (tache a tache)", flush=True)
            print("   verite banc : +%d (taches %s)  -%d (taches %s)" % (
                len(out["croise"]["banc_gagne"]), out["croise"]["banc_gagne"],
                len(out["croise"]["banc_perdu"]), out["croise"]["banc_perdu"]), flush=True)
            print("   service     : +%d (taches %s)  -%d (taches %s)" % (
                len(out["croise"]["service_gagne"]), out["croise"]["service_gagne"],
                len(out["croise"]["service_perdu"]), out["croise"]["service_perdu"]),
                flush=True)
            print("   appels de coordinateur evites : %d" % out["croise"]["coord_economises"],
                  flush=True)
            print("   la ou b a remplace c (verite banc) :", flush=True)
            for k in sorted(out["croise"]["b_remplace_c"]):
                print("     %-16s %2d  taches %s" % (
                    k, out["croise"]["b_remplace_c"][k], out["croise"]["b_remplace_c_ids"][k]),
                    flush=True)
            d = out["duo_sans_c"]
            print("   duo sans coordinateur (DERIVE, non rejoue) : %d/%d taches rentrees, "
                  "service %d, verite banc %d, non traitees %d" % (
                      d["taches_rentrees"], d["n"], d["svc_ok"], d["bench_ok"],
                      d["non_traitees"]), flush=True)

        os.makedirs(args.out_dir, exist_ok=True)
        path = os.path.join(args.out_dir, "duo_service_%s.json" % datetime.now(
            timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print("\nJSON: %s" % path, flush=True)
    finally:
        mod.DUO_MODEL = ""
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    main()
