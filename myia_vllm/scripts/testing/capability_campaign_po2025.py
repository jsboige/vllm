"""Campagne de capacite du siege po-2025 — batterie reutilisable, deux modeles comparables.

POURQUOI CETTE BATTERIE EXISTE
==============================
La promotion d'Ornith-1.5-9B du 03/11 a echoue sur des portes dont TROIS se sont revelees
defaillantes dans le sens du resultat propre (comparaison de chaines non normalisee, filtre
qui eliminait le cas piege avant de le compter, seau d'erreur manquant dans une
classification). Le siege a donc besoin d'une batterie qui :

  - calcule l'ORACLE PAR LA MACHINE (`in`, jamais la parole du modele) ;
  - normalise la sortie (numerotation, puces) avant de comparer ;
  - classe CHAQUE ligne de sortie dans exactement un seau, sans trou :
        hit       dans l'oracle
        faux_pos  presente au corpus mais HORS oracle   <- le seau qui manquait a l'eval
        fabriquee absente du corpus (prefixe d'horodatage)
        hors_fmt  ni ligne de journal ni oracle (commentaire, delire)
  - tourne a l'identique sur les DEUX modeles, donc se compare a l'incumbent ;
  - utilise de VRAIS journaux du siege, pas des lignes inventees.

Le corpus est lu sur disque et l'oracle recalcule a chaque execution : leger le fichier,
l'oracle suit. Aucune valeur attendue n'est codee en dur.

CRITERE D'ADMISSION — FIGE AVANT LA MESURE D'ORNITH (arbitrage user 03/11 22:30)
================================================================================
Verbatim user : « tu pousses les tests, et si Ornith a un avantage significatif, on
onboarde, sinon retropedalage et on pousse sur la solidification par sk-agent en
test time scaling ».

**AVANTAGE SIGNIFICATIF** (constante ci-dessous, ecrite AVANT d'avoir le score) :
  - le candidat gagne sur >= MIN_WINS epreuves du corps (T1-T6, T7 refus, T9 horde) ;
  - il n'en perd AUCUNE ;
  - au moins une victoire est un DEFAUT de l'incumbent (faux positif, fabrication,
    ou couverture < 0.90), et non un simple ecart de rappel.
Sinon -> PAS significatif : retropedalage, FrogNano reste en service, et la lane
bascule sur la solidification par sk-agent en test-time scaling.

« Gagne » = meilleure couverture ; a couverture egale, moins de faux positifs ; a
egalite encore, moins de fabriquees. Un ecart d'UNE ligne sur 14 dans un seul test
n'est PAS un avantage significatif : c'est reel (sorties deterministes) mais pas
materiel au sens du user — et c'est ecrit ici pour ne pas le reevaluer apres coup.

USAGE
    python capability_campaign_po2025.py --base http://localhost:5003 --model mini \
        --label frognano --out .tmp/campaign_frognano.json

Les cles ne sont jamais ecrites sur disque ni affichees.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# --- Criteres d'admission, figes avant la mesure du candidat (voir en-tete) ---------
MIN_WINS = 3            # epreuves gagnees par le candidat
MAX_LOSSES = 0          # epreuves perdues tolerees
MATERIAL_COVERAGE = 0.90  # une couverture incumbent < 0.90 compte comme DEFAUT

GUARD = r"C:\ProgramData\maint-scripts\logs\guard-docker-logon\guard.log"
GOVERNOR = r"D:\dev\vllm\myia_vllm\_logs\gpu-governor.log"
THERMAL = r"D:\dev\vllm\myia_vllm\_logs\gpu-thermal.log"

NUM = re.compile(r"^\s*(?:[-*•]\s*)?\d{1,3}[.)]\s*")
TS_START = re.compile(r"^\s*\[?\d{4}-\d{2}-\d{2}")


def norm(line: str) -> str:
    """Retire la numerotation de tete. CORRECTION v1 : sans ca, un modele qui numerote
    est note 0 et l'ecart mesure la ponctuation, pas la capacite."""
    return NUM.sub("", line).strip()


def read_lines(path: str) -> list[str]:
    with open(path, encoding="utf-8", errors="replace") as f:
        return [l.rstrip("\n") for l in f if l.strip()]


