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
HUB = os.environ.get("CLAUDISH_HUB", "http://localhost:3000")
# Le directeur (tier au-dessus du mini, spec §3) passe par le hub claudish — standard de
# consommation flotte. La clé proxy vient de l'env, JAMAIS du dépôt (demande à po-2025:claudish).
HUB_KEY_ENV = "CLAUDISH_PROXY_KEY"
DIRECTEUR_MODEL = os.environ.get("DIRECTEUR_MODEL", "qwen3.6-35b-a3b")
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


# --------------------------------------------------------------------------- directeur
# Spec §3 : le directeur RANGE ET PRIORISE SEULEMENT (oldest-first, « à lire en premier »),
# sur fiches déjà passées par les portes. Interdits : verdict de fond, décision de levée.
# Le driver porte les portes DU directeur (producteur mini ≠ directeur ≠ portes = driver).

# Routage mécanique par point — FAITS (existence + dates), aucune polarité (leçon §10.1) :
#   levée posée        -> FERMÉ        (le coordinateur a tranché ; rien en attente)
#   réponse lane posée -> COORDINATEUR (arbitrage/levée formelle attendus de lui)
#   sinon              -> LANE         (réponse/correction attendue de la lane)
BALL_PRIORITY = {"LANE": 0, "COORDINATEUR": 1, "FERMÉ": 2}


def balle_point(c: Candidate) -> str:
    if c.lifted:
        return "FERMÉ"
    if c.lane_reply:
        return "COORDINATEUR"
    return "LANE"


def balle_pr(rows: list[Candidate]) -> str:
    """Pire balle de la PR (celle qui bloque : LANE > COORDINATEUR > FERMÉ)."""
    return min((balle_point(r) for r in rows), key=lambda b: BALL_PRIORITY[b])


def facts_table(rows: list[Candidate], heads: dict) -> str:
    """Table de faits compacte, une ligne par PR — le SEUL texte donné au directeur."""
    lines = []
    for pr in sorted({r.pr for r in rows}):
        sub = [r for r in rows if r.pr == pr]
        oldest = min((r.date for r in sub if r.date), default="?")
        n_fermes = sum(1 for r in sub if balle_point(r) == "FERMÉ")
        gate_ok = sum(1 for r in sub if r.gate and r.gate.get("schema")
                      and r.gate.get("verbatim") == r.gate.get("verbatim_total"))
        worst = next((r.verdict for r in sub if r.verdict and r.verdict not in ("—", "?", "échec")), "—")
        lines.append(f"PR {pr} | tête {heads.get(pr, '?')[:7]} | points {len(sub)} "
                     f"(fiches {gate_ok} PASS) | balle {balle_pr(sub)} | "
                     f"levées {n_fermes}/{len(sub)} | plus ancien {oldest[:10]} | "
                     f"jetons pire point {worst}")
    return "\n".join(lines)


# Définition versionnée du directeur — l'empreinte sha256 est tracée dans chaque run (PO, §3c).
DIRECTEUR_DEF = (
    "Tu es le directeur de lecture d'un coordinateur pressé. On te donne une table de FAITS, "
    "une ligne par pull request. Ta seule mission : produire l'ORDRE DE LECTURE (« à lire en "
    "premier »), en citant un fait de la ligne. Règles : (1) tu couvres TOUTES les PRs, chacune "
    "exactement une fois, aucune inventée ; (2) chaque raison est courte et CITE un fait de la "
    "ligne entre backticks ; (3) tu ne juges PAS le fond (pédagogie, preuve, honnêteté), tu ne "
    "décides PAS d'une levée de réserve, tu ne donnes AUCUN statut du type prêt/bloqué/traité — "
    "seulement l'ordre et le fait qui le motive. Réponds UNIQUEMENT un JSON strict : "
    '{"ordre": [{"pr": <nombre>, "raison": "<texte>"}]}'
)


def directeur_gates(reply: str, prs: set[int], facts: str) -> dict:
    """Portes DU directeur (mécaniques, dans le driver) :
    G1 JSON strict à clés exactes ; G2 permutation exacte de l'entrée (ni inventé, ni oublié) ;
    G3 chaque raison cite ≥1 fait verbatim (sous-chaîne ≥8 car. de la table) ;
    G4 aucun mot de décision (le directeur range, il ne tranche pas)."""
    rep = {"json": False, "permutation": False, "verbatim": 0, "verbatim_total": 0,
           "interdits": [], "ordre": []}
    m = re.search(r"\{.*\}", reply or "", re.S)
    if not m:
        return rep
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return rep
    rep["json"] = sorted(obj.keys()) == ["ordre"] and isinstance(obj["ordre"], list)
    if not rep["json"]:
        return rep
    seen: list[int] = []
    for it in obj["ordre"]:
        if not isinstance(it, dict) or sorted(it.keys()) != ["pr", "raison"]:
            return rep
        pr, raison = it["pr"], str(it["raison"])
        rep["verbatim_total"] += 1
        # G3 : un segment citation `` … `` (ou une sous-chaîne ≥8 car.) repris de la table.
        cited = re.findall(r"`([^`\n]{8,80})`", raison) or [s for s in (raison,) if len(s) >= 8]
        if any(seg in facts for seg in cited):
            rep["verbatim"] += 1
        low = raison.lower()
        for bad in ("à lever", "à lever.", "doit être levée", "levable", "prêt pour merge",
                    "ready", "blocked", "traité", "non traité", "approuve"):
            if bad in low:
                rep["interdits"].append(bad)
        seen.append(pr)
    rep["permutation"] = sorted(seen) == sorted(prs) and len(seen) == len(prs)
    rep["ordre"] = seen
    return rep


