#!/usr/bin/env python3
"""W1 — Réserves par PR (BG workflow, spec v1 : myia_vllm/docs/frognano-bg-workflows.md §5).

Consommateur : coordinateur `myia-ai-01:CoursIA`. Livrable : index à champs fixes, une ligne
par point de réserve, **citation verbatim + provenance**, aucune décision de levée.

Architecture (spec §2) : driver script, pas de preset sk-agent.
  snapshot REST bulk  ->  horde `extracteur-fiche` (mini, HTTP direct :5003)
                      ->  portes mécaniques (driver, jamais un modèle)
                      ->  markdown à champs fixes

Les portes (spec §4) :
  1. schéma    : JSON parsable, clés exactes
  2. verbatim  : toute valeur chaîne est une sous-chaîne de la source fournie
  3. rappel    : mesuré et PUBLIÉ, jamais exigé (les absents sont comptés contre le corpus)
  4. recompte  : tous les comptes sont calculés ici ; le modèle ne compte rien

Règle mesurée le 05/11 (vigie po-2025) : le mini est fiable sur un motif unique et complet,
aveugle sur un préfixe à occurrences multiples. ⇒ **la sélection d'items reste au driver**
(`grep`/Python) ; le mini ne fait que copier les champs d'un item **déjà isolé**.

Aucune écriture GitHub (interdit §5). Lecture seule via `gh api` (bulk, paginé).

Usage :
  python w1_reserves.py --prs 24599,24640,24457 --out livrable.md
  python w1_reserves.py --prs 24599 --self-test     # portes, hors réseau
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_REPO = "jsboige/CoursIA"
ENGINE = "http://localhost:5003"
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
LANE_MARKERS = ("myia-", "[Hermes]", "[RooSync]", "[OVERRIDE]")
RESERVE_STATES = {"CHANGES_REQUESTED"}
HERMES_MARKERS = ("COMMENT_WITH_CONCERNS",)
GLYPHS = ("🟡", "🔴")

# Champs que le mini doit recopier (forme fixe, jamais un statut).
FICHE_KEYS = ["pr", "comment_id", "auteur", "date", "extrait"]


# --------------------------------------------------------------------------- modèle
@dataclass
class Candidate:
    pr: int
    kind: str                 # review | comment | inline
    comment_id: str
    auteur: str
    date: str
    body: str
    url: str = ""
    path: str = ""            # inline uniquement
    line: int | None = None
    fiche: dict = field(default_factory=dict)
    gate: dict = field(default_factory=dict)
    verdict: str = "?"          # n/m jetons cités encore présents — fait brut
    verdict_reason: str = ""
    where_head: str = ""        # fichier(s) @ sha où ils sont présents
    body_pr: str = ""           # jetons cités dans la description de PR (vs tête)
    lane_reply: str = ""
    lane_body: str = ""
    lifted: str = ""


# --------------------------------------------------------------------------- io
def sh(args: list[str], timeout: int = 120) -> str:
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:4])}… rc={r.returncode}: {r.stderr.strip()[:300]}")
    return r.stdout


def gh_api(path: str, paginate: bool = True) -> object:
    """Une requête REST. `--paginate` UNIQUEMENT sur les listes (jamais --jq) : sur un objet
    unique, `gh api --paginate` sort en erreur (mesuré 05/11)."""
    out = sh(["gh", "api", path] + (["--paginate"] if paginate else []))
    dec = json.JSONDecoder()
    items, idx, out = [], 0, out.strip()
    while idx < len(out):
        while idx < len(out) and out[idx] in " \n\r\t":
            idx += 1
        if idx >= len(out):
            break
        obj, idx = dec.raw_decode(out, idx)
        items.extend(obj if isinstance(obj, list) else [obj])
    return items


def engine_key() -> str:
    if not ENV_FILE.exists():
        raise SystemExit(f".env introuvable : {ENV_FILE}")
    for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^\s*VLLM_API_KEY_MINI\s*=\s*(.+)$", line)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    raise SystemExit("VLLM_API_KEY_MINI absent de .env")


def engine(prompt: str, key: str, model: str = "frognano-4b", max_tokens: int = 400,
           retries: int = 2) -> tuple[str, dict]:
    body = json.dumps({"model": model, "temperature": 0, "max_tokens": max_tokens,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    last = ""
    for attempt in range(retries + 1):
        req = urllib.request.Request(f"{ENGINE}/v1/chat/completions", data=body,
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {key}"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                payload = json.loads(r.read())
                return payload["choices"][0]["message"]["content"], payload.get("usage", {})
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as e:
            last = str(e)[:200]
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"moteur indisponible : {last}")


def head_file(repo: str, path: str, sha: str, cache: dict) -> str | None:
    """Contenu du fichier À LA TÊTE, octets exacts (base64 décodé). None = illisible."""
    k = (path, sha)
    if k in cache:
        return cache[k]
    content = None
    try:
        meta = gh_api(f"/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={sha}", paginate=False)
        if isinstance(meta, list):
            meta = meta[0]
        enc = meta.get("content") or ""
        if enc:
            content = base64.b64decode(enc).decode("utf-8", errors="replace")
        else:  # > 1 Mo : le JSON du contents n'inline pas le corps → blob par son sha
            blob = gh_api(f"/repos/{repo}/git/blobs/{meta['sha']}", paginate=False)
            content = base64.b64decode(blob["content"]).decode("utf-8", errors="replace")
    except Exception:
        content = None
    cache[k] = content
    return content


# --------------------------------------------------------------------------- sélection
def quoted_tokens(body: str, limit: int = 12) -> list[str]:
    toks = re.findall(r"`([^`\n]{3,80})`", body)
    seen, out = set(), []
    for t in toks:
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out[:limit]


def file_refs(body: str, limit: int = 6) -> list[str]:
    refs = re.findall(r"\b([\w./-]+\.(?:py|ipynb|md|yml|yaml|json|lean|txt|ps1|sh))(?::\d+)?", body)
    seen, out = set(), []
    for r in refs:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out[:limit]


REVIEW_BOTS = ("clusterManager-Myia",)          # personas NanoClaw / Hermes
OVERRIDE_MARKERS = ("[OVERRIDE]", "[TRANSLATION-OVERRIDE]")


def _glyph_points(body: str) -> list[str]:
    """Nit 🟡/🔴 = une ligne du corps de review. Sélection faite ICI (jamais par le mini)."""
    pts = []
    for line in body.splitlines():
        s = line.strip()
        if s and any(g in s for g in GLYPHS) and len(s) > 25:
            pts.append(s.lstrip("-*• ").strip())
    return pts


def collect(repo: str, pr: int) -> list[Candidate]:
    """Détection calée sur la forme MESURÉE le 05/11 (le lot réel ne ressemble pas à la prose) :
    la réserve est une **review `COMMENTED` d'un persona** (LGTM ou CONCERNS), levée par un
    `[OVERRIDE]` postérieur d'une lane `myia-*`. Les points sont les lignes 🟡/🔴 du corps."""
    pull = gh_api(f"/repos/{repo}/pulls/{pr}")
    if isinstance(pull, list):
        pull = pull[0]
    reviews = gh_api(f"/repos/{repo}/pulls/{pr}/reviews?per_page=100")
    comments = gh_api(f"/repos/{repo}/issues/{pr}/comments?per_page=100")
    inline = gh_api(f"/repos/{repo}/pulls/{pr}/comments?per_page=100")

    overrides = [(c.get("created_at") or "", c.get("id")) for c in comments
                 if any(m in (c.get("body") or "") for m in OVERRIDE_MARKERS)
                 and (c.get("user", {}).get("login", "").startswith("myia-")
                      or "lane" in (c.get("body") or "").lower())]
    actions = sorted(((c.get("created_at") or "", c.get("id"), c.get("body") or "") for c in comments
                      if "[ACTION]" in (c.get("body") or "")), key=lambda x: x[0])

    cands: list[Candidate] = []

    for rv in reviews:
        author = rv.get("user", {}).get("login", "?")
        if author not in REVIEW_BOTS:
            continue
        at = rv.get("submitted_at") or rv.get("created_at") or ""
        body = rv.get("body") or ""
        title = "CONCERNS" if "CONCERNS" in body.upper() else ("LGTM" if "LGTM" in body.upper() else "?")
        pts = _glyph_points(body) or [body[:600]]
        for i, pt in enumerate(pts, 1):
            c = Candidate(pr=pr, kind=f"review:{title}", comment_id=f"review:{rv.get('id')}#p{i}",
                          auteur=author, date=at, body=pt, url=rv.get("html_url", ""))
            lift = next((o for o in overrides if o[0] > at), None)
            c.lifted = f"LEVÉE {lift[0][:16]} (comment {lift[1]})" if lift else ""
            reply = next((a for a in actions if a[0] > at), None)
            if reply:
                c.lane_reply = f"{reply[1]}, {reply[0][:16]}"
                c.lane_body = reply[2]
            cands.append(c)

    for c in inline:
        body = c.get("body") or ""
        if len(body.strip()) < 20:
            continue
        cand = Candidate(pr=pr, kind="inline", comment_id=f"inline:{c.get('id')}",
                         auteur=c.get("user", {}).get("login", "?"),
                         date=c.get("created_at", ""), body=body,
                         url=c.get("html_url", ""), path=c.get("path", ""),
                         line=c.get("line") or c.get("original_line"))
        lift = next((o for o in overrides if o[0] > cand.date), None)
        cand.lifted = f"LEVÉE {lift[0][:16]} (comment {lift[1]})" if lift else ""
        cands.append(cand)
    return cands


