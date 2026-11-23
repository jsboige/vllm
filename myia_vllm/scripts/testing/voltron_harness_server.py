#!/usr/bin/env python3
"""Service harnais voltron — API HTTP locale (adoption flotte, mandat user 18/11).

UNE requête → réponse déjà fiabilisée. La chaîne worker (voltron-1.7B local,
:5028) + réparation dirigée (≤2 tours, delta signé du gate) + coordinateur
(swift-1.5-27b via hub claudish) tourne DANS le service ; chaque étage est
re-gaté par le CONTRAT fourni par l'appelant. L'appelant lit ok/détail — le
coût de vérification est déjà payé (critère d'adoption FrogNano : vérification
≪ refaire soi-même).

Types de tâches (familles mesurées, banc real_task_bench 40/40 en chaîne
complète ; le service exécute A→C, la phase B sibling restant un outil de
mesure hors-ligne — cf. docs/voltron-harness-adoption.md) :

  extract  {data, fields[, verbatim=True]}   → JSON exact, valeurs verbatim
  classify {data, classes}                   → {"classe","ligne_cle"} preuve verbatim
  numbers  {data, report_prompt, numbers}    → rapport citant exactement ces nombres
  diff     {a, b}  (JSON tous deux)          → l'outil calcule le diff, le modèle
                                               rédige le rapport (pivot-outil v2.1)

Tâches longues : POST /v1/jobs {"tasks":[...]} → job_id (exécution en fond,
persistée sur disque) ; GET /v1/jobs/<id> pour suivre. Reprise : au boot, un
job 'running' dont le thread est mort voit ses tâches restantes RELANCÉES
(la charge est persistée) ; les jobs pré-reprise deviennent 'orphaned'.

Auto-guérison : si l'engine :5028 est muet, `docker start voltron-harness`
puis attente santé ≤240 s. Bind 127.0.0.1:5029 — usage local machine,
même politique que l'engine d'éval (keyless, boucle locale).

Clé hub : env ZAI_API_KEY au lancement du serveur (résolue en mémoire par
start_voltron_service.ps1 depuis ~/.claude.json, jamais écrite sur disque).
Absent → phase C sautée, la réponse porte stage="a" + note.
"""
import concurrent.futures
import json
import os
import re
import subprocess
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys_dir = os.path.dirname(os.path.abspath(__file__))
import sys
sys.path.insert(0, sys_dir)
import real_task_bench as rb  # checkers + extraction JSON éprouvés du banc

ENGINE_URL = "http://127.0.0.1:5028"
ENGINE_MODEL = "voltron-1-mini"
ENGINE_CONTAINER = "voltron-harness"
# CHANGES_REQUESTED ai-01 §7-8 : aucune adresse LAN ni chemin machine versionnés
# — tout par environnement, le lanceur local fournit les valeurs (exemple
# documenté dans docs/voltron-harness-adoption.md §1).
HUB_URL = os.environ.get("VOLTRON_HUB_URL", "")  # chat() ajoute /v1/chat/completions
HUB_MODEL = os.environ.get("VOLTRON_HUB_MODEL", "swift-1.5-27b")
PORT = 5029
_data_root = os.path.join(os.path.expanduser("~"), ".voltron_harness")
JOBS_DIR = os.environ.get("VOLTRON_JOBS_DIR") or os.path.join(_data_root, "jobs")
USAGE_PATH = os.environ.get("VOLTRON_USAGE_PATH") or os.path.join(_data_root, "usage.json")
# compteur DURABLE (piège po-2025 : les compteurs engine avancent en fin de
# requête et repartent à zéro au boot — l'instrument d'adoption doit survivre
# aux restarts)
MAX_DATA_CHARS = 20000  # garde contexte 32K : data + prompt + réponse
MAX_DEFS_CHARS = 4000   # class_definitions sérialisées (contexte, pas corpus)
MAX_BODY_BYTES = 2 * 1024 * 1024  # borne POST (CHANGES_REQUESTED §6)
JOB_CONCURRENCY = 6     # moteur mesuré N=64 (3 673 t/s) ; 6 laisse la place
                         # aux appels /v1/task directs et borne la charge hub
MAX_REPAIR_ROUNDS = 2

# Ancrage de format par contrat (mesuré 20/11) : sans préremplissage, le 1.7B
# délibère en prose et le livrable arrive noyé — ou jamais (max_tokens épuisé
# en raisonnement). Prérempli, il complète mécaniquement. La réponse du moteur
# ne contient PAS le préfixe : gate et assemblage le recollent.
PREFILLS = {"extract": "{", "numbers": "Rapport : "}
HUB_KEY = os.environ.get("ZAI_API_KEY")  # figé au démarrage du serveur

_jobs_lock = threading.Lock()
_jobs = {}  # id -> dict(status, name, total, done, results)


# ---------------------------------------------------------------- transport

