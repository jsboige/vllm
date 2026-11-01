#!/usr/bin/env python3
"""Portes mecaniques FrogNano — R9/R10/R11 (voir docs/frognano-team-solve.md).

Une porte ne lit JAMAIS ce que le mini affirme : elle recompte ses citations
verifiees, ou elle compare des nombres. Le mini cite, la porte juge.

Usage (exit code 0 = porte passee, 1 = porte echouee, 2 = erreur d'usage/IO):

    python frognano_gate.py partition --corpus C --a A --b B
    python frognano_gate.py threshold --corpus C --a A --b B --field free --op lt --value 2000
    python frognano_gate.py fidelity  --src S --dst D
    python frognano_gate.py selftest

`--json` sur n'importe quelle sous-commande: sortie machine pour un appelant
automatise (un modele mandataire consomme le verdict, pas la prose).

R9/R10 prennent A et B = les sorties des DEUX extracteurs a motifs qui
partitionnent le corpus (un motif, un autre motif; ou motif / "le reste").
R11 prend la source et la reecriture, et compare les nombres des deux cotes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Iterable, Sequence

OPS = {
    "lt": lambda v, t: v < t,
    "le": lambda v, t: v <= t,
    "gt": lambda v, t: v > t,
    "ge": lambda v, t: v >= t,
    "eq": lambda v, t: v == t,
}

# v1 (mesuree): les separateurs de milliers/decimaux sont retires. Cela prouve
# la conservation des CHIFFRES, pas la position decimale (74,9 == 749 == 74.9).
# C'est la porte telle qu'elle a ete mesuree 20/20 le 01/11 ; ne pas durcir sans
# une nouvelle mesure.
NUM_RE = re.compile(r"\d+(?:[ .,]\d+)*")


def read_lines(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        return [ln.strip() for ln in fh if ln.strip()]


def multiset(lines: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for ln in lines:
        out[ln] = out.get(ln, 0) + 1
    return out


def gate_partition(corpus: Sequence[str], a: Sequence[str], b: Sequence[str]) -> dict:
    """R9: precision (sortie ∈ source) + disjoint + partition + couverture.

    Si les quatre tiennent, |A| est un compte PROUVE : aucune ligne n'a pu etre
    ajoutee, perdue ou comptee deux fois. Precision seule ne prouve rien.
    """
    corpus_ms = multiset(corpus)
    union = list(a) + list(b)
    union_ms = multiset(union)

    fabricated = [ln for ln in union if ln not in corpus_ms]
    # Sans contrainte de multiplicite, une ligne presente 2x dans la source et
    # 3x dans l'union passerait: on compare donc les multiplicités.
    over = [ln for ln, n in union_ms.items() if n > corpus_ms.get(ln, 0)]
    intersection = sum(1 for ln, n in union_ms.items() if n > 1)
    missing = sorted(ln for ln in corpus_ms if ln not in union_ms)

    passed = (
        not fabricated
        and not over
        and intersection == 0
        and not missing
        and len(a) + len(b) == len(corpus)
        and sorted(union) == sorted(corpus)
    )
    return {
        "gate": "partition",
        "passed": passed,
        "count_a": len(a),
        "count_b": len(b),
        "corpus": len(corpus),
        "fabricated": fabricated,
        "over_counted": over,
        "duplicated": intersection,
        "missing": missing,
    }


def gate_threshold(
    corpus: Sequence[str],
    a: Sequence[str],
    b: Sequence[str],
    field: str,
    op: str,
    value: float,
) -> dict:
    """R10: parse exhaustif du champ sur l'union VERIFIEE, puis comparaison.

    La partition de R9 sert de socle: si elle echoue, le seuil n'a aucune valeur
    (on ne compare pas des nombres issus de lignes non prouvees). Le parse doit
    etre exhaustif: un seul `free=` non parse = porte echouee, jamais ignore.
    """
    part = gate_partition(corpus, a, b)
    union = list(a) + list(b)
    pat = re.compile(rf"{re.escape(field)}\s*=\s*(-?\d+(?:\.\d+)?)")
    parsed: list[tuple[str, float]] = []
    unparsed: list[str] = []
    for ln in union:
        m = pat.search(ln)
        if m:
            parsed.append((ln, float(m.group(1))))
        else:
            unparsed.append(ln)

    hits = [ln for ln, v in parsed if OPS[op](v, value)]
    values = [v for _, v in parsed]
    passed = part["passed"] and not unparsed
    return {
        "gate": "threshold",
        "passed": passed,
        "partition_ok": part["passed"],
        "field": field,
        "op": op,
        "value": value,
        "parsed": len(parsed),
        "total": len(union),
        "unparsed": unparsed,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "hits": len(hits),
        "hit_lines": hits,
    }


def numbers(text: str) -> list[str]:
    return [m.group(0).replace(" ", "").replace(",", "").replace(".", "")
            for m in NUM_RE.finditer(text)]


def gate_fidelity(src: str, dst: str) -> dict:
    """R11: multiset des nombres de la source vs de la reecriture."""
    with open(src, "r", encoding="utf-8-sig", errors="replace") as fh:
        s = fh.read()
    with open(dst, "r", encoding="utf-8-sig", errors="replace") as fh:
        d = fh.read()
    ns, nd = numbers(s), numbers(d)
    ms, md = multiset(ns), multiset(nd)
    lost = sorted(k for k in ms if ms[k] > md.get(k, 0))
    added = sorted(k for k in md if md[k] > ms.get(k, 0))
    return {
        "gate": "fidelity",
        "passed": not lost and not added and len(ns) == len(nd),
        "src_numbers": len(ns),
        "dst_numbers": len(nd),
        "lost": lost,
        "added": added,
        "note": "separateurs retires: prouve les chiffres, pas la position decimale",
    }


def render(res: dict) -> str:
    head = "PORTE PASSEE" if res["passed"] else "PORTE ECHOUEE"
    lines = [f"[{head}] {res['gate']}"]
    g = res["gate"]
    if g == "partition":
        lines.append(f"  A={res['count_a']} B={res['count_b']} corpus={res['corpus']}"
                     f" (somme {'=' if res['count_a'] + res['count_b'] == res['corpus'] else '!='} corpus)")
        lines.append(f"  fabriquees={len(res['fabricated'])} sur-comptees={len(res['over_counted'])}"
                     f" doublons={res['duplicated']} manquantes={len(res['missing'])}")
        for ln in (res["fabricated"] + res["over_counted"] + res["missing"])[:5]:
            lines.append(f"    ! {ln[:100]}")
        if res["passed"]:
            lines.append(f"  COMPTE PROUVE : {res['count_a']}")
    elif g == "threshold":
        lines.append(f"  {res['field']} {res['op']} {res['value']} -> {res['hits']} ligne(s)"
                     f" ; parse {res['parsed']}/{res['total']} ; min={res['min']} max={res['max']}")
        lines.append(f"  partition={'OK' if res['partition_ok'] else 'ECHOUEE'}"
                     f" parse={'exhaustif' if not res['unparsed'] else str(len(res['unparsed'])) + ' non parse(s)'}")
        for ln in res["hit_lines"]:
            lines.append(f"    > {ln[:120]}")
        for ln in res["unparsed"][:5]:
            lines.append(f"    ! non parse: {ln[:100]}")
    elif g == "fidelity":
        lines.append(f"  nombres source={res['src_numbers']} reecriture={res['dst_numbers']}")
        for n in res["lost"]:
            lines.append(f"    - perdu/altere: {n}")
        for n in res["added"]:
            lines.append(f"    + ajoute: {n}")
    return "\n".join(lines)


def selftest() -> int:
    """Reproduit les cas mesures le 01/11 + les falsifications qui doivent echouer."""
    corpus = (
        [f"2026-11-01 {h:02d}:02:02 HEARTBEAT temp=33C free={5000 + h}MB mode=normal" for h in range(28)]
        + [
            "2026-10-31 16:42:02 WARN RAM basse free=3824MB temp=31C mode=normal",
            "2026-11-01 01:52:02 WARN RAM basse free=3862MB temp=32C mode=normal",
            "2026-11-01 06:22:03 WARN RAM CRITIQUE free=1128MB mais pire RSM=0.1GB (< barre 4GB, pas de kill) - escalader au dashboard (ne pas fermer de fenetres)",
            "2026-11-01 06:27:03 WARN RAM basse free=2567MB temp=32C mode=normal",
        ]
    )
    warn = [ln for ln in corpus if "WARN" in ln]
    hb = [ln for ln in corpus if "HEARTBEAT" in ln]
    checks: list[tuple[str, bool]] = []

    p = gate_partition(corpus, warn, hb)
    checks.append(("R9 partition 4+28=32 passe", p["passed"] and p["count_a"] == 4))

    checks.append(("R9 fabrication detectee",
                   not gate_partition(corpus, warn + ["WARN invente free=1MB"], hb)["passed"]))
    checks.append(("R9 omission detectee",
                   not gate_partition(corpus, warn[1:], hb)["passed"]))
    checks.append(("R9 doublon detecte",
                   not gate_partition(corpus, warn + warn[:1], hb)["passed"]))
    # Le contradicteur du 01/11: compte faux (3) avec 4 citations justes.
    checks.append(("R9 compte faux non retenu",
                   gate_partition(corpus, warn, hb)["count_a"] == 4))

    t = gate_threshold(corpus, warn, hb, "free", "lt", 2000)
    checks.append(("R10 free<2000 -> 1 ligne, min 1128",
                   t["passed"] and t["hits"] == 1 and t["min"] == 1128.0))
    checks.append(("R10 parse exhaustif 32/32", t["parsed"] == 32))
    tu = gate_threshold(corpus, warn, hb[:-1] + ["2026-11-01 09:02:03 HEARTBEAT sans champ"], "free", "lt", 2000)
    checks.append(("R10 champ non parse -> porte echouee", not tu["passed"]))

    checks.append(("R11 20/20 conserve", numbers("temp 74,9 C, 1 234 ms, 12.5 %") ==
                   numbers("temp 74.9 C, 1234 ms, 12.5 %")))
    checks.append(("R11 alteration detectee",
                   numbers("debit 1 200 MB/s") != numbers("debit 1 020 MB/s")))
    checks.append(("R11 perte detectee",
                   numbers("3 requetes, 42 tokens") != numbers("3 requetes")))

    ok = True
    for label, passed in checks:
        ok &= passed
        print(("  OK   " if passed else "  FAIL ") + label)
    print(("selftest OK" if ok else "selftest ECHEC") + f" ({len(checks)} controles)")
    return 0 if ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Portes mecaniques FrogNano (R9/R10/R11)")
    ap.add_argument("--json", action="store_true", help="sortie machine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("partition", help="R9: comptage prouve par partition")
    for name in ("corpus", "a", "b"):
        p1.add_argument(f"--{name}", required=True)

    p2 = sub.add_parser("threshold", help="R10: seuil sur valeur de champ, prouve")
    for name in ("corpus", "a", "b"):
        p2.add_argument(f"--{name}", required=True)
    p2.add_argument("--field", required=True)
    p2.add_argument("--op", required=True, choices=sorted(OPS))
    p2.add_argument("--value", required=True, type=float)

    p3 = sub.add_parser("fidelity", help="R11: fidelite des nombres d'une reecriture")
    p3.add_argument("--src", required=True)
    p3.add_argument("--dst", required=True)

    sub.add_parser("selftest", help="rejoue les cas mesures")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "partition":
            res = gate_partition(read_lines(args.corpus), read_lines(args.a), read_lines(args.b))
        elif args.cmd == "threshold":
            res = gate_threshold(read_lines(args.corpus), read_lines(args.a), read_lines(args.b),
                                 args.field, args.op, args.value)
        elif args.cmd == "fidelity":
            res = gate_fidelity(args.src, args.dst)
        else:
            return selftest()
    except OSError as exc:
        print(f"ERREUR IO: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else render(res))
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