def window(path: str, start: int, n: int) -> list[str]:
    L = read_lines(path)
    start = max(0, min(start, max(0, len(L) - n)))
    return L[start:start + n]


def build_corpora() -> dict:
    """Chaque test = (lignes du corpus, aiguille, description). Oracle = par la machine."""
    T = {}

    # T1 — journal reel homogene, petite fenetre. Densite elevee (cas courant du siege).
    t1 = window(GOVERNOR, 0, 45)
    T["T1_reel_homogene_45"] = (t1, "HEARTBEAT",
                                "45 lignes reelles de gpu-governor.log, motif courant")

    # T2 — journal reel, densite FAIBLE. Un modele qui liste trop se fait prendre ici.
    t2 = window(GOVERNOR, 0, 60)
    T["T2_reel_faible_densite_60"] = (t2, "RAM CRITIQUE",
                                     "60 lignes reelles, motif rare (8/60)")

    # T3 — corpus HETEROGENE (3 journaux differents) : le point faible documente du siege
    #      (« non garanti sur corpus heterogene »).
    t3 = window(GOVERNOR, 40, 20) + window(THERMAL, 40, 20) + window(GUARD, 200, 20)
    T["T3_heterogene_60"] = (t3, "WARN",
                            "3 journaux concatenes, formats differents")

    # T4 — QUASI-DOUBLONS REELS, discrimination a UN CARACTERE. Fenetre 2380 de guard.log :
    #      31 lignes portent `engine UP (29.8.2)` et 29 portent `engine UP (29.9.2)`.
    #      Elles ne different que par ce caractere. C'est le cas que le corpus synthetique
    #      du 03/11 imitait mal ; ici c'est le journal du siege lui-meme, en vrai.
    t4 = window(GUARD, 2380, 60)
    T["T4_quasi_doublons_un_caractere_60"] = (
        t4, "29.8.2", "60 lignes reelles : 31x engine UP (29.8.2) vs 29x (29.9.2)")

    # T5 — GRAND volume, le cas des balayages reels (mini-sweeper, fan-out).
    #      200 lignes et non 300 : a 300, le prompt (~6 K tok) + la sortie attendue
    #      (~21 K tok) frôlent la fenetre de 32 K et le test mesurerait la fenetre.
    t5 = window(GOVERNOR, 0, 200)
    T["T5_grand_200"] = (t5, "HEARTBEAT", "200 lignes reelles, balayage")

    # T6 — PIEGE INJECTE : 120 lignes reelles + 1 ligne construite qui contient PRESQUE le
    #      motif (`temp=33.0C` ne contient pas `temp=33C`). Declare comme injectee.
    #      Elle ne doit PAS sortir ; toute sortie la contenant est un faux positif.
    base = window(THERMAL, 380, 120)
    needle = "temp=33C"
    trap = "2026-10-07 09:14:02 HEARTBEAT temp=33.0C util=0% vram=0/16384MiB ram_free=12004MB"
    t6 = list(base)
    t6.insert(31, trap)
    T["T6_piege_injecte_121"] = (t6, needle,
                                 "120 lignes reelles + 1 piege INJECTE (`temp=33.0C`)")

    # T7 — MOTIF ABSENT : refus attendu. Un modele qui rend quelque chose ment.
    t7 = window(GOVERNOR, 0, 40)
    T["T7_motif_absent_40"] = (t7, "FOOBAR_INEXISTANT",
                               "40 lignes reelles, motif absent : la bonne reponse est AUCUNE ligne")

    return T


def make_prompt(lines: list[str], needle: str) -> str:
    body = "\n".join(lines)
    return ("Voici un journal, une ligne par ligne, sans numerotation.\n\n"
            f"{body}\n\n"
            f"Liste VERBATIM, une par ligne, sans numerotation, sans entete et sans commentaire, "
            f"UNIQUEMENT les lignes qui contiennent la chaine exacte {needle}. "
            f"Ne modifie aucun caractere. Ne recopie AUCUNE autre ligne. "
            f"S'il n'y en a aucune, reponds exactement: AUCUNE")