# --------------------------------------------------------------------------- portes
EXTRAIT_LEN = 160   # longueur citée : mesuré 05/11, au-delà le mini altère (3/14 rejets à 600)


def gate(c: Candidate, reply: dict | None) -> dict:
    """Portes 1+2 sur la fiche du mini. Retourne le rapport de portes."""
    src = json.dumps({"pr": c.pr, "comment_id": c.comment_id, "auteur": c.auteur,
                      "date": c.date, "extrait": c.body[:EXTRAIT_LEN]}, ensure_ascii=False)
    rep = {"schema": False, "verbatim": 0, "verbatim_total": 0, "missing": []}
    raw = (reply or {}).get("raw", "")
    if not raw:
        return rep
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return rep
    try:
        fiche = json.loads(m.group(0))
    except json.JSONDecodeError:
        return rep
    rep["schema"] = sorted(fiche.keys()) == sorted(FICHE_KEYS)
    if not rep["schema"]:
        return rep
    for k in FICHE_KEYS:
        v = str(fiche.get(k, ""))
        rep["verbatim_total"] += 1
        if v and v in src:
            rep["verbatim"] += 1
        else:
            rep["missing"].append(k)
    return rep


def pull_files(repo: str, pr: int, limit: int = 8) -> list[str]:
    """Fichiers changés par la PR — corpus de la tête quand le point ne nomme aucun chemin."""
    try:
        files = gh_api(f"/repos/{repo}/pulls/{pr}/files?per_page=100")
    except Exception:
        return []
    out = [f["filename"] for f in files if f.get("status") != "removed"]
    return out[:limit]


