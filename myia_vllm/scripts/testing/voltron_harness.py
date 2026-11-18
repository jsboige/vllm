#!/usr/bin/env python3
"""voltron_harness.py — harnais de fiabilisation voltron-1-mini (mandat user 18/11).

Basis: quality_bench baseline 88/120 = 73.3 % (fp8, 17/11). Per-class:
  extract/json/grounded 100 % · sort/transform 93 % · constraint 60 %
  (anchored canned phrase) · arith 27 % / count 13 % (computation drift).

Design (user spec: siblings verify siblings, a smarter coordinator gates and
mandates corrections CHEAPLY — deterministic first, model tokens last):

  1. Adaptive routing by MEASURED class reliability:
     - green  (100 %): 1 call, structural gate only            -> 1x tokens
     - ok     ( 93 %): 3 siblings, majority on normalized output -> 3x
     - yellow ( 60 %): 1 call + deterministic gate (word count) + up to 2
                        DIRECTED repairs (feedback says +/- how many words)
     - red    (< 30 %): EXECUTION PIVOT — 3 siblings each produce a Python
                        EXPRESSION; the harness evals it sandboxed; majority
                        is computed on VALUES, not on text          -> 3x
  2. Repair rounds carry exact gate feedback ("6 mots lu, 7 attendu").
  3. Coordinator hook (v0: deterministic arbitration only; v1: FrogNano-4B
     via sk-agent / HTTP, bounded max_tokens, only on: no-majority after
     repair, or unfixable constraint) — never rewrites full output.
  4. Refusal is a valid output: after max rounds with gate still failing,
     the harness emits "REFUS: <reason>" (correctness-preserving in prod).

Same 120 tasks / oracles as the baseline (imports quality_bench_po2025),
so the harness run is directly comparable: 88/120 is the number to beat.

Usage:
  python voltron_harness.py --label harness-v0            # engine :5028
  python voltron_harness.py --label harness-v0 --dry-run  # no engine needed
"""
import argparse
import ast
import json
import operator as op
import os
import re
import statistics
import sys
import time
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import quality_bench_po2025 as qb  # noqa: E402  (same 120 tasks + scorer)

MAX_TOKENS = 320
MAX_REPAIRS = 2

# --- sibling framings: independent minds, same model ----------------------
# S1 neutral temp 0 · S2 meticulous persona temp 0 · S3 neutral temp 0.3
SIBLINGS = [
    {"id": "s1", "system": None, "temperature": 0.0},
    {"id": "s2", "system": "Tu es un assistant méticuleux. Vérifie ta réponse avant de l'écrire.", "temperature": 0.0},
    {"id": "s3", "system": None, "temperature": 0.3},
]

ROUTE = {  # from the measured baseline, not from vibes
    "extract": "green", "json": "green", "grounded": "green",
    "sort": "ok", "transform": "ok",
    "constraint": "yellow",
    "arith": "red", "count": "red",
}

# --- sandboxed expression evaluation (arith/count pivot) ------------------
_BINOPS = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
           ast.FloorDiv: op.floordiv, ast.Mod: op.mod}
_ALLOWED_METHODS = {"count", "find", "index"}


def safe_eval(expr: str, bindings: dict):
    """Evaluate a whitelisted arithmetic/counting expression. Raises on anything else."""
    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, str)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            return _BINOPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            v = ev(node.operand)
            return v if isinstance(node.op, ast.UAdd) else -v
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id == "len" and len(node.args) == 1:
                return len(ev(node.args[0]))
            if isinstance(f, ast.Attribute) and f.attr in _ALLOWED_METHODS:
                target = ev(f.value)
                args = [ev(a) for a in node.args]
                return getattr(target, f.attr)(*args)
        if isinstance(node, ast.Name) and node.id in bindings:
            return bindings[node.id]
        raise ValueError(f"node interdit: {ast.dump(node)[:60]}")
    return ev(ast.parse(expr.strip(), mode="eval"))


