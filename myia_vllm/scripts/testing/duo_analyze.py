#!/usr/bin/env python3
"""Pairs two duo_bench.py runs of the same bench: the 2x2 of their gates and the
rules a harness can apply WITHOUT knowing the oracle.

Every rule below is decided from information available at run time — the
contract type and the mechanical gate — never from the expected answer. The
oracle only scores, afterwards.

  cascade A→B     A answers; if its gate fails, B answers the same task dry;
                  B's answer is accepted if its gate passes
  cascade B→A     the reverse
  router          the first reader is chosen by contract type (a table learned
                  on one bench, --route "cat=arm,cat=arm"); the other reader is
                  the fallback
  agreement       on tasks without a mechanical gate: do the two readers give
                  the same answer, and is an agreement more often right?

Usage:
  python duo_analyze.py --a duo_socle_voltron_<stamp>.json --b duo_socle_frog_<stamp>.json
  python duo_analyze.py --a ... --b ... --route "err-classify=b,fail-extract=b" --out verdict.json
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone


def canon(out):
    """Comparable form of an answer: a parsed JSON object, else whitespace-normalised text."""
    text = (out or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.dumps(json.loads(m.group(0)), sort_keys=True, ensure_ascii=False)
        except ValueError:
            pass
    return re.sub(r"\s+", " ", text).strip().strip("«»\"' .").lower()


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cascade(a, b, route=None):
    """Accepts the routed reader when its gate passes, else the other one. Returns (ok, calls)."""
    ok, calls = 0, 0
    for ra, rb in zip(a, b):
        first, second = (ra, rb) if (route or "a") == "a" else (rb, ra)
        if first["ok"]:
            ok += 1
            calls += 1
        elif second["ok"]:
            ok += 1
            calls += 2
        else:
            calls += 2
    return ok, calls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--name-a", default="A")
    ap.add_argument("--name-b", default="B")
    ap.add_argument("--route", default="", help="cat=a|b par catégorie, séparé par des virgules")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    A, B = load(args.a), load(args.b)
    if A["bench"] != B["bench"] or A["n"] != B["n"]:
        sys.exit("bancs différents : %s/%s vs %s/%s" % (A["bench"], A["n"], B["bench"], B["n"]))
    a, b = A["results"], B["results"]
    if [r["i"] for r in a] != [r["i"] for r in b]:
        sys.exit("les deux bras ne couvrent pas les mêmes tâches")

    route = {}
    for part in filter(None, (p.strip() for p in args.route.split(","))):
        cat, arm = part.split("=")
        route[cat.strip()] = arm.strip().lower()

    n = len(a)
    both = sum(1 for ra, rb in zip(a, b) if ra["ok"] and rb["ok"])
    only_a = sum(1 for ra, rb in zip(a, b) if ra["ok"] and not rb["ok"])
    only_b = sum(1 for ra, rb in zip(a, b) if not ra["ok"] and rb["ok"])
    neither = n - both - only_a - only_b
    agree = [canon(ra["out"]) == canon(rb["out"]) for ra, rb in zip(a, b)]

    cats = sorted({r["cat"] for r in a})
    by_cat = {}
    for c in cats:
        idx = [i for i, r in enumerate(a) if r["cat"] == c]
        by_cat[c] = {
            "n": len(idx),
            "a_ok": sum(int(a[i]["ok"]) for i in idx),
            "b_ok": sum(int(b[i]["ok"]) for i in idx),
            "union": sum(int(a[i]["ok"] or b[i]["ok"]) for i in idx),
            "agree": sum(int(agree[i]) for i in idx),
        }

    routed_ok, routed_calls = 0, 0
    for c in cats:
        first = route.get(c, "a")
        o, k = cascade([a[i] for i in range(n) if a[i]["cat"] == c],
                       [b[i] for i in range(n) if b[i]["cat"] == c], first)
        routed_ok += o
        routed_calls += k

    out = {
        "at": datetime.now(timezone.utc).isoformat(),
        "bench": A["bench"], "n": n,
        "a": {"name": args.name_a, "file": args.a, "model": A["model"],
              "ok": A["ok"], "elapsed_s": A["elapsed_s"]},
        "b": {"name": args.name_b, "file": args.b, "model": B["model"],
              "ok": B["ok"], "elapsed_s": B["elapsed_s"]},
        "cross": {"both": both, "only_a": only_a, "only_b": only_b, "neither": neither,
                  "oracle_union": both + only_a + only_b},
        "rules": {
            "cascade_a_then_b": {"ok": cascade(a, b, "a")[0]},
            "cascade_b_then_a": {"ok": cascade(a, b, "b")[0]},
            "router": {"ok": routed_ok, "route": route},
        },
        "agreement": {
            "n_agree": sum(agree), "n_disagree": n - sum(agree),
            "a_ok_if_agree": sum(int(ra["ok"]) for ra, g in zip(a, agree) if g),
            "b_ok_if_agree": sum(int(rb["ok"]) for rb, g in zip(b, agree) if g),
            "a_ok_if_disagree": sum(int(ra["ok"]) for ra, g in zip(a, agree) if not g),
            "b_ok_if_disagree": sum(int(rb["ok"]) for rb, g in zip(b, agree) if not g),
        },
        "by_cat": by_cat,
    }

    print("Banc %s — %d tâches appariées" % (A["bench"], n))
    print("  %-10s %3d/%d" % (args.name_a, A["ok"], n))
    print("  %-10s %3d/%d" % (args.name_b, B["ok"], n))
    print("  croisé     les deux=%d  seulement %s=%d  seulement %s=%d  aucun=%d"
          % (both, args.name_a, only_a, args.name_b, only_b, neither))
    print("  oracle     union=%d/%d (plafond du duo)" % (both + only_a + only_b, n))
    print("  règles (décidées sans l'oracle) :")
    print("    cascade %s->%s   %d/%d" % (args.name_a, args.name_b,
                                         out["rules"]["cascade_a_then_b"]["ok"], n))
    print("    cascade %s->%s   %d/%d" % (args.name_b, args.name_a,
                                         out["rules"]["cascade_b_then_a"]["ok"], n))
    print("    routeur %s   %d/%d" % (route or "{toutes=%s}" % args.name_a, routed_ok, n))
    ag = out["agreement"]
    print("  accord de réponse : %d d accord (%s ok %d, %s ok %d) ; %d de desaccord "
          "(%s ok %d, %s ok %d)" % (
              ag["n_agree"], args.name_a, ag["a_ok_if_agree"], args.name_b, ag["b_ok_if_agree"],
              ag["n_disagree"], args.name_a, ag["a_ok_if_disagree"],
              args.name_b, ag["b_ok_if_disagree"]))
    print("  par catégorie (n / %s / %s / union / accord) :" % (args.name_a, args.name_b))
    for c, v in by_cat.items():
        print("    %-13s %2d  %2d  %2d  %2d  %2d" % (c, v["n"], v["a_ok"], v["b_ok"],
                                                    v["union"], v["agree"]))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print("-> %s" % args.out)


if __name__ == "__main__":
    main()