def mechanical_verdict(c: Candidate, repo: str, sha: str, cache: dict,
                       fallback: list[str] | None = None,
                       pr_body: str = "") -> tuple[str, str, str, str]:
    """Colonnes purement FACTUELLES — aucune polarité supposée.

    Mesuré le 05/11 sur 3 PRs : un même lot de réserves cite tantôt le texte DU DÉFAUT
    (« le kernelspec est inchangé `coursia-ml-training` »), tantôt la PREUVE QUE C'EST BON
    (« `csharp_sha` reproduits byte-exact »). « Jeton encore présent à la tête » ne prouve
    donc rien dans un sens ni dans l'autre : en tirer TRAITÉ / NON TRAITÉ produit des faux
    drapeaux dans les deux sens (mesuré : 5 alertes toutes fausses sur #24457, 4 sur
    #24640). Le BG livre le fait et l'emplacement ; la lane arbitre.

    Retourne (n_presents, preuve_detaillee, ou_detail).
    """
    toks = quoted_tokens(c.body)
    paths = (file_refs(c.body) or ([c.path] if c.path else []) or (fallback or []))[:8]
    where: dict[str, list[str]] = {}
    checked = 0
    for p in paths:
        blob = head_file(repo, p, sha, cache)
        if blob is None:
            continue
        checked += 1
        for t in toks:
            if t in blob:
                where.setdefault(t, []).append(p)
    found = sorted(where)

    # Colonne demandée par ai-01:CoursIA (#24599 : « les carnets étaient corrigés mais le
    # body citait encore l'ancien run ») — c'est la DESCRIPTION DE LA PR, pas le texte du
    # commentaire. Le fait utile est le CROISEMENT : jeton encore dans la description alors
    # qu'il a disparu de la tête = description périmée.
    in_body = [t for t in toks if pr_body and t in pr_body]
    stale = [t for t in in_body if t not in where]
    body_col = (f"{len(in_body)}/{len(toks)} jeton(s) dans le body de PR, "
                f"dont {len(stale)} absent(s) de la tête"
                + (f" ; ex. `{max(stale, key=len)[:60]}`" if stale else "")
                if toks else "—")

    if not toks:
        return "—", "aucun jeton cité : rien de vérifiable mécaniquement", "—", body_col
    if not checked:
        return "?", "aucun fichier de la tête lisible pour ce point", "—", body_col

    n = f"{len(found)}/{len(toks)}"
    # Le jeton le plus long est le plus discriminant (un identifiant court du body —
    # `pass`, `appel_vision` — est présent à la tête pour des raisons étrangères au point).
    ex = f" ; ex. `{max(found, key=len)[:60]}`" if found else ""
    proof = f"jetons cités encore présents à la tête : {n} ({checked} fichier(s) lus){ex}"
    if not found:
        return n, proof, "aucun", body_col
    files = sorted({p for ps in where.values() for p in ps})
    return (n, proof, ", ".join(p.rsplit("/", 1)[-1] for p in files[:3]) + f" @ {sha[:7]}",
            body_col)