def extract_expression(text: str) -> str | None:
    """Pull a python expression out of a model reply (fenced, inline or bare)."""
    text = (text or "").strip()
    m = re.search(r"```(?:python)?\s*([^`]+?)```", text)
    if m:
        text = m.group(1).strip()
    # keep the last line that looks like an expr; tolerate a prose label
    # before a ':' ("L'expression est : 47*6+12")
    def _looks_expr(s: str) -> bool:
        return bool(s) and bool(re.fullmatch(r"[0-9A-Za-z_()\s\"'+\-*/%.]+", s))

    for line in reversed(text.splitlines()):
        line = line.strip().rstrip(".")
        if not line or line.startswith(("#", ">", "Réponse", "answer")):
            continue
        if _looks_expr(line):
            return line
        if ":" in line:  # prose label before the expression
            tail = line.rsplit(":", 1)[-1].strip()
            if _looks_expr(tail):
                return tail
    return None


# --- engine access ----------------------------------------------------------
def ask(base: str, key: str, model: str, prompt: str, system=None, temperature=0.0,
        max_tokens=None, extra_body=None) -> str:
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    payload = {"model": model, "max_tokens": max_tokens or MAX_TOKENS,
               "temperature": temperature,
               "chat_template_kwargs": {"enable_thinking": False},
               "messages": msgs}
    if extra_body:
        payload.update(extra_body)
    req = urllib.request.Request(base + "/v1/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        body = json.loads(r.read())
    msg = body["choices"][0]["message"]
    content = msg.get("content") or ""
    if not content and msg.get("reasoning_content"):
        content = msg["reasoning_content"]
    return content


# --- coordinator (tier ABOVE the worker; routes via the fleet claudish hub,
# exactly like sk-agent's own configs — swift-1.5-27b/no-thinking, key never
# leaves the hub; called ONLY on residuals the deterministic layer REFUSES) ---
COORD_SYSTEM = ("Tu es coordonnateur-vérificateur dans un harnais fiabilisation. "
                "Un modèle worker (1.7B) a échoué cette tâche malgré relances. "
                "Donne la réponse correcte, rien d'autre — pas d'explication.")


def coordinator_call(cfg: dict, task_prompt: str, worker_best: str, gate_msg: str) -> str:
    prompt = (f"{task_prompt}\n\nMeilleure tentative du worker (rejetée — {gate_msg}) :\n"
              f"{worker_best[:400]}\n\nRéponds UNIQUEMENT par la réponse correcte "
              "à la tâche, dans le format demandé par la tâche.")
    return ask(cfg["url"], cfg["key"], cfg["model"], prompt,
               system=COORD_SYSTEM, temperature=0.0, max_tokens=120)


# --- per-class harness pipelines -------------------------------------------
def majority(values: list):
    """(value, count) of the most frequent item; None if empty."""
    if not values:
        return None, 0
    uniq = {}
    for v in values:
        uniq[v] = uniq.get(v, 0) + 1
    v, c = max(uniq.items(), key=lambda kv: kv[1])
    return v, c


def run_green(task, ask1):
    """Measured 100 %: single call, structural gate = the oracle scorer itself
    is not available in prod; here gate = parseability. Bench scores the answer."""
    out = ask1(task["prompt"])
    return out, {"route": "green", "calls": 1, "rounds": 0}


def sort_want(task):
    nums = [int(x) for x in re.findall(r"\d+", task["prompt"].rsplit(":", 1)[-1])]
    return sorted(nums)


def sort_gate(o: str, want) -> bool:
    got = [int(x) for x in re.findall(r"-?\d+", o or "")]
    return got[:len(want)] == want


def transform_want(task):
    m = re.search(r"«\s*(.+?)\s*»", task["prompt"])
    return m.group(1).upper() if m else None


def transform_gate(o: str, want) -> bool:
    return want is not None and qb.norm(o).upper() == want


def constraint_gate(o: str, n: int) -> bool:
    return word_count(o) == n


def regate(cat: str, out: str, task) -> bool | None:
    """Deterministic re-verification of ANY answer (worker or coordinator).
    None = class not mechanically re-checkable."""
    if cat == "sort":
        return sort_gate(out, sort_want(task))
    if cat == "transform":
        return transform_gate(out, transform_want(task))
    if cat == "constraint":
        return constraint_gate(out, int(task["oracle"]))
    return None


def run_ok(task, ask_with):
    """93 % classes, both VERIFIABLE. Gate first (sort = ascending permutation
    of the prompt's numbers; transform = exact uppercase of the quoted phrase);
    majority picks among gate-passers only — plain majority was measured
    AMPLIFYING the temp-0 error (sort 14->13 on 18/11). No passer after 1
    directed repair -> REFUS (main() may then escalate to the coordinator)."""
    if task["cat"] == "sort":
        want = sort_want(task)
        gate = lambda o: sort_gate(o, want)  # noqa: E731
        repair = ("\nAttention : ta liste doit être EXACTEMENT les mêmes nombres "
                  "que ceux donnés, triés du plus petit au plus grand. "
                  "Réponds uniquement la liste.")
    else:
        want = transform_want(task)
        gate = lambda o: transform_gate(o, want)  # noqa: E731
        repair = ("\nRéponds uniquement la phrase source entre guillemets, en "
                  "MAJUSCULES EXACTES, mot pour mot, rien en moins ni en plus.")
    outs = [ask_with(s, task["prompt"]) for s in SIBLINGS]
    calls = 3
    passers = [o for o in outs if gate(o)]
    if not passers and want:  # one directed repair
        outs.append(ask_with(SIBLINGS[0], task["prompt"] + repair))
        calls += 1
        if gate(outs[-1]):
            passers.append(outs[-1])
    if not passers:
        best = qb.norm(outs[0]) if outs else ""
        return f"REFUS: gate échouée après repair — « {best[:80]} »", {
            "route": "ok", "calls": calls, "rounds": 1, "agree": 0, "gated": True,
            "sibling_norms": [qb.norm(o) for o in outs]}
    norms = [qb.norm(o) for o in passers]
    val, cnt = majority(norms)
    raw = passers[norms.index(val)]
    return raw, {"route": "ok", "calls": calls, "rounds": 0, "agree": cnt,
                 "gated": True, "sibling_norms": [qb.norm(o) for o in outs]}


EXPR_PROMPT = {
    "arith": ("Calcule {p}. NE donne PAS le résultat. Réponds UNIQUEMENT par "
              "l'expression Python arithmétique qui calcule ce résultat "
              "(nombres et opérateurs + - * // % uniquement), sans texte autour."),
    "count": ("Soit T le texte ci-dessous. Combien de fois la lettre « {q} » "
              "apparaît-elle dans T ? NE donne PAS le résultat. Réponds UNIQUEMENT "
              "par l'expression Python qui le calcule avec T, par exemple "
              "T.count('x') — sans texte autour.\nT = {text}"),
}


def run_red(task, ask_with, cat):
    """<30 % classes: execution pivot. Siblings produce EXPRESSIONS; we eval;
    majority on computed VALUES. Repair: sibling whose expr failed gets one
    retry with the parse error."""
    if cat == "arith":
        prompt = EXPR_PROMPT["arith"].format(p=_arith_body(task["prompt"]))
        bindings = {}
    else:  # count
        m = re.search(r"la lettre « (\w) »", task["prompt"])
        text = task["prompt"].split("Texte : ", 1)[-1].strip()
        prompt = EXPR_PROMPT["count"].format(q=m.group(1), text=text)
        bindings = {"T": text}

    vals, exprs, errors, calls = [], [], [], 0
    for s in SIBLINGS:
        out = ask_with(s, prompt)
        calls += 1
        expr = extract_expression(out)
        if expr is None:
            errors.append(f"{s['id']}: no expr in {out[:60]!r}")
            continue
        try:
            vals.append(int(safe_eval(expr, bindings)))
            exprs.append(expr)
        except Exception as e:
            errors.append(f"{s['id']}: {e}")
    val, cnt = majority(vals)
    # one directed repair round if no majority
    if cnt < 2 and calls < 6:
        s = SIBLINGS[0]
        fb = errors[0] if errors else "expressions divergentes"
        out = ask_with(s, prompt + f"\nAttention: ta réponse précédente était inutilisable ({fb}). "
                      "Réponds strictement par l'expression seule.")
        calls += 1
        expr = extract_expression(out)
        if expr:
            try:
                vals.append(int(safe_eval(expr, bindings)))
                exprs.append(expr)
            except Exception as e:
                errors.append(f"repair: {e}")
        val, cnt = majority(vals)
    out = str(val) if val is not None else "REFUS: pas d'expression évaluable"
    return out, {"route": "red", "calls": calls, "rounds": 1 if cnt else 0,
                 "values": vals, "exprs": exprs, "errors": errors, "agree": cnt}


def _arith_body(prompt: str) -> str:
    m = re.search(r"Calcule (.+?)\. Réponds", prompt)
    return m.group(1) if m else prompt


def word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", qb.norm(text)) if w])


def run_yellow(task, ask1):
    """60 % class: deterministic gate (exact word count) + up to MAX_REPAIRS
    DIRECTED repairs — feedback carries the signed delta, so the repair is a
    one-word edit, not a regeneration."""
    n = int(task["oracle"])
    out = ask1(task["prompt"])
    calls, log = 1, []
    wc = word_count(out)
    for r in range(MAX_REPAIRS):
        if wc == n:
            break
        delta = n - wc
        how = ("ajoute exactement %d mot(s)" % delta) if delta > 0 else \
              ("retire exactement %d mot(s)" % -delta)
        out = ask1(f"Ta phrase : « {qb.norm(out)} »\nElle fait {wc} mots ; "
                   f"il en faut EXACTEMENT {n}. {how.capitalize()} et renvoie "
                   "uniquement la phrase corrigée, sans autre texte.")
        calls += 1
        wc = word_count(out)
        log.append(f"round{r + 1}: {wc} mots")
    if wc != n:
        out = f"REFUS: {wc} mots au lieu de {n} — « {qb.norm(out)[:80]} »"
    return out, {"route": "yellow", "calls": calls, "rounds": len(log),
                 "gate_log": log, "final_wc": wc}


# --- main -------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:5028")
    ap.add_argument("--model", default="voltron-1-mini")
    ap.add_argument("--label", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only-cat", default="", help="restrindre à une catégorie (debug)")
    ap.add_argument("--no-coord", action="store_true",
                    help="désactiver le coordonnateur (REFUS finals restent des refus)")
    ap.add_argument("--coord-url", default="http://192.168.0.50:3000",
                    help="hub claudish (même route que sk-agent)")
    ap.add_argument("--coord-model", default="swift-1.5-27b")
    args = ap.parse_args()

    coord = None
    if not args.no_coord:
        ckey = os.environ.get("ZAI_API_KEY", "")
        if ckey:
            coord = {"url": args.coord_url, "key": ckey, "model": args.coord_model}
        else:
            print("NOTE: ZAI_API_KEY absent — coordonnateur désactivé (REFUS finals)")
    coord_calls = 0

    key = qb.load_key()
    tasks = qb.build_tasks()
    if args.only_cat:
        tasks = [t for t in tasks if t["cat"] == args.only_cat]
    if args.limit:
        tasks = tasks[: args.limit]

    def ask1(prompt, **kw):
        return ask(args.url, key, args.model, prompt, **kw)

    def ask_with(s, prompt):
        return ask(args.url, key, args.model, prompt,
                   system=s["system"], temperature=s["temperature"])

    results = []
    t_start = time.time()
    for i, t in enumerate(tasks, 1):
        t0 = time.time()
        cat = t["cat"]
        route = ROUTE[cat]
        coord_used = coord_ok = None
        try:
            if route == "green":
                out, meta = run_green(t, ask1)
            elif route == "ok":
                out, meta = run_ok(t, ask_with)
            elif route == "yellow":
                out, meta = run_yellow(t, ask1)
            else:
                out, meta = run_red(t, ask_with, cat)
            ok, detail = qb.score(cat, out, t["oracle"])
            err = None
            if coord and not ok and out.startswith("REFUS"):
                # residual: the deterministic layer refused. The coordinator
                # (tier ABOVE) gets task + worker best + gate reason; its
                # answer is RE-GATED whenever the class is verifiable —
                # even the 27B is not trusted on parole.
                coord_used = True
                coord_calls += 1
                out_c = coordinator_call(coord, t["prompt"], out, detail)
                rg = regate(cat, out_c, t)
                if rg is True:
                    out, coord_ok, ok = out_c, True, True
                    detail = f"[coord + regate OK] {detail}"
                elif rg is False:
                    coord_ok = False  # coordinator also failed the gate: keep REFUS
                    detail = f"[coord rejeté par gate] {detail}"
                else:  # class not re-checkable (red routes): adopt, marked
                    out, coord_ok, ok = out_c, True, qb.score(cat, out_c, t["oracle"])[0]
                    detail = f"[coord adopté, sans regate] {detail}"
        except Exception as e:
            out, ok, detail, err, meta = "", False, "appel en échec", repr(e), {}
        row = dict(i=i, cat=cat, ok=ok, detail=detail, err=err,
                   out=out[:400], dt=round(time.time() - t0, 2))
        row.update({f"h_{k}": v for k, v in meta.items() if k != "sibling_norms"})
        if coord_used is not None:
            row["h_coord_used"] = coord_used
            row["h_coord_ok"] = coord_ok
        results.append(row)
        calls = meta.get("calls", "?")
        ctag = " COORD" if coord_used else ""
        print(f"[{i:>3}/{len(tasks)}] {cat:<10} {'OK ' if ok else 'FAIL'} "
              f"calls={calls:<2}{ctag} {detail[:90]}", flush=True)

    total = len(results)
    ok_total = sum(int(r["ok"]) for r in results)
    cats = {}
    for r in results:
        c = cats.setdefault(r["cat"], {"n": 0, "ok": 0, "calls": 0})
        c["n"] += 1
        c["ok"] += int(r["ok"])
        c["calls"] += r.get("h_calls", 0) or 0
    tot_calls = sum(c["calls"] for c in cats.values())
    summary = {
        "label": args.label, "url": args.url, "model": args.model,
        "at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(time.time() - t_start, 1),
        "n": total, "ok": ok_total,
        "acc": round(ok_total / total, 4) if total else None,
        "total_llm_calls": tot_calls,
        "coord_calls": coord_calls,
        "calls_per_task": round((tot_calls + coord_calls) / total, 2) if total else None,
        "by_cat": {k: v for k, v in sorted(cats.items())},
        "results": results,
    }
    out_dir = os.environ.get("VOLTRON_HARNESS_OUT", os.path.join(HERE, "_out"))
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(out_dir, f"voltron_harness_{args.label}_{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print(f"\n== {args.label}: {ok_total}/{total} = {summary['acc']:.3f} "
          f"({tot_calls} appels worker + {coord_calls} coord, "
          f"{summary['calls_per_task']}/tâche)")
    for k, v in cats.items():
        print(f"   {k:<10} {v['ok']}/{v['n']} = {v['ok'] / v['n']:.3f}  ({v['calls']} appels)")
    print(f"-> {path}")


if __name__ == "__main__":
    main()