def directeur_passes(rep: dict) -> bool:
    return (rep["json"] and rep["permutation"]
            and rep["verbatim"] == rep["verbatim_total"] == max(1, rep["verbatim_total"])
            and not rep["interdits"])


def directeur_llm(facts: str) -> tuple[str, dict]:
    """Appel hub (OpenAI /v1) — swift alias par défaut, DIRECTEUR_MODEL sinon."""
    key = os.environ.get(HUB_KEY_ENV, "")
    if not key:
        raise RuntimeError(f"{HUB_KEY_ENV} absent de l'environnement (clé proxy claudish)")
    body = json.dumps({"model": DIRECTEUR_MODEL, "temperature": 0, "max_tokens": 600,
                       "messages": [{"role": "user", "content": DIRECTEUR_DEF + "\n\n" + facts}]}
                      ).encode()
    req = urllib.request.Request(f"{HUB}/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {key}"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=400) as r:   # swift : ≥400 s (mandat user 03/11)
        payload = json.loads(r.read())
    return payload["choices"][0]["message"]["content"], {
        "model_used": payload.get("model", DIRECTEUR_MODEL), "lat_s": round(time.time() - t0, 1),
        "usage": payload.get("usage", {}), "hub": HUB,
        "def_sha256": __import__("hashlib").sha256(DIRECTEUR_DEF.encode()).hexdigest()[:12],
    }


def directeur_order(rows: list[Candidate], heads: dict, mode: str) -> tuple[list[int], str]:
    """Rend (ordre des PRs, rapport). mode: off | mock | llm.
    mock = ordre mécanique déterministe (balle bloquante puis plus ancien), SANS modèle ;
    llm   = le directeur range, puis ses portes ; toute échec → fallback mécanique, signalé."""
    import hashlib
    sha = hashlib.sha256(DIRECTEUR_DEF.encode()).hexdigest()[:12]
    prs = sorted({r.pr for r in rows})
    by_pr = {p: [r for r in rows if r.pr == p] for p in prs}
    mech = sorted(prs, key=lambda p: (BALL_PRIORITY[balle_pr(by_pr[p])],
                                      min((r.date for r in by_pr[p] if r.date), default="")))
    if mode == "off":
        return [], "off"
    if mode == "mock":
        return mech, (f"directeur=mock def_sha256={sha} ordre=mécanique "
                      f"(balle bloquante puis oldest-first)")
    facts = facts_table(rows, heads)
    try:
        reply, meta = directeur_llm(facts)
    except Exception as e:
        return mech, f"⚠️ DIRECTEUR INDISPONIBLE ({str(e)[:120]}) — fallback ordre mécanique. def_sha256={sha}"
    rep = directeur_gates(reply, set(prs), facts)
    ok = directeur_passes(rep)
    if ok:
        return rep["ordre"], (f"directeur: model={meta['model_used']} hub={meta['hub']} "
                              f"def_sha256={meta['def_sha256']} lat={meta['lat_s']}s "
                              f"tokens={meta['usage'].get('total_token', meta['usage'])} "
                              f"portes=PASS")
    return mech, (f"⚠️ DIRECTEUR ÉCHUE portes={rep} — fallback ordre mécanique. "
                  f"model={meta['model_used']} def_sha256={meta['def_sha256']} lat={meta['lat_s']}s")


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

    # À lire en premier (directeur) — ordre seul, faits recopiés, aucun statut (spec §3).
    if meta.get("directeur_order"):
        by_pr = {p: [r for r in rows if r.pr == p] for p in {r.pr for r in rows}}
        out.append("## À lire en premier (directeur — rangement seul, la balle est mécanique)\n")
        out.append("| rang | PR | balle (mécanique) | points | plus ancien |")
        out.append("|---|---|---|---|---|")
        for i, pr in enumerate(meta["directeur_order"], 1):
            sub = by_pr[pr]
            oldest = min((r.date for r in sub if r.date), default="?")[:10]
            out.append(f"| {i} | #{pr} | {balle_pr(sub)} | {len(sub)} | {oldest} |")
        out.append(f"\n{meta['directeur_report']}\n")

    for pr in sorted({r.pr for r in rows}):
        sub = [r for r in rows if r.pr == pr]
        out.append(f"\n## PR #{pr} — {len(sub)} point(s) — tête `{meta['heads'].get(pr, '?')[:12]}`\n")
        out.append("| point (verbatim + id) | auteur (login) | réponse lane (id, date) | "
                   "jetons cités encore présents à la tête | où | body de PR | levée (fait) | "
                   "balle (mécanique) |")
        out.append("|---|---|---|---|---|---|---|---|")
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
                       f"{r.lifted or 'non levée'} | {balle_point(r)} |")
    out.append("\n---\n*Livrable mécanique : chaque valeur est un extrait de la source, provenance "
               "citée. La colonne « jetons cités » est un FAIT (présence à la tête), pas un statut : "
               "une réserve cite tantôt le défaut, tantôt la preuve que c'est bon — la lane seule "
               "sait ce qu'elle a corrigé. La colonne « balle » est un routage par dates/auteurs "
               "(levée→FERMÉ, réponse posée→COORDINATEUR, sinon→LANE), pas un jugement. "
               "Le BG ne juge pas la levée.*\n")
    return "\n".join(out)