# --------------------------------------------------------------------------- rendu
def fiche_prompt(c: Candidate) -> str:
    rec = json.dumps({"pr": c.pr, "comment_id": c.comment_id, "auteur": c.auteur,
                      "date": c.date, "extrait": c.body[:EXTRAIT_LEN]}, ensure_ascii=False)
    return (
        "Recopie les champs de l'enregistrement ci-dessous dans un JSON strict, sans rien inventer, "
        "sans calcul, sans jugement. Clés exactes : pr, comment_id, auteur, date, extrait. "
        "Valeurs recopiées au caractère près. Aucun autre texte que le JSON.\n\n" + rec
    )


def render(rows: list[Candidate], meta: dict) -> str:
    out = []
    out.append(f"# W1 — Réserves par PR — {meta['repo']} — {meta['stamp']}\n")
    out.append(f"Portes : {meta['gate_pass']}/{meta['n']} fiches PASS (schéma+verbatim). "
               f"Rappel mesuré : {meta['recall']}. Aucune décision de levée (hors périmètre BG).\n")
    for pr in sorted({r.pr for r in rows}):
        sub = [r for r in rows if r.pr == pr]
        out.append(f"\n## PR #{pr} — {len(sub)} point(s) — tête `{meta['heads'].get(pr, '?')[:12]}`\n")
        out.append("| point (verbatim + id) | auteur (login) | réponse lane (id, date) | "
                   "jetons cités encore présents à la tête | où | body de PR | levée (fait) |")
        out.append("|---|---|---|---|---|---|---|")
        for r in sub:
            pt = r.body.replace("|", "\\|").replace("\n", " ")[:220]
            # Une fiche qui a échoué la porte verbatim se SIGNALE : le lecteur doit voir
            # laquelle des 14 lignes n'a pas passé, pas seulement le compte en en-tête.
            if r.gate and not (r.gate.get("schema") and
                               r.gate.get("verbatim") == r.gate.get("verbatim_total")):
                pt = (f"⚠️ PORTE ÉCHUE {r.gate.get('verbatim')}/{r.gate.get('verbatim_total')} "
                      f"champ {r.gate.get('missing')} — " + pt)
            out.append(f"| {pt} ({r.comment_id}) | {r.auteur} | {r.lane_reply or '—'} | "
                       f"{r.verdict_reason or '—'} | {r.where_head or '—'} | {r.body_pr or '—'} | "
                       f"{r.lifted or 'non levée'} |")
    out.append("\n---\n*Livrable mécanique : chaque valeur est un extrait de la source, provenance "
               "citée. La colonne « jetons cités » est un FAIT (présence à la tête), pas un statut : "
               "une réserve cite tantôt le défaut, tantôt la preuve que c'est bon — la lane seule "
               "sait ce qu'elle a corrigé. Le BG ne juge pas la levée.*\n")
    return "\n".join(out)