def chat(url, model, messages, max_tokens=400, timeout=120, api_key=None, prefill=None):
    msgs = list(messages)
    if prefill:
        msgs.append({"role": "assistant", "content": prefill})
    payload = {"model": model, "messages": msgs,
               "max_tokens": max_tokens, "temperature": 0.0}
    if prefill:
        # continuation assistant : vLLM exige ce couple, 400 BadRequest sinon
        # (mesuré 20/11). La réponse ne contient PAS le préfixe — l'appelant
        # concatène prefill + complétion pour reconstituer le JSON complet.
        payload["continue_final_message"] = True
        payload["add_generation_prompt"] = False
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions",
                                 data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    return d["choices"][0]["message"]["content"] or ""


def engine_healthy(timeout=2):
    try:
        with urllib.request.urlopen(ENGINE_URL + "/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_engine():
    """Auto-guérison : docker start + attente santé. Retourne (ok, message)."""
    if engine_healthy():
        return True, ""
    try:
        subprocess.run(["docker", "start", ENGINE_CONTAINER],
                       capture_output=True, timeout=30)
    except Exception as exc:
        return False, f"docker start échoué: {exc}"
    for _ in range(48):  # ≤240 s : boot mesuré 115-150 s
        if engine_healthy():
            return True, ""
        time.sleep(5)
    return False, "engine voltron-harness muet après docker start (240 s)"


# ---------------------------------------------------------------- contrats

def top_diff(a, b):
    """Diff de PREMIER niveau {clé: [valeur_a, valeur_b]} — le contrat mesuré
    v2.1 (check_report : valeurs sérialisées >60 chars exemptées de citation
    verbatim, la mention de clé + qualificatif suffit). Les sous-objets restent
    des valeurs entières."""
    return {k: [a.get(k), b.get(k)] for k in set(a) | set(b) if a.get(k) != b.get(k)}


def build_contract(t):
    """Valide la tâche entrante → (contract, prompt, gate_fn, feedback_fn, max_tokens)."""
    ty = t.get("type")
    if ty == "extract":
        data, fields = t.get("data", ""), t.get("fields")
        if not isinstance(fields, list) or not fields or not all(isinstance(f, str) for f in fields):
            return None, "extract: 'fields' = liste non vide de chaînes requis"
        if len(data) > MAX_DATA_CHARS:
            return None, f"extract: data > {MAX_DATA_CHARS} caractères"
        instruction = t.get("instruction") or (
            f"Extrais les champs suivants des Données : {fields}")
        contract = {"data": data, "fields": fields, "verbatim": bool(t.get("verbatim", True))}

        def gate(out):
            objs = rb.extract_json_objs(out)
            if not objs:
                return False, "aucun objet JSON parsable dans la réponse"
            obj = objs[0] if any(o.get(f) is not None for o in objs for f in fields) \
                else rb.merged_json_obj(out)
            missing = [f for f in fields if f not in obj]
            extra = [k for k in obj if k not in fields]
            if missing or extra:
                return False, f"clés manquantes {missing}, en trop {extra}"
            if contract["verbatim"]:
                bad = [k for k, v in obj.items()
                       if isinstance(v, str) and str(v) not in data]
                if bad:
                    return False, f"valeurs non verbatim (reformulées): {bad}"
            return True, ""

        prompt = (f"Données :\n{data}\n\n{instruction}\nRenvoie UNIQUEMENT un objet JSON avec "
                  f"exactement ces clés : {fields}. Les valeurs sont recopiées mot pour mot "
                  f"depuis les Données, sans reformulation. Les éventuels placeholders entre "
                  f"< > ou \"...\" dans l'instruction sont des indications de FORMAT, pas des "
                  f"valeurs — remplace-les par la valeur réelle extraite des Données. "
                  f"Rien d'autre que le JSON.")

        def fb(detail):
            return (f"Le vérificateur a rejeté ton JSON : {detail}. Renvoie UNIQUEMENT le "
                    f"JSON corrigé, clés exactement {fields}, valeurs recopiées mot pour "
                    f"mot des Données.")
        return contract, prompt, gate, fb, 600

    if ty == "classify":
        data, classes = t.get("data", ""), t.get("classes")
        if not isinstance(classes, list) or not classes:
            return None, "classify: 'classes' = liste non vide requis"
        if len(data) > MAX_DATA_CHARS:
            return None, f"classify: data > {MAX_DATA_CHARS} caractères"
        contract = {"data": data, "classes": classes}

        def gate(out):
            objs = rb.extract_json_objs(out)
            if not objs:
                return False, "aucun objet JSON parsable dans la réponse"
            obj = objs[0]
            cls = obj.get("classe")
            if cls not in classes:
                return False, f"classe '{cls}' hors taxonomie autorisée"
            ev = str(obj.get("ligne_cle", ""))
            # seuil 8 (était 15, héritage FrogNano) : une ligne de code juste
            # fait souvent 8-14 chars — à 15, les cellules courtes sont
            # structurellement ingatables en stage a (mesuré 20/11 : queue
            # stage c 17 % sur cellules C# réelles)
            if len(ev) < 8 or ev not in data:
                return False, "ligne_cle introuvable mot pour mot dans le texte (ou <8 caractères)"
            return True, ""

        prompt = (f"Texte :\n{data}\n\nClasse ce texte dans EXACTEMENT une de ces classes : "
                  f"{classes}. Renvoie UNIQUEMENT un JSON {{\"classe\": ..., \"ligne_cle\": ...}} "
                  f"où ligne_cle est la ligne la plus diagnostique du texte, recopiée mot pour "
                  f"mot (au moins 8 caractères).")
        return contract, prompt, gate, lambda d: (
            f"Classe incorrecte ou preuve invalide : {d}. Classes autorisées : {classes}. "
            f"Renvoie le JSON corrigé, ligne_cle recopiée mot pour mot depuis le Texte."), 400

    if ty == "numbers":
        data, wanted = t.get("data", ""), t.get("numbers")
        rp = t.get("report_prompt", "")
        # isinstance(list) : une chaîne est itérée caractère par caractère
        # (CHANGES_REQUESTED §6) — "44" devenait ["4", "4"]
        if not isinstance(wanted, list) or not wanted or not rp:
            return None, "numbers: 'report_prompt' et 'numbers' (liste non vide) requis"
        if len(data) > MAX_DATA_CHARS:
            return None, f"numbers: data > {MAX_DATA_CHARS} caractères"
        wanted_s = [str(n) for n in wanted]
        contract = {"data": data, "numbers": wanted_s}

        def gate(out):
            miss = [n for n in wanted_s
                    if not re.search(rf"(?<!\d){re.escape(n)}(?!\d)", out)]
            if miss:
                return False, f"nombres manquants dans le rapport : {miss}"
            for m in rb.NUM_RE.findall(out):
                # garde alphanum (celle du banc) : le chiffre d'un identifiant
                # (« le 51 de fable51 ») n'est pas un nombre récitable
                if not re.search(rf"(?<![A-Za-z0-9_]){re.escape(m)}(?![A-Za-z0-9_])", data):
                    return False, f"nombre absent des Données (inventé ?): {m}"
            return True, ""

        prompt = (f"Données :\n{data}\n\n{rp}\nRécite exactement les nombres demandés tels "
                  f"qu'ils figurent dans les Données. N'écris AUCUN nombre qui n'y figure pas.")
        return contract, prompt, gate, lambda d: (
            f"Le vérificateur a rejeté ton rapport : {d}. Récite exactement les nombres "
            f"{wanted_s} depuis les Données, supprime tout nombre absent des Données."), 600

    if ty == "diff":
        a, b = t.get("a", ""), t.get("b", "")
        # bornes d'entrée (CHANGES_REQUESTED §6) : même garde que data
        if not isinstance(a, str) or not isinstance(b, str) \
                or len(a) > MAX_DATA_CHARS or len(b) > MAX_DATA_CHARS:
            return None, f"diff: 'a' et 'b' = chaînes JSON ≤{MAX_DATA_CHARS} caractères"
        try:
            ja, jb = json.loads(a), json.loads(b)
        except Exception as exc:
            return None, f"diff: a et b doivent être du JSON parsable ({exc})"
        diff = top_diff(ja, jb)
        src = json.dumps(ja, ensure_ascii=False) + "\n" + json.dumps(jb, ensure_ascii=False)
        if not diff:
            return None, "diff: aucun écart entre a et b (rien à rapporter)"
        contract = {"diff": diff, "source": src}
        lines = "\n".join(f"- {k} : A={json.dumps(v[0], ensure_ascii=False)} / "
                          f"B={json.dumps(v[1], ensure_ascii=False)}"
                          for k, v in diff.items())
        prompt = (f"Diff calculé par outil entre la config A et la config B :\n{lines}\n\n"
                  f"Rédige un rapport court (2 à 5 phrases) qui cite CHAQUE clé divergente "
                  f"avec ses deux valeurs. Sans clé ni valeur inventée.")
        return contract, prompt, \
            lambda out: rb.CHECKERS["report"](out, contract), \
            lambda d: (f"Le vérificateur a rejeté ton rapport : {d}. Cite CHAQUE clé "
                       f"divergente du diff fourni avec ses deux valeurs, en 2 à 5 phrases, "
                       f"sans clé ni valeur inventée."), 1000

    return None, f"type inconnu: {ty!r} (extract|classify|numbers|diff)"


# ---------------------------------------------------------------- chaîne A→C

COORD_NOTE = ("\n\n(Les tentatives précédentes d'un modèle plus petit ont toutes été rejetées "
              "par un vérificateur mécanique. Réponds au format exact demandé, rien d'autre.)")


def clean_answer(out):
    """Le 1.7B « réfléchit en prose » : ne livrer que la partie après le bloc
    de raisonnement quand il y en a un (mesuré : rapport final correct mais
    noyé après un pavé de brouillon)."""
    return out.split("</think>")[-1].strip() if "</think>" in out else out.strip()


def run_classify(t):
    """Classify en DEUX appels préremplis, un champ chacun. Sur un prompt
    combiné, le 1.7B délibère en prose et n'émet jamais le JSON (mesuré 20/11 :
    3/3 escalades en stage c, max_tokens épuisé en raisonnement) ; prérempli,
    il complète mécaniquement. La preuve est LIÉE au verdict : l'étape B
    reçoit la classe choisie en A et copie la ligne qui la justifie — gate
    inchangé (classe ∈ taxonomie, ligne_cle verbatim ≥8)."""
    built = build_contract(t)
    if isinstance(built, tuple) and built[0] is None and len(built) == 2:
        return {"ok": False, "stage": "reject", "answer": "", "detail": built[1],
                "turns": 0, "dt_s": 0.0}
    contract, prompt, gate, feedback, _ = built
    data, classes = contract["data"], contract["classes"]
    t0 = time.time()

    # définitions optionnelles (axe consommateur claudish-cd 20/11 : confusion
    # fondations=def réutilisable vs exercice=consigne à compléter = 60-75 %
    # de précision fine sans elles). Injectées comme contexte, la gate reste
    # inchangée (classe ∈ taxonomie, preuve verbatim).
    defs = t.get("class_definitions")
    defs_ctx = ""
    if isinstance(defs, dict) and defs:
        defs_ctx = "\n".join(f"- {k} : {v}" for k, v in defs.items()) + "\n"
        # borne d'entrée (CHANGES_REQUESTED §6) : les définitions sont du
        # contexte, pas un corpus — même famille de garde que data
        if len(defs_ctx) > MAX_DEFS_CHARS:
            return {"ok": False, "stage": "reject", "answer": "",
                    "detail": f"classify: class_definitions > {MAX_DEFS_CHARS} "
                    "caractères sérialisés", "turns": 0, "dt_s": 0.0}

    ok_engine, msg = ensure_engine()
    if not ok_engine:
        return {"ok": False, "stage": "engine-down", "answer": "", "detail": msg,
                "turns": 0, "dt_s": round(time.time() - t0, 2)}

    pre_classe = '{"classe": "'
    p_a = (f"Texte :\n{data}\n\nClasse ce texte dans EXACTEMENT une de ces "
           f"classes : {classes}.\n{defs_ctx}")
    # defs APRÈS la taxonomie, jamais au-dessus du Texte (mesuré 20/11 : en
    # amont, l'étape B recopiait la ligne de la définition — absente de data —
    # → gate rejette → stage c ×4)
    turns, classe, ligne, out_a = 0, "", "", ""
    try:
        turns += 1
        out_a = chat(ENGINE_URL, ENGINE_MODEL, [{"role": "user", "content": p_a}],
                     max_tokens=60, prefill=pre_classe)
        objs = rb.extract_json_objs(pre_classe + out_a)
        if objs:
            classe = str(objs[0].get("classe", ""))
    except Exception as exc:
        return {"ok": False, "stage": "engine-error", "answer": "",
                "detail": f"étape classe: appel engine échoué: {exc!r}",
                "turns": turns, "dt_s": round(time.time() - t0, 2)}

    def step_b(extra=""):
        p_b = (f"Texte :\n{data}\n\nCe texte relève de la classe {classe}. "
               f"Recopie la ligne qui justifie le mieux cette classe "
               f"(au moins 8 caractères ; s'il y a le choix, la plus diagnostique "
               f"et longue), mot pour mot, sans rien changer.\n"
               f"Réponds UNIQUEMENT cette ligne.{extra}")
        # ancre BRUTE (pas de contexte JSON) : la complétion n'a aucun
        # échappement à réussir, la première ligne EST la copie — mesuré 20/11 :
        # l'ancre JSON faisait échouer l'échappement sur une part des lignes C#
        out = chat(ENGINE_URL, ENGINE_MODEL, [{"role": "user", "content": p_b}],
                   max_tokens=200, prefill="LIGNE : ")
        return out.split("\n")[0].strip()

    try:
        turns += 1
        ligne = step_b()
        if not ligne:  # A avait parfois déjà les deux champs — repli
            objs = rb.extract_json_objs(pre_classe + out_a)
            if objs:
                ligne = str(objs[0].get("ligne_cle", ""))
    except Exception:
        ligne = ""

    combined = json.dumps({"classe": classe, "ligne_cle": ligne}, ensure_ascii=False)
    ok, detail = gate(combined)
    stage = "a"
    # réparation dirigée : on relance l'ÉTAPE fautive avec le delta signé
    while not ok and turns - 2 < MAX_REPAIR_ROUNDS:
        turns += 1
        try:
            if "taxonomie" in detail:
                out = chat(ENGINE_URL, ENGINE_MODEL,
                           [{"role": "user", "content": p_a + "\n" + feedback(detail)}],
                           max_tokens=60, prefill=pre_classe)
                objs = rb.extract_json_objs(pre_classe + out)
                if objs:
                    classe = str(objs[0].get("classe", ""))
            else:
                ligne = step_b("\n" + feedback(detail))
        except Exception:
            pass
        combined = json.dumps({"classe": classe, "ligne_cle": ligne},
                              ensure_ascii=False)
        ok, detail = gate(combined)

    if ok:
        return {"ok": True, "stage": "a", "answer": combined, "detail": "",
                "turns": turns, "dt_s": round(time.time() - t0, 2)}

    # --- phase C : coordinateur hub sur le prompt combiné original, re-gaté.
    # stage/turns ne marquent QUE si l'appel a réellement eu lieu (complément
    # relecture ai-01 : posés avant le test de clé, ils étiquetaient "c" une
    # phase qui n'a pas tourné et gonflaient la métrique appels/tâche).
    coord_note = ""
    stage = "a"
    if HUB_KEY and HUB_URL:
        stage = "c"
        turns += 1
        try:
            out = clean_answer(chat(HUB_URL, HUB_MODEL,
                                    [{"role": "user", "content": prompt + COORD_NOTE}],
                                    max_tokens=3000, timeout=300, api_key=HUB_KEY))
            ok, detail = gate(out)
            return {"ok": ok, "stage": stage, "answer": clean_answer(out),
                    "detail": detail, "turns": turns,
                    "dt_s": round(time.time() - t0, 2)}
        except Exception as exc:
            detail = f"worker 2-étapes échoué ({detail}); coordinateur hub échoué: {exc!r}"
    else:
        coord_note = " (coordinateur indisponible: ZAI_API_KEY ou VOLTRON_HUB_URL absent au démarrage)"
    return {"ok": False, "stage": stage, "answer": combined,
            "detail": detail + coord_note, "turns": turns,
            "dt_s": round(time.time() - t0, 2)}


def run_task(t):
    """Chaîne complète pour UNE tâche. Retourne le dict de réponse du service."""
    if t.get("type") == "classify":
        return run_classify(t)
    built = build_contract(t)
    if isinstance(built, tuple) and built[0] is None and len(built) == 2:
        return {"ok": False, "stage": "reject", "answer": "", "detail": built[1],
                "turns": 0, "dt_s": 0.0}
    contract, prompt, gate, feedback, max_tokens = built
    t0 = time.time()

    ok_engine, msg = ensure_engine()
    if not ok_engine:
        return {"ok": False, "stage": "engine-down", "answer": "", "detail": msg,
                "turns": 0, "dt_s": round(time.time() - t0, 2)}

    # --- phase A : worker local + réparation dirigée (delta signé, jamais la réponse)
    # Le gate porte TOUJOURS la réponse nettoyée : on certifie ce qu'on livre
    # (mesuré 18/11 : clé citée dans le brouillon de raisonnement mais absente
    # du livrable final → svc OK / vérité FAIL).
    msgs = [{"role": "user", "content": prompt}]
    pre = PREFILLS.get(t.get("type"))
    try:
        out = clean_answer(chat(ENGINE_URL, ENGINE_MODEL, msgs,
                                max_tokens=max_tokens, prefill=pre))
    except Exception as exc:
        return {"ok": False, "stage": "engine-error", "answer": "",
                "detail": f"appel engine échoué: {exc!r}", "turns": 0,
                "dt_s": round(time.time() - t0, 2)}
    ok, detail = gate((pre or "") + out)
    turns = 1
    stage = "a"
    while not ok and turns <= MAX_REPAIR_ROUNDS:
        msgs.append({"role": "assistant", "content": (pre or "") + out})
        msgs.append({"role": "user", "content": feedback(detail)})
        out = clean_answer(chat(ENGINE_URL, ENGINE_MODEL, msgs,
                                max_tokens=max_tokens, prefill=pre))
        ok, detail = gate((pre or "") + out)
        turns += 1

    # --- phase C : coordinateur hub, prompt SEC (mesuré : les brouillons du 1.7B
    # polluent le 27B), réponse re-gatée comme les autres.
    coord_note = ""
    if not ok and HUB_KEY and HUB_URL:
        stage = "c"
        turns += 1
        try:
            out = clean_answer(chat(HUB_URL, HUB_MODEL,
                                    [{"role": "user", "content": prompt + COORD_NOTE}],
                                    max_tokens=3000, timeout=300, api_key=HUB_KEY))
            ok, detail = gate(out)
        except Exception as exc:
            detail = f"résiduel après worker (phase A échouée: {detail}); coordinateur hub échoué: {exc!r}"
    elif not ok:
        coord_note = " (coordinateur indisponible: ZAI_API_KEY ou VOLTRON_HUB_URL absent au démarrage du serveur)"

    ans = clean_answer(out)
    if ok and t.get("type") == "extract":
        # livrer le JSON parsé, pas la prose autour (le 1.7B l'enveloppe
        # parfois de délibération — objs[0] EST le livrable). Le préfixe de
        # préremplissage doit être recollé AVANT parse ; le repli nu couvre
        # une sortie de coordinateur (stage c, jamais préremplie).
        objs = rb.extract_json_objs((pre or "") + ans) or rb.extract_json_objs(ans)
        if objs:
            ans = json.dumps(objs[0], ensure_ascii=False)
    return {"ok": ok, "stage": stage, "answer": ans,
            "detail": detail + coord_note,
            "turns": turns, "dt_s": round(time.time() - t0, 2)}


def _run_tasks(job_id, idx_tasks, count_usage=True):
    """Exécute un SOUS-ENSEMBLE (index, tâche) d'un job — plein ou reprise.
    Concurrence : le moteur tient N=64 (3 673 t/s mesurés) alors qu'un job
    séquentiel plafonne à ~1 req — 5 586 tâches = des heures vs ~15 min (20/11).
    count_usage=False sur la REPRISE (CHANGES_REQUESTED §4) : une tâche relancée
    ne re-bump pas tasks_total — le compteur d'adoption compte des exécutions
    complétées une fois, pas des tentatives."""
    job = _jobs[job_id]

    def one(i_t):
        i, t = i_t
        try:
            if not isinstance(t, dict):
                raise ValueError(
                    f"objet JSON attendu, reçu {type(t).__name__} — contrat §2")
            res = run_task(t)
            if count_usage:
                _bump_usage(t.get("type", "?"), res.get("ok"), via_job=True)
        except Exception as exc:  # une tâche ne tue JAMAIS le job — même
            # malformée : elle devient un résultat d'erreur consultable, les
            # autres avancent (mesuré 21/11 : un str dans le lot gelait le
            # pool entier via ex.map, job 'running' à vie)
            res = {"ok": False, "stage": "error", "answer": "",
                   "detail": f"exécution tâche {i}: {exc!r}", "turns": 0, "dt_s": 0.0}
        res["task"] = i
        with _jobs_lock:
            job["results"].append(res)
            job["done"] += 1
        # CHANGES_REQUESTED §1 : la persistance ne doit JAMAIS casser le pool —
        # un échec d'écriture se loggue, le résultat reste en mémoire et la
        # persistance suivante reprend l'état complet.
        try:
            _persist(job_id)
        except Exception as exc:
            print(f"[persist] job {job_id}: écriture échouée ({exc!r}) — "
                  f"état conservé en mémoire", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=JOB_CONCURRENCY) as ex:
        list(ex.map(one, idx_tasks))
    # finalisation dans le CHEMIN PARTAGÉ : vrai pour un job complet (run_job)
    # comme pour une reprise (le sous-ensemble restant achève le job).
    with _jobs_lock:
        if job["done"] >= job["total"]:
            job["status"] = "done"
    _persist(job_id)


def run_job(job_id):
    _run_tasks(job_id, list(enumerate(_jobs[job_id]["tasks"])))


_persist_lock = threading.Lock()
_persist_seq = 0


def _persist(job_id):
    # La CHARGE est persistée aussi (depuis la reprise 21/11) : c'est elle qui
    # rend un job interrompu relançable. Écriture atomique tmp+replace — un
    # serveur tué mi-écriture ne laisse pas de JSON tronqué.
    # CHANGES_REQUESTED §1 (bloquant) : jusqu'à JOB_CONCURRENCY threads
    # persistent le MÊME job — sérialisation par verrou dédié + tmp À NOM
    # UNIQUE par écriture (un tmp partagé produisait du JSON entrelacé via
    # os.replace, ou un PermissionError Windows en remplaçant un tmp encore
    # ouvert) + snapshot des résultats sous _jobs_lock (un append concurrent
    # pendant json.dump lèverait « list changed size during iteration »).
    global _persist_seq
    os.makedirs(JOBS_DIR, exist_ok=True)
    with _persist_lock:
        # Snapshot DANS _persist_lock (re-review 22/11 : pris avant, deux
        # threads pouvaient écrire à rebours — le fichier régressait d'un
        # résultat). Ordre _persist_lock -> _jobs_lock sûr : rien ne tient
        # _jobs_lock en appelant _persist (vérifié ligne par ligne en review).
        with _jobs_lock:
            job = dict(_jobs[job_id])
            job["results"] = list(job["results"])
        _persist_seq += 1
        tmp = os.path.join(JOBS_DIR, f"{job_id}.{threading.get_ident()}-"
                                     f"{_persist_seq}.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(job, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, os.path.join(JOBS_DIR, f"{job_id}.json"))


def _wait_engine(timeout_s=300):
    """Reprise : l'engine partage souvent la fenêtre de redémarrage (reboot
    hôte) — boot mesuré 115-150 s, on attend 300 s avant de brûler les tâches."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(f"{ENGINE_URL}/health", timeout=5) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(5)
    return False


def _recover_orphans():
    """Reprise après restart serveur (mandat « tâches longues en background ») :
    un job 'running' SUR DISQUE est un job dont le thread est mort — le statut
    ment. Les résultats déjà faits sont gardés, les tâches restantes sont
    RELANCÉES. Les fichiers d'avant la reprise (sans 'tasks') deviennent
    'orphaned' : terminal honnête, le consommateur re-POST."""
    if not os.path.isdir(JOBS_DIR):
        return
    for fn in sorted(os.listdir(JOBS_DIR)):
        if not fn.endswith(".json"):
            continue
        jid = fn[:-5]
        try:
            with open(os.path.join(JOBS_DIR, fn), encoding="utf-8") as f:
                job = json.load(f)
        except Exception as exc:
            print(f"[reprise] {fn} illisible ({exc!r}) — ignoré, pas supprimé",
                  flush=True)
            continue
        if job.get("status") != "running":
            continue
        with _jobs_lock:
            _jobs[jid] = job
        if "tasks" not in job:  # pré-reprise : charge jamais persistée
            job["status"] = "orphaned"
            job["orphaned_at"] = datetime.now(timezone.utc).isoformat()
            _persist(jid)
            print(f"[reprise] {jid}: sans charge -> orphaned (re-POST conseillé)",
                  flush=True)
            continue
        done_idx = {r.get("task") for r in job.get("results", [])}
        pending = [(i, t) for i, t in enumerate(job["tasks"]) if i not in done_idx]
        if not pending:  # tué entre dernière tâche et finalisation
            job["status"] = "done"
            _persist(jid)
            print(f"[reprise] {jid}: déjà complet -> finalisé", flush=True)
            continue
        _wait_engine()
        job["recovered"] = job.get("recovered", 0) + 1
        _persist(jid)
        # count_usage=False : les tâches relancées ne re-bumpent pas le
        # compteur d'adoption (CHANGES_REQUESTED §4 — la direction prudente
        # pour un instrument de mesure : sous-compter, jamais sur-compter)
        threading.Thread(target=_run_tasks, args=(jid, pending),
                         kwargs={"count_usage": False}, daemon=True).start()
        print(f"[reprise] {jid}: {len(pending)}/{job.get('total', '?')} tâches "
              f"relancées (recovery #{job['recovered']})", flush=True)


# ------------------------------------------------- compteur d'usage durable

_usage_lock = threading.Lock()


def _usage():
    """Compteurs persistés — l'instrument de mesure d'ADOPTION (usage réel,
    survit aux restarts serveur ET engine). Lecture tolérante (affichage)."""
    u, _ = _load_usage()
    if u is None:
        return {"tasks_total": 0, "ok": 0, "by_type": {}, "jobs_total": 0,
                "job_tasks": 0, "first": datetime.now(timezone.utc).isoformat(),
                "last": None}
    return u


def _load_usage():
    """(dict|None, writable) — writable=False : fichier PRÉSENT mais illisible ;
    l'appelant doit refuser d'écrire plutôt que repartir de zéro
    (CHANGES_REQUESTED §3 : c'est l'historique d'adoption, un dict à zéro
    l'écraserait au bump suivant). None+writable = premier boot légitime."""
    try:
        with open(USAGE_PATH, encoding="utf-8") as f:
            return json.load(f), True
    except FileNotFoundError:
        return None, True
    except Exception as exc:
        print(f"[usage] {USAGE_PATH} illisible ({exc!r}) — écriture REFUSÉE, "
              f"l'historique n'est pas écrasé", flush=True)
        return None, False


def _bump_usage(ttype, ok, job=False, via_job=False):
    """+1 tâche (ou +1 job si job=True) — écriture atomique tmp+fsync+replace."""
    with _usage_lock:
        u, writable = _load_usage()
        if not writable:
            return None
        if u is None:
            u = {"tasks_total": 0, "ok": 0, "by_type": {}, "jobs_total": 0,
                 "job_tasks": 0, "first": datetime.now(timezone.utc).isoformat(),
                 "last": None}
        if job:
            u["jobs_total"] = u.get("jobs_total", 0) + 1
        else:
            u["tasks_total"] = u.get("tasks_total", 0) + 1
            if via_job:
                u["job_tasks"] = u.get("job_tasks", 0) + 1
            bt = u["by_type"].setdefault(str(ttype), {"n": 0, "ok": 0})
            bt["n"] += 1
            bt["ok"] += int(bool(ok))
            u["ok"] = u.get("ok", 0) + int(bool(ok))
        u["last"] = datetime.now(timezone.utc).isoformat()
        os.makedirs(os.path.dirname(USAGE_PATH), exist_ok=True)
        tmp = f"{USAGE_PATH}.{threading.get_ident()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(u, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, USAGE_PATH)
        return u


# ---------------------------------------------------------------- HTTP

CAPABILITIES = {
    "service": "harnais voltron — une requête, une réponse déjà gatée",
    "chain": "A worker voltron-1.7B (réparation ≤2 tours, delta signé) → C coordinateur swift-1.5-27b (hub) ; "
             "chaque sortie re-gatée par le contrat de l'appelant",
    "endpoints": {
        "POST /v1/task": {"type": "extract|classify|numbers|diff", "...": "voir types"},
        "POST /v1/jobs": {"tasks": ["<task>..."], "name": "optionnel"},
        "GET /v1/jobs/<id>": "statut + résultats (persistés, REPRIS au restart serveur — "
                             "les tâches restantes d'un job interrompu sont relancées au boot)",
        "GET /v1/usage": "compteurs d'usage DURABLES (survivent aux restarts) — l'instrument d'adoption",
        "GET /health": "engine + hub + serveur",
        "GET /v1/capabilities": "ce document"},
    "types": {
        "extract": {"champs": "data (≤20000 chars), fields [str], verbatim (défaut true), "
                              "instruction (la sémantique de l'extraction, ex. « la catégorie "
                              "à la PLUS BASSE accuracy » — mesuré : sans elle, valeurs "
                              "verbatim mais hors-sujet)",
                    "gate": "JSON exact à ces clés ; valeurs chaînes verbatim de la source"},
        "classify": {"champs": "data, classes [str] ; class_definitions {classe: definition} "
                               "OPTIONNEL (désambiguïsation fine — axe consommateur 20/11)",
                     "gate": "classe dans la taxonomie ; ligne_cle verbatim ≥8 chars"},
        "numbers": {"champs": "data, report_prompt, numbers [str|int]",
                    "gate": "chaque nombre cité (bornes digits) ; aucun nombre inventé"},
        "diff": {"champs": "a, b (JSON tous deux)",
                 "gate": "l'OUTIL calcule le diff de PREMIER niveau (top_diff) ; le modèle "
                         "rédige le rapport (chaque clé divergente + deux valeurs ; valeurs "
                         ">60 chars exemptées de citation verbatim)"}},
    "refuse": "verdicts/jugements, sorties non gatées, data >20000 chars — cf. docs/voltron-harness-adoption.md",
    "mesures": "banc real_task_bench : chaîne complète 40/40 ; service A→C documenté dans docs/voltron-harness-adoption.md",
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%SZ')}] {fmt % args}", flush=True)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"server": "up", "engine": engine_healthy(),
                             "hub_key": bool(HUB_KEY), "jobs": len(_jobs),
                             "engine_url": ENGINE_URL})
        elif self.path in ("/", "/v1/capabilities"):
            # "/" sert les capacités : premier réflexe d'un consommateur (mesuré,
            # claudish-cd 20/11 — un 404 "route inconnue" à la racine est une friction)
            self._send(200, CAPABILITIES)
        elif self.path == "/v1/usage":
            with _usage_lock:
                self._send(200, _usage())
        elif self.path.startswith("/v1/jobs/"):
            jid = self.path.split("/", 3)[3]
            # CHANGES_REQUESTED §5 : valider le format AVANT tout os.path.join
            # (un jid forgé ne traverse pas vers le disque)
            if not re.fullmatch(r"job-\d{8}T\d{6}Z-[0-9a-f]{6}", jid):
                self._send(400, {"error": "identifiant de job malformé"})
                return
            with _jobs_lock:
                job = _jobs.get(jid)
            if not job:
                # relire depuis le disque (serveur redémarré)
                p = os.path.join(JOBS_DIR, f"{jid}.json")
                if os.path.exists(p):
                    with open(p, encoding="utf-8") as f:
                        job = json.load(f)
            if not job:
                self._send(404, {"error": f"job inconnu: {jid}"})
            else:
                view = {k: v for k, v in job.items() if k != "tasks"}
                self._send(200, view)
        else:
            self._send(404, {"error": "route inconnue"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if length < 0:  # re-review 22/11 : read(-1) lit jusqu'à l'EOF
            self._send(400, {"error": "Content-Length négatif"})
            return
        if length > MAX_BODY_BYTES:  # CHANGES_REQUESTED §6 : corps borné
            self._send(413, {"error": f"corps > {MAX_BODY_BYTES} octets"})
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception as exc:
            self._send(400, {"error": f"JSON invalide: {exc}"})
            return
        if self.path == "/v1/task":
            res = run_task(body)
            _bump_usage(body.get("type", "?"), res.get("ok"))
            self._send(200, res)
        elif self.path == "/v1/jobs":
            tasks = body.get("tasks")
            if not isinstance(tasks, list) or not tasks:
                self._send(400, {"error": "'tasks' = liste non vide requis"})
                return
            _bump_usage(None, None, job=True)
            jid = f"job-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
            with _jobs_lock:
                _jobs[jid] = {"status": "running", "name": body.get("name", ""),
                              "total": len(tasks), "done": 0, "results": [],
                              "tasks": tasks,
                              "created": datetime.now(timezone.utc).isoformat()}
            _persist(jid)  # la charge est sur disque AVANT le premier tour —
            # un kill immédiat reste reprisable (reprise au boot, 21/11)
            threading.Thread(target=run_job, args=(jid,), daemon=True).start()
            self._send(200, {"job_id": jid, "total": len(tasks)})
        else:
            self._send(404, {"error": "route inconnue"})


def main():
    print(f"harnais serveur sur 127.0.0.1:{PORT} — engine {ENGINE_URL}, "
          f"hub {HUB_URL or '(VOLTRON_HUB_URL absent)'} "
          f"({'clé OK' if HUB_KEY else 'SANS clé → phase C désactivée'})",
          flush=True)
    # BIND AVANT REPRISE (complément relecture ai-01) : le bind qui échoue
    # garantit l'instance unique — un second lancement meurt ici au lieu de
    # relancer les jobs 'running' du disque en double exécution.
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    _recover_orphans()  # instance unique acquise : reprendre, puis servir
    srv.serve_forever()


if __name__ == "__main__":
    main()