# --------------------------------------------------------------------------- main
def self_test() -> int:
    """Portes 1+2 et portes du directeur sur fixtures, hors réseau."""
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

    # Portes du directeur (G1-G4) — fixtures hors réseau.
    facts = ("PR 24442 | tête abc1234 | points 1 (fiches 1 PASS) | balle LANE | "
             "levées 0/1 | plus ancien 2026-11-03 | jetons pire point 0/2\n"
             "PR 24755 | tête def5678 | points 1 (fiches 1 PASS) | balle FERMÉ | "
             "levées 1/1 | plus ancien 2026-11-04 | jetons pire point 4/6")
    d_ok = json.dumps({"ordre": [{"pr": 24442, "raison": "à lire en premier : `balle LANE`"},
                                 {"pr": 24755, "raison": "ensuite : `levées 1/1`"}]})
    d_invented = json.dumps({"ordre": [{"pr": 24442, "raison": "`balle LANE`"},
                                       {"pr": 99999, "raison": "`levées 1/1`"}]})
    d_dropped = json.dumps({"ordre": [{"pr": 24442, "raison": "`balle LANE`"}]})
    d_fab = json.dumps({"ordre": [{"pr": 24442, "raison": "le carnet est correct selon moi"},
                                  {"pr": 24755, "raison": "`levées 1/1`"}]})
    d_verdict = json.dumps({"ordre": [{"pr": 24442, "raison": "`balle LANE` — doit être levée"},
                                      {"pr": 24755, "raison": "`levées 1/1`"}]})
    d_cases = [("permutation+verbatim", d_ok, True), ("PR inventée", d_invented, False),
               ("PR oubliée", d_dropped, False), ("raison non verbatim", d_fab, False),
               ("mot de décision", d_verdict, False)]
    for name, reply, want in d_cases:
        rep = directeur_gates(reply, {24442, 24755}, facts)
        passed = directeur_passes(rep)
        verdict = "PASS" if passed == want else "FAIL"
        rc |= 0 if verdict == "PASS" else 1
        print(f"[{verdict}] directeur {name}: json={rep['json']} perm={rep['permutation']} "
              f"verbatim={rep['verbatim']}/{rep['verbatim_total']} interdits={rep['interdits']} "
              f"(attendu {'accepté' if want else 'rejeté'})")

    # Ordre mécanique (mock) : LANE avant FERMÉ, puis oldest-first.
    m_rows = [
        Candidate(pr=24755, kind="review:LGTM", comment_id="r:1", auteur="bot", date="2026-11-04T10:00:00Z",
                  body="point", lifted="LEVÉE 2026-11-05 (comment 1)"),
        Candidate(pr=24442, kind="review:LGTM", comment_id="r:2", auteur="bot", date="2026-11-03T09:00:00Z",
                  body="point"),
    ]
    order, report = directeur_order(m_rows, {24442: "a", 24755: "b"}, "mock")
    want_order = [24442, 24755]
    verdict = "PASS" if order == want_order else "FAIL"
    rc |= 0 if verdict == "PASS" else 1
    print(f"[{verdict}] directeur mock: ordre={order} (attendu {want_order}) — {report[:60]}")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--prs", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--no-mini", action="store_true", help="portes 1+2 désactivées (colonnes mécaniques seules)")
    ap.add_argument("--directeur", choices=("off", "mock", "llm"), default="off",
                    help="off=absent ; mock=ordre mécanique (balle puis oldest-first) ; "
                         "llm=directeur hub (exige CLAUDISH_PROXY_KEY), portes + fallback mock")
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
    d_order, d_report = directeur_order(rows, heads, a.directeur)
    meta = {"repo": a.repo, "stamp": stamp, "n": n_tot, "gate_pass": n_ok, "heads": heads,
            "recall": f"{len(rows)} points retenus" + (f", {len(skipped)} écartés" if skipped else ""),
            "directeur_order": d_order, "directeur_report": d_report}
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