def post(base: str, key: str, model: str, prompt: str, max_tokens: int = 2048,
         temperature: float = 0.0, timeout: int = 600) -> dict:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def score_output(out: str, oracle: list[str], corpus: set[str], needle: str) -> dict:
    """Classe CHAQUE ligne de sortie dans exactement un seau. Aucun trou (lecon du 03/11)."""
    L = [norm(l) for l in out.splitlines()]
    L = [l for l in L if l]
    if len(L) == 1 and L[0].upper().strip(" .!:") == "AUCUNE":
        L = []
    oracle_set = set(oracle)
    hit, faux_pos, fabriquee, hors_fmt = set(), [], [], []
    for l in L:
        if l in oracle_set:
            hit.add(l)
        elif l in corpus:
            faux_pos.append(l)          # present au corpus mais hors oracle -> SEau manquant

        elif TS_START.match(l):
            fabriquee.append(l)          # ressemble a une ligne de journal, n'existe pas
        else:
            hors_fmt.append(l)           # commentaire, entete, delire
    return {
        "rappel": len(hit),
        "oracle": len(oracle_set),
        "faux_positifs": len(faux_pos),
        "fabriquees": len(fabriquee),
        "hors_format": len(hors_fmt),
        "lignes_rendues": len(L),
        "detail_faux_positifs": [x[:100] for x in faux_pos[:4]],
        "detail_fabriquees": [x[:100] for x in fabriquee[:4]],
        "manquantes": [x[:100] for x in oracle if x not in hit][:4],
        "couverture": round(len(hit) / max(1, len(oracle_set)), 3),
    }


def budget_for(oracle_lines: list[str]) -> int:
    """Budget de generation dimensionne sur la SORTIE ATTENDUE, pas sur une constante.

    Lecon du 03/11 : un plafond trop bas produit un `finish=length` qui se lit a tort
    comme un echec de rappel, et une ligne coupee en deux se lit a tort comme une
    fabrication. On estime ~1,6 token par caractere de sortie et on double la marge.
    """
    chars = sum(len(l) + 1 for l in oracle_lines)
    return min(24576, max(2048, int(chars * 1.6) + 600))


def run_extraction(base, key, model, lines, needle, repeat=1):
    prompt = make_prompt(lines, needle)
    oracle = [l for l in lines if needle in l]
    corpus = set(lines)
    budget = budget_for(oracle)
    runs = []
    for i in range(repeat):
        t0 = time.time()
        r = post(base, key, model, prompt, max_tokens=budget)
        dt = time.time() - t0
        ch = r["choices"][0]
        out = ch["message"].get("content") or ""
        s = score_output(out, oracle, corpus, needle)
        s.update({"run": i + 1, "wall_s": round(dt, 2),
                  "finish": ch.get("finish_reason"),
                  "completion_tokens": r["usage"]["completion_tokens"],
                  "prompt_tokens": r["usage"]["prompt_tokens"]})
        runs.append(s)
    return runs


def run_refusal(base, key, model):
    """T7 : le motif est absent. Toute ligne rendue est une invention."""
    lines = window(GOVERNOR, 0, 40)
    prompt = make_prompt(lines, "FOOBAR_INEXISTANT")
    r = post(base, key, model, prompt)
    ch = r["choices"][0]
    out = ch["message"].get("content") or ""
    L = [norm(l) for l in out.splitlines() if norm(l)]
    constate = any("AUCUNE" in l.upper() for l in L)
    rendues = [l for l in L if l.upper().strip(" .!:") != "AUCUNE"]
    return {"constate_absence": constate, "lignes_rendues": len(rendues),
            "correct": bool(constate and not rendues),
            "detail": [x[:100] for x in rendues[:4]]}


def run_tool(base, key, model):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Quel temps fait-il a Paris ? Utilise l'outil."}],
        "max_tokens": 512, "temperature": 0,
        "tools": [{"type": "function", "function": {
            "name": "get_weather", "description": "Meteo d'une ville",
            "parameters": {"type": "object",
                           "properties": {"city": {"type": "string"}},
                           "required": ["city"]}}}],
    }
    req = urllib.request.Request(
        base.rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read().decode())
    tc = d["choices"][0]["message"].get("tool_calls") or []
    return {"tool_calls": len(tc),
            "nom": tc[0]["function"]["name"] if tc else None,
            "correct": bool(tc and tc[0]["function"]["name"] == "get_weather")}


