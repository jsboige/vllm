#!/usr/bin/env python3
"""gateway_probe.py -- sonde du transport des dashboards RooSync (siege po-2028:vllm).

Mesure, appel par appel, OU le temps se perd dans l'echange MCP :
`initialize`, `tools/call`, puis lecture du corps. Un `tools/call` qui ne
repond jamais pendant qu'`initialize` repond en < 200 ms designe la
passerelle, pas l'archive -- c'est la distinction qui a manque le 26/11
(l'organe rendait exit 1 sur des archives en realite intactes).

Historique : la premiere version vivait dans
`D:\\dev\\wt-po2028-vllm-599\\.tmp\\` et a disparu avec le retrait de ce
worktree (acteur non identifie, 26/11). Cette version est commitee dans le
depot (myia_vllm/scripts/monitoring/) et doublee hors depot pour rester
utilisable sans checkout :

    D:\\vllm-data\\bench\\seat-po2028\\gateway_probe.py

Le transport n'est pas recopie : il est importe de l'organe partage
(`detect-approval-stalls.py`, fonction `call_dashboard_tool`), pour que la
sonde mesure exactement le chemin que l'organe emprunte.

Sortie : une ligne JSON par appel + une synthese + `exit=` (0 toujours :
une sonde qui echoue n'est pas une sonde en panne).
"""
import argparse
import importlib.util
import json
import os
import sys
import time

# surchargeable par ROO_EXTENSIONS_DIAG (defaut : chemin de ce siege)
DIAG = (os.environ.get("ROO_EXTENSIONS_DIAG")
        or r"D:\dev\roo-extensions\scripts\diagnostic")
ENV_FILE = os.path.join(os.path.expanduser("~"), ".roo-state-manager", "stall-detector.env")

# Lecture d'un appel : ok=true = sert ; fail=tools-call/... = MUET (le defaut
# mesure) ; ok=false avec fail='-' = la passerelle a repondu et le tool a
# refuse (archive absente, store-absent) -- ce n'est pas un muet.
#
# Archives de reference, choisies parce qu'elles ont ete MUETTES puis SERVIES
# (elles ne distinguent donc pas "archive perdue" de "passerelle qui dort").
CASES = [
    ("CoursIA-3", "workspace-CoursIA-3-2026-11-25T16-27-47.md", "CONTROLE jamais muet"),
    ("CoursIA-2", "workspace-CoursIA-2-2026-11-26T01-56-46.md", "muet 2/2 a 50 s, lu 607 ms en local"),
    ("CoursIA-2", "workspace-CoursIA-2-2026-11-26T00-46-14.md", "muet 1/1 a 50 s"),
    ("CoursIA-2", None, "CONTROLE listing (metadonnees seules)"),
]


def load_transport():
    spec = importlib.util.spec_from_file_location(
        "detect_approval_stalls", os.path.join(DIAG, "detect-approval-stalls.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.call_dashboard_tool


def load_proxy():
    """(url, bearer). Le bearer n'est jamais affiche ni journalise."""
    url, bearer = None, None
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip().strip('"').strip("'")
                if key in ("MCP_PROXY_URL", "MCP_PROXY_BASE_URL"):
                    url = url or val
                elif key == "MCP_PROXY_BEARER":
                    bearer = bearer or val
    url = url or os.environ.get("MCP_PROXY_URL") or os.environ.get("MCP_PROXY_BASE_URL")
    bearer = bearer or os.environ.get("MCP_PROXY_BEARER")
    return (url or "https://mcp-tools.myia.io"), bearer


def args_for(workspace, archive_file=None):
    a = {"action": "read_archive", "type": "workspace", "workspace": workspace}
    if archive_file:
        a["archiveFile"] = archive_file
    return a


def one(call_tool, url, bearer, ws, fname, label, timeout):
    tel = {}
    t0 = time.monotonic()
    result = None
    try:
        result = call_tool(args_for(ws, fname), url, bearer,
                           timeout=timeout, client="gateway-probe", telemetry=tel)
    except Exception as exc:  # la sonde rapporte, elle ne meurt pas
        tel.setdefault("failure", {})["exception"] = type(exc).__name__
    elapsed = round((time.monotonic() - t0) * 1000.0, 1)
    phases = {}
    for name, entry in (tel.get("phases") or {}).items():
        phases[name] = entry.get("ms")
    if tel.get("phases", {}).get("tools-call", {}).get("bytes"):
        phases["bytes"] = tel["phases"]["tools-call"]["bytes"]
    fail = tel.get("failure") or {}
    fail_txt = "-"
    if fail:
        fail_txt = "%s/%s/%s" % (fail.get("phase"), fail.get("exception"),
                                 round(float(fail.get("elapsed_ms") or 0.0), 1))
    ok = result is not None
    return {"label": label, "ws": ws, "file": fname or "-", "ok": ok, "ms": elapsed,
            "phases": phases, "fail": fail_txt}


def main():
    ap = argparse.ArgumentParser(description="Sonde du transport des dashboards RooSync")
    ap.add_argument("--rounds", type=int, default=2, help="passes sur le jeu de cas (defaut 2)")
    ap.add_argument("--timeout", type=float, default=30.0, help="delai par appel, s (defaut 30)")
    ap.add_argument("--ws", help="restreindre a un workspace")
    ap.add_argument("--file", help="lire une archive precise (avec --ws)")
    ap.add_argument("--label", default="cible ad hoc")
    opts = ap.parse_args()

    call_tool = load_transport()
    url, bearer = load_proxy()
    print("gateway: %s | bearer charged: %s" % (url, bool(bearer)))
    if not bearer:
        print("ERREUR: aucun bearer trouve (%s) ; rien ne peut etre mesure." % ENV_FILE)
        print("exit=1")
        return 1

    cases = CASES
    if opts.ws:
        cases = [(opts.ws, opts.file, opts.label)]

    results = []
    for rnd in range(1, opts.rounds + 1):
        print("--- round %d ---" % rnd)
        consecutive_fail = 0
        for ws, fname, label in cases:
            row = one(call_tool, url, bearer, ws, fname, label, opts.timeout)
            print(json.dumps(row, ensure_ascii=False))
            results.append(row)
            consecutive_fail = 0 if row["ok"] else consecutive_fail + 1
            if consecutive_fail >= 2:
                print("STOP adaptatif : 2 echecs consecutifs (passerelle qui ne repond plus)")
                break

    oks = [r for r in results if r["ok"]]
    fails = [r for r in results if not r["ok"]]
    print("--- synthese ---")
    print("appels=%d ok=%d echecs=%d" % (len(results), len(oks), len(fails)))
    if oks:
        ms = sorted(r["ms"] for r in oks)
        print("ok ms: min=%.1f p50=%.1f max=%.1f" % (ms[0], ms[len(ms) // 2], ms[-1]))
    print("echecs: %s" % (["%s/%s %s" % (r["ws"], r["file"], r["fail"]) for r in fails] or "[]"))
    print("exit=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
