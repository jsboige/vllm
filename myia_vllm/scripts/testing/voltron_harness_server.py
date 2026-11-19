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
persistée sur disque) ; GET /v1/jobs/<id> pour suivre.

Auto-guérison : si l'engine :5028 est muet, `docker start voltron-harness`
puis attente santé ≤240 s. Bind 127.0.0.1:5029 — usage local machine,
même politique que l'engine d'éval (keyless, boucle locale).

Clé hub : env ZAI_API_KEY au lancement du serveur (résolue en mémoire par
start_voltron_service.ps1 depuis ~/.claude.json, jamais écrite sur disque).
Absent → phase C sautée, la réponse porte stage="a" + note.
"""
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
HUB_URL = "http://192.168.0.50:3000"  # chat() ajoute /v1/chat/completions
HUB_MODEL = "swift-1.5-27b"
PORT = 5029
JOBS_DIR = r"D:\vllm-data\bench\v2_jobs"
USAGE_PATH = r"D:\vllm-data\bench\v2_usage.json"  # compteur DURABLE (piège po-2025 :
# les compteurs engine avancent en fin de requête et repartent à zéro au boot —
# l'instrument d'adoption doit survivre aux restarts)
MAX_DATA_CHARS = 20000  # garde contexte 32K : data + prompt + réponse
MAX_REPAIR_ROUNDS = 2
HUB_KEY = os.environ.get("ZAI_API_KEY")  # figé au démarrage du serveur

_jobs_lock = threading.Lock()
_jobs = {}  # id -> dict(status, name, total, done, results)


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
            if len(ev) < 15 or ev not in data:
                return False, "ligne_cle introuvable mot pour mot dans le texte (ou <15 caractères)"
            return True, ""

        prompt = (f"Texte :\n{data}\n\nClasse ce texte dans EXACTEMENT une de ces classes : "
                  f"{classes}. Renvoie UNIQUEMENT un JSON {{\"classe\": ..., \"ligne_cle\": ...}} "
                  f"où ligne_cle est la ligne la plus diagnostique du texte, recopiée mot pour "
                  f"mot (au moins 15 caractères).")
        return contract, prompt, gate, lambda d: (
            f"Classe incorrecte ou preuve invalide : {d}. Classes autorisées : {classes}. "
            f"Renvoie le JSON corrigé, ligne_cle recopiée mot pour mot depuis le Texte."), 400

    if ty == "numbers":
        data, wanted = t.get("data", ""), t.get("numbers")
        rp = t.get("report_prompt", "")
        if not wanted or not rp:
            return None, "numbers: 'report_prompt' et 'numbers' (liste) requis"
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


def run_task(t):
    """Chaîne complète pour UNE tâche. Retourne le dict de réponse du service."""
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
    try:
        out = clean_answer(chat(ENGINE_URL, ENGINE_MODEL, msgs, max_tokens=max_tokens))
    except Exception as exc:
        return {"ok": False, "stage": "engine-error", "answer": "",
                "detail": f"appel engine échoué: {exc!r}", "turns": 0,
                "dt_s": round(time.time() - t0, 2)}
    ok, detail = gate(out)
    turns = 1
    stage = "a"
    while not ok and turns <= MAX_REPAIR_ROUNDS:
        msgs.append({"role": "assistant", "content": out})
        msgs.append({"role": "user", "content": feedback(detail)})
        out = clean_answer(chat(ENGINE_URL, ENGINE_MODEL, msgs, max_tokens=max_tokens))
        ok, detail = gate(out)
        turns += 1

    # --- phase C : coordinateur hub, prompt SEC (mesuré : les brouillons du 1.7B
    # polluent le 27B), réponse re-gatée comme les autres.
    coord_note = ""
    if not ok and HUB_KEY:
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
        coord_note = " (coordinateur indisponible: ZAI_API_KEY absent au démarrage du serveur)"

    return {"ok": ok, "stage": stage, "answer": clean_answer(out),
            "detail": detail + coord_note,
            "turns": turns, "dt_s": round(time.time() - t0, 2)}


def run_job(job_id):
    job = _jobs[job_id]
    for i, t in enumerate(job["tasks"]):
        res = run_task(t)
        res["task"] = i
        _bump_usage(t.get("type", "?"), res.get("ok"), via_job=True)
        with _jobs_lock:
            job["results"].append(res)
            job["done"] = i + 1
        _persist(job_id)
    with _jobs_lock:
        job["status"] = "done"
    _persist(job_id)


def _persist(job_id):
    os.makedirs(JOBS_DIR, exist_ok=True)
    job = dict(_jobs[job_id])
    job.pop("tasks", None)  # la charge n'est pas re-persistée, les résultats oui
    with open(os.path.join(JOBS_DIR, f"{job_id}.json"), "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=1)


# ------------------------------------------------- compteur d'usage durable

_usage_lock = threading.Lock()


def _usage():
    """Compteurs persistés — l'instrument de mesure d'ADOPTION (usage réel,
    survit aux restarts serveur ET engine)."""
    try:
        with open(USAGE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"tasks_total": 0, "ok": 0, "by_type": {}, "jobs_total": 0,
                "job_tasks": 0, "first": datetime.now(timezone.utc).isoformat(),
                "last": None}


def _bump_usage(ttype, ok, job=False, via_job=False):
    """+1 tâche (ou +1 job si job=True) — écriture atomique tmp+replace."""
    with _usage_lock:
        u = _usage()
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
        tmp = USAGE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(u, f, ensure_ascii=False, indent=1)
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
        "GET /v1/jobs/<id>": "statut + résultats (persistés sur disque)",
        "GET /v1/usage": "compteurs d'usage DURABLES (survivent aux restarts) — l'instrument d'adoption",
        "GET /health": "engine + hub + serveur",
        "GET /v1/capabilities": "ce document"},
    "types": {
        "extract": {"champs": "data (≤20000 chars), fields [str], verbatim (défaut true), "
                              "instruction (la sémantique de l'extraction, ex. « la catégorie "
                              "à la PLUS BASSE accuracy » — mesuré : sans elle, valeurs "
                              "verbatim mais hors-sujet)",
                    "gate": "JSON exact à ces clés ; valeurs chaînes verbatim de la source"},
        "classify": {"champs": "data, classes [str]",
                     "gate": "classe dans la taxonomie ; ligne_cle verbatim ≥15 chars"},
        "numbers": {"champs": "data, report_prompt, numbers [str|int]",
                    "gate": "chaque nombre cité (bornes digits) ; aucun nombre inventé"},
        "diff": {"champs": "a, b (JSON tous deux)",
                 "gate": "l'OUTIL calcule le diff profond ; le modèle rédige le rapport "
                         "(chaque clé divergente + deux valeurs ; valeurs >60 chars exemptées "
                         "de citation verbatim)"}},
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
        elif self.path == "/v1/capabilities":
            self._send(200, CAPABILITIES)
        elif self.path == "/v1/usage":
            with _usage_lock:
                self._send(200, _usage())
        elif self.path.startswith("/v1/jobs/"):
            jid = self.path.split("/", 3)[3]
            with _jobs_lock:
                job = _jobs.get(jid)
            if not job:
                # relire depuis le disque (serveur redémarré)
                p = os.path.join(JOBS_DIR, f"{jid}.json")
                if os.path.exists(p):
                    job = json.load(open(p, encoding="utf-8"))
            if not job:
                self._send(404, {"error": f"job inconnu: {jid}"})
            else:
                view = {k: v for k, v in job.items() if k != "tasks"}
                self._send(200, view)
        else:
            self._send(404, {"error": "route inconnue"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
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
            threading.Thread(target=run_job, args=(jid,), daemon=True).start()
            self._send(200, {"job_id": jid, "total": len(tasks)})
        else:
            self._send(404, {"error": "route inconnue"})


def main():
    print(f"harnais serveur sur 127.0.0.1:{PORT} — engine {ENGINE_URL}, "
          f"hub {HUB_URL} ({'clé OK' if HUB_KEY else 'SANS clé → phase C désactivée'})",
          flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
