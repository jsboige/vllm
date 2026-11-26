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

Les archives de reference ne sont PAS figees : chaque run lit le listing du
workspace et prend ses deux archives les plus recentes. Une archive condensee
n'a plus de corps et rend `refus`, pas `muet` : figee dans le code, elle
devenait un controle muet a la place du cas discriminant. FALLBACK ne sert
que si le listing lui-meme ne repond pas.

Cinq lectures par appel :
  - `sert`   : le tool a repondu (resultat MCP) ;
  - `refus`  : la passerelle a repondu et le tool a refuse (isError : archive
               absente, store-absent). Ce n'est PAS un muet ;
  - `muet`   : echec de transport AVEC sa phase (`tools-call`, `lecture`...) ;
  - `echec`  : aucun resultat et aucune phase en faute -- non servi, cause
               non mesuree. Ne se lit JAMAIS comme un refus ;
  - `erreur` : le transport a leve une exception (son contrat dit non).

Sortie : une ligne JSON par appel + une synthese classee + `exit=` (0 sauf
absence de bearer : une sonde qui echoue n'est pas une sonde en panne).
"""
import argparse
import importlib.util
import json
import os
import re
import sys
import time

# surchargeable par ROO_EXTENSIONS_DIAG (defaut : chemin de ce siege)
DIAG = (os.environ.get("ROO_EXTENSIONS_DIAG")
        or r"D:\dev\roo-extensions\scripts\diagnostic")
ENV_FILE = os.path.join(os.path.expanduser("~"), ".roo-state-manager", "stall-detector.env")

# Repli seulement : noms verifies le 26/11, utilises si le listing ne repond pas.
FALLBACK = [
    ("CoursIA-3", "workspace-CoursIA-3-2026-11-25T16-27-47.md"),
    ("CoursIA-2", "workspace-CoursIA-2-2026-11-26T01-56-46.md"),
]

CLASSES = ("sert", "muet", "refus", "echec", "erreur")
STAMP_RE = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})")
SUFFIX_RE = re.compile(r"_(\d+)\.md$")


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


def result_text(result):
    """Texte concatene d'un resultat MCP (le listing en a besoin)."""
    if not isinstance(result, dict):
        return ""
    return "".join(item.get("text", "") for item in result.get("content", [])
                   if isinstance(item, dict))


def summarize(tel):
    """Phases lisibles, tolerant a une telemetrie malformee.

    Le contrat de la sonde est de ne jamais mourir : une entree de phase qui
    n'est pas un dict (ou un `phases` qui n'en est pas un) doit couter la
    colonne, pas le run. Les octets vivent sur la phase `lecture` (forme
    reelle de l'organe), pas sur `tools-call`.
    """
    out = {}
    if not isinstance(tel, dict):
        return out
    phases = tel.get("phases")
    if not isinstance(phases, dict):
        return out
    for name, entry in phases.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("ms") is not None:
            out[name] = entry["ms"]
        if entry.get("bytes") is not None:
            out["bytes"] = entry["bytes"]
    return out


def one(call_tool, url, bearer, ws, fname, label, timeout):
    """Un appel mesure. Rend (row, result) ; row est la seule chose imprimee.

    `return_rejected_text=True` : un refus serveur revient comme texte (str)
    au lieu de None, pour qu'un refus ne se confonde jamais avec un echec de
    transport -- c'est exactement la confusion que la sonde existe pour lever.
    """
    tel = {}
    t0 = time.monotonic()
    result = None
    raised = None
    try:
        result = call_tool(args_for(ws, fname), url, bearer,
                           timeout=timeout, client="gateway-probe",
                           return_rejected_text=True, telemetry=tel)
    except Exception as exc:  # la sonde rapporte, elle ne meurt pas
        raised = type(exc).__name__
    elapsed = round((time.monotonic() - t0) * 1000.0, 1)
    fail = tel.get("failure") if isinstance(tel, dict) else None
    fail = fail if isinstance(fail, dict) else {}
    fail_txt = "-"
    if fail:
        fail_txt = "%s/%s/%s" % (fail.get("phase"), fail.get("exception"),
                                 round(float(fail.get("elapsed_ms") or 0.0), 1))
    if raised:
        cls, fail_txt = "erreur", "exception levee/%s/%s" % (raised, elapsed)
    elif isinstance(result, dict):
        cls = "sert"
    elif isinstance(result, str):
        cls = "refus"
    elif fail:
        cls = "muet"
    else:
        cls = "echec"
    row = {"label": label, "ws": ws, "file": fname or "-", "ok": cls == "sert", "cls": cls,
           "ms": elapsed, "phases": summarize(tel), "fail": fail_txt}
    return row, result


def pick_archives(text, ws, count=2):
    """Les `count` archives les plus recentes d'un listing.

    On trie sur l'horodatage porte par le NOM, jamais sur le nom entier : un
    suffixe de collision (`...T01-56-46_2.md`) fausse le tri par nom (ordinal
    ici, culturel en PowerShell). A horodatage egal, le suffixe le plus haut
    a ete ecrit en second.
    """
    pat = re.compile(r"workspace-" + re.escape(ws)
                     + r"-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}(?:_\d+)?\.md")
    names = sorted(set(pat.findall(text)))
    if not names:
        return []

    def key(name):
        stamp = STAMP_RE.search(name)
        suffix = SUFFIX_RE.search(name)
        return (stamp.group(1) if stamp else "", int(suffix.group(1)) if suffix else -1)

    names.sort(key=key, reverse=True)
    return names[:count]


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

    results = []

    if opts.ws:
        workspaces = [opts.ws]
    else:
        workspaces = []
        for ws, _ in FALLBACK:
            if ws not in workspaces:
                workspaces.append(ws)

    # References resolues a chaque run : listing mesure, puis 2 archives les plus
    # recentes. Le listing lui-meme est une mesure (metadonnees, corps non lu).
    refs = {}
    static_used = []
    for ws in workspaces:
        if opts.file:
            refs[ws] = [(opts.file, opts.label)]
            continue
        row, result = one(call_tool, url, bearer, ws, None, "listing (%s)" % ws, opts.timeout)
        print(json.dumps(row, ensure_ascii=False))
        results.append(row)
        names = pick_archives(result_text(result), ws) if row["cls"] == "sert" else []
        if names:
            refs[ws] = [(n, "archive du listing %d" % i) for i, n in enumerate(names, 1)]
        else:
            refs[ws] = [(f, "REPLI statique") for w, f in FALLBACK if w == ws]
            static_used.append(ws)
            print("AVERTISSEMENT: listing %s inexploitable (%s) -> repli statique %s"
                  % (ws, row["cls"], [f for f, _ in refs[ws]] or "aucun"))

    stop = False
    for rnd in range(1, opts.rounds + 1):
        print("--- round %d ---" % rnd)
        consecutive_fail = 0
        for ws in workspaces:
            for fname, label in refs[ws]:
                row, _ = one(call_tool, url, bearer, ws, fname, label, opts.timeout)
                print(json.dumps(row, ensure_ascii=False))
                results.append(row)
                consecutive_fail = 0 if row["ok"] else consecutive_fail + 1
                if consecutive_fail >= 2:
                    print("STOP adaptatif : 2 echecs consecutifs (passerelle qui ne repond plus)")
                    stop = True
                    break
            if stop:
                break
        if stop:
            break

    n = {c: sum(1 for r in results if r["cls"] == c) for c in CLASSES}
    oks = [r for r in results if r["ok"]]
    dead = n["muet"] + n["echec"] + n["erreur"]
    print("--- synthese ---")
    print("appels=%d sert=%d muet=%d refus=%d echec=%d erreur=%d"
          % (len(results), n["sert"], n["muet"], n["refus"], n["echec"], n["erreur"]))
    if oks:
        ms = sorted(r["ms"] for r in oks)
        print("ok ms: min=%.1f p50=%.1f max=%.1f" % (ms[0], ms[len(ms) // 2], ms[-1]))
    for cls in ("muet", "echec", "erreur"):
        if n[cls]:
            print("%s: %s" % (cls.upper(), ["%s/%s %s" % (r["ws"], r["file"], r["fail"])
                                           for r in results if r["cls"] == cls]))
    if n["refus"]:
        print("refus (pas des muets): %s" % ["%s/%s" % (r["ws"], r["file"])
                                            for r in results if r["cls"] == "refus"])
    if static_used:
        print("ATTENTION: jeu de reference statique sur %s -- la sonde perd sa "
              "discrimination si ces archives sont condensees" % static_used)
    if dead and oks:
        print("VERDICT: intermittent -- %d servi(s), %d non servi(s)" % (len(oks), dead))
    elif dead:
        print("VERDICT: le transport ne sert rien -- muet confirme")
    elif oks:
        print("VERDICT: sert")
    else:
        print("VERDICT: aucun appel abouti et aucun muet (que des refus) -- verifier le jeu de cas")
    print("exit=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