# --------------------------------------------------------------------------- main
def self_test() -> int:
    """Portes 1+2 sur fixtures, hors réseau."""
    good = Candidate(pr=1, kind="comment", comment_id="issue:1", auteur="alice",
                     date="2026-11-05T00:00:00Z", body="Le carnet cite `execution_count: 12`.")
    ok = gate(good, {"raw": json.dumps({"pr": 1, "comment_id": "issue:1", "auteur": "alice",
                                        "date": "2026-11-05T00:00:00Z",
                                        "extrait": "Le carnet cite `execution_count: 12`."})})
    bad = gate(good, {"raw": json.dumps({"pr": 1, "comment_id": "issue:1", "auteur": "alice",
                                         "date": "2026-11-05T00:00:00Z",
                                         "extrait": "Le carnet cite 42."})})
    broke = gate(good, {"raw": "aucun JSON ici"})
    cases = [("fiche exacte", ok, True), ("valeur inventée", bad, False), ("pas de JSON", broke, False)]
    rc = 0
    for name, rep, want in cases:
        passed = rep["schema"] and rep["verbatim"] == rep["verbatim_total"]
        verdict = "PASS" if passed == want else "FAIL"
        rc |= 0 if verdict == "PASS" else 1
        print(f"[{verdict}] {name}: schema={rep['schema']} verbatim={rep['verbatim']}/{rep['verbatim_total']} "
              f"missing={rep['missing']} (attendu {'accepté' if want else 'rejeté'})")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--prs", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--no-mini", action="store_true", help="portes 1+2 désactivées (colonnes mécaniques seules)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    if a.self_test:
        return self_test()
    if not a.prs:
        return print("--prs requis") or 2

    key = engine_key()
    cache: dict = {}
    heads: dict = {}
    rows: list[Candidate] = []
    n_ok = n_tot = 0
    skipped = []

    for pr in [int(x) for x in a.prs.split(",") if x.strip()]:
        pull = gh_api(f"/repos/{a.repo}/pulls/{pr}")
        if isinstance(pull, list):
            pull = pull[0]
        sha = pull["head"]["sha"]
        heads[pr] = sha
        cands = collect(a.repo, pr)
        fbk = pull_files(a.repo, pr)
        print(f"#{pr} tete={sha[:10]} candidats={len(cands)}", file=sys.stderr)
        for c in cands:
            try:
                n_tot += 1
                if a.no_mini:
                    c.gate = {}
                    n_ok += 1
                else:
                    raw, _ = engine(fiche_prompt(c), key)
                    c.gate = gate(c, {"raw": raw})
                    if c.gate["schema"] and c.gate["verbatim"] == c.gate["verbatim_total"]:
                        n_ok += 1
                    else:
                        skipped.append(f"#{pr} {c.comment_id} portes={c.gate}")
                v, why, wh, bp = mechanical_verdict(c, a.repo, sha, cache, fbk,
                                                    pull.get("body") or "")
                c.verdict, c.verdict_reason, c.where_head, c.body_pr = v, why, wh, bp
            except Exception as e:
                c.verdict, c.verdict_reason, c.where_head, c.body_pr = "échec", str(e)[:160], "—", "—"
                skipped.append(f"#{pr} {c.comment_id} {str(e)[:120]}")
            rows.append(c)

    stamp = time.strftime("%Y-%m-%d %H:%M local", time.localtime())
    meta = {"repo": a.repo, "stamp": stamp, "n": n_tot, "gate_pass": n_ok, "heads": heads,
            "recall": f"{len(rows)} points retenus" + (f", {len(skipped)} écartés" if skipped else "")}
    md = render(rows, meta)
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
        print(f"écrit : {a.out}", file=sys.stderr)
    print(md)
    for s in skipped:
        print(f"[écarté] {s}", file=sys.stderr)
    return 0 if n_ok == n_tot else 1


if __name__ == "__main__":
    sys.exit(main())