def run_concurrency(base, key, model, n=8):
    """La horde : c'est l'usage reel du siege. Mesure le taux d'erreur sous charge."""
    lines = window(GOVERNOR, 0, 45)
    prompt = make_prompt(lines, "HEARTBEAT")
    oracle = [l for l in lines if "HEARTBEAT" in l]
    corpus = set(lines)
    # Meme budget que l'epreuve sequentielle equivalente : sinon la horde mesure la
    # troncature de SON plafond et non la tenue sous charge (artefact mesure le 03/11).
    budget = budget_for(oracle)

    def one(_):
        t0 = time.time()
        try:
            r = post(base, key, model, prompt, max_tokens=budget, timeout=900)
            ch = r["choices"][0]
            out = ch["message"].get("content") or ""
            s = score_output(out, oracle, corpus, "HEARTBEAT")
            return {"ok": True, "wall_s": round(time.time() - t0, 2),
                    "comp": r["usage"]["completion_tokens"],
                    "couverture": s["couverture"], "faux_positifs": s["faux_positifs"]}
        except Exception as e:
            return {"ok": False, "err": str(e)[:120], "wall_s": round(time.time() - t0, 2)}

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=n) as ex:
        res = list(ex.map(one, range(n)))
    wall = time.time() - t0
    ok = [r for r in res if r.get("ok")]
    return {"n": n, "wall_s": round(wall, 2), "ok": len(ok), "err": len(res) - len(ok),
            "aggregate_tok_s": round(sum(r["comp"] for r in ok) / wall, 1) if wall else 0,
            "couverture_min": min((r["couverture"] for r in ok), default=None),
            "couverture_moy": round(sum(r["couverture"] for r in ok) / len(ok), 3) if ok else None,
            "detail_err": [r["err"] for r in res if not r.get("ok")][:3]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5003")
    ap.add_argument("--model", default="mini")
    ap.add_argument("--label", default="modele")
    ap.add_argument("--out", default="")
    ap.add_argument("--skip-concurrency", action="store_true")
    ap.add_argument("--repeat", type=int, default=2,
                    help="repetitions des extractions (determinisme)")
    args = ap.parse_args()

    key = os.environ.get("MINI_KEY", "")
    if not key:
        tail = ""
        try:
            with open(r"D:\dev\vllm\myia_vllm\.env", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("VLLM_API_KEY_MINI"):
                        key = line.split("=", 1)[1].strip()
                        tail = key[-4:]
                        break
        except OSError as e:
            print("cle illisible:", e, file=sys.stderr)
        if key:
            print(f"cle chargee depuis .env (longueur {len(key)}, fin {tail}) — jamais affichee")

    result = {"label": args.label, "model": args.model, "base": args.base,
              "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "tests": {}}

    corpora = build_corpora()
    print(f"\n{'test':32s} {'rappel':>9s} {'fp':>4s} {'fab':>4s} {'hors':>5s} {'cov':>6s} {'gen':>5s}")
    print("-" * 74)
    for name, (lines, needle, desc) in corpora.items():
        if name.startswith("T7"):
            r = run_refusal(args.base, key, args.model)
            result["tests"][name] = {"desc": desc, "refusal": r}
            print(f"{name:32s} refus={'OK' if r['correct'] else 'ECHEC':>9s} "
                  f"rendues={r['lignes_rendues']}")
            continue
        runs = run_extraction(args.base, key, args.model, lines, needle, repeat=args.repeat)
        result["tests"][name] = {"desc": desc, "needle": needle, "runs": runs}
        for s in runs:
            print(f"{name:32s} {s['rappel']:>4d}/{s['oracle']:<4d} {s['faux_positifs']:>4d} "
                  f"{s['fabriquees']:>4d} {s['hors_format']:>5d} {s['couverture']:>6.2f} "
                  f"{s['completion_tokens']:>5d}")

    r = run_tool(args.base, key, args.model)
    result["tests"]["T8_outil"] = r
    print(f"\n{'T8_outil':32s} tool_calls={r['tool_calls']} nom={r['nom']} correct={r['correct']}")

    if not args.skip_concurrency:
        c = run_concurrency(args.base, key, args.model)
        result["tests"]["T9_horde_N8"] = c
        print(f"{'T9_horde_N8':32s} ok={c['ok']}/{c['n']} err={c['err']} "
              f"agg={c['aggregate_tok_s']} tok/s wall={c['wall_s']}s "
              f"cov_moy={c['couverture_moy']}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        print(f"\nresultats -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
