#!/usr/bin/env python3
"""Tests des instruments de siege po-2028 (revue ai-01 du 26/11 sur PR #619).

Deux familles, SANS transport ni disque reel :

  A. `gateway_probe.py` -- tolerer une telemetrie malformee (la sonde ne meurt
     pas), classer sert / refus / muet / echec / erreur sans jamais confondre
     un refus avec un muet, lire les octets sur la phase qui les porte
     (`lecture`), et choisir les archives de reference sur l'horodatage du nom
     (un suffixe de collision ne doit pas fausser l'ordre).
  B. `ddrive_sizes.ps1 -Mode diff` -- ordonner les releves par l'horodatage de
     leur EN-TETE, comparer le dernier a l'horodatage DISTINCT le plus recent
     (deux releves de la meme seconde ne donnent aucun debit), et ne compter le
     bilan qu'au niveau 1 (L1 + L2 additionnes comptent `d:\dev` deux fois).

Execution : python -m pytest myia_vllm/scripts/testing/test_seat_instruments.py -v
            (ou directement : python test_seat_instruments.py)

Preuve rouge, sans toucher au depot :
    PROBE_SRC=<sonde d'avant correctif> DD_SRC=<script d'avant correctif> \
        python test_seat_instruments.py
Les versions d'avant correctif se tirent de git, par exemple :
    git show HEAD:myia_vllm/scripts/monitoring/ddrive_sizes.ps1 > /tmp/old.ps1
"""
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MON = os.path.join(HERE, "..", "monitoring")
PROBE_SRC = os.environ.get("PROBE_SRC") or os.path.join(MON, "gateway_probe.py")
DD_SRC = os.environ.get("DD_SRC") or os.path.join(MON, "ddrive_sizes.ps1")


def load_probe():
    spec = importlib.util.spec_from_file_location("gateway_probe_under_test", PROBE_SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Stub:
    """Transport factice : rend `result`, remplit `telemetry` comme l'organe."""

    def __init__(self, result, phases="skip", failure=None, raises=None):
        self.result, self.phases, self.failure, self.raises = result, phases, failure, raises
        self.calls = []

    def __call__(self, args, url, bearer, timeout=10.0, client="", client_dummy=None,
                 return_rejected_text=False, telemetry=None):
        self.calls.append({"args": args, "return_rejected_text": return_rejected_text})
        if self.raises is not None:
            raise self.raises
        if telemetry is not None:
            if self.phases != "skip":
                telemetry["phases"] = self.phases
            if self.failure is not None:
                telemetry["failure"] = self.failure
        return self.result


def _one(stub, ws="CoursIA-3", fname="workspace-CoursIA-3-2026-11-25T16-27-47.md"):
    mod = load_probe()
    return mod, mod.one(stub, "http://example.invalid", "tok", ws, fname, "cas", 1.0)[0]


# --- A. sonde : tolerance de la telemetrie -----------------------------------

def test_probe_survives_phases_none():
    for phases in (None, {}, {"tools-call": None}, {"tools-call": "boom"},
                   {"initialize": 1.0}, "not-a-dict"):
        _, row = _one(_Stub({"content": []}, phases=phases))
        assert isinstance(row["phases"], dict), (phases, row)


def test_probe_reads_bytes_from_lecture_not_tools_call():
    tele = {"initialize": {"ms": 1.0}, "tools-call": {"ms": 5.0},
            "lecture": {"ms": 1.0, "bytes": 42}}
    _, row = _one(_Stub({"content": []}, phases=tele))
    assert row["phases"].get("bytes") == 42, row
    assert row["phases"].get("tools-call") == 5.0, row


# --- A. sonde : cinq classes, aucune confusion -------------------------------

def test_probe_classifies_served_result():
    _, row = _one(_Stub({"content": [{"type": "text", "text": "ok"}]},
                        phases={"tools-call": {"ms": 3.0}, "lecture": {"ms": 1.0}}))
    assert row["cls"] == "sert" and row["ok"] is True, row
    assert row["fail"] == "-", row


def test_probe_classifies_server_rejection_as_refus_not_muet():
    # l'organe rend le texte du refus (isError) quand on le lui demande : un
    # refus ne doit jamais se lire comme un muet.
    stub = _Stub("archive introuvable", phases={"tools-call": {"ms": 2.0}})
    _, row = _one(stub)
    assert row["cls"] == "refus" and row["ok"] is False, row
    assert stub.calls[0]["return_rejected_text"] is True, stub.calls


def test_probe_classifies_transport_failure_with_phase_as_muet():
    _, row = _one(_Stub(None, phases={"initialize": {"ms": 1.0}},
                        failure={"phase": "tools-call", "exception": "URLError",
                                 "elapsed_ms": 30000.0}))
    assert row["cls"] == "muet", row
    assert row["fail"].startswith("tools-call/URLError/"), row


def test_probe_classifies_unmeasured_failure_as_echec_never_refus():
    # None SANS telemetrie de phase : non servi, cause non mesuree.
    _, row = _one(_Stub(None, phases="skip"))
    assert row["cls"] == "echec", row


def test_probe_classifies_raised_exception_as_erreur():
    _, row = _one(_Stub(None, phases="skip", raises=RuntimeError("boom")))
    assert row["cls"] == "erreur", row
    assert "RuntimeError" in row["fail"], row


# --- A. sonde : jeu de reference ---------------------------------------------

def test_probe_picks_newest_archives_by_stamp_not_by_name():
    mod = load_probe()
    listing = "\n".join([
        "- workspace-CoursIA-3-2026-11-20T10-00-00.md (1,2 Ko)",
        "- workspace-CoursIA-3-2026-11-25T16-27-47.md (3,4 Ko)",
        "- workspace-CoursIA-3-2026-11-25T16-27-47_2.md (3,5 Ko)",
        "- workspace-CoursIA-3-2026-11-11T06-09-16.md (0,9 Ko)",
        "- workspace-CoursIA-2-2026-11-26T01-56-46.md (9,9 Ko)",
    ])
    picked = mod.pick_archives(listing, "CoursIA-3", count=2)
    assert picked == ["workspace-CoursIA-3-2026-11-25T16-27-47_2.md",
                      "workspace-CoursIA-3-2026-11-25T16-27-47.md"], picked


def test_probe_pick_archives_returns_empty_on_foreign_or_empty_listing():
    mod = load_probe()
    assert mod.pick_archives("", "CoursIA-3") == []
    assert mod.pick_archives("- workspace-CoursIA-2-2026-11-26T01-56-46.md", "CoursIA-3") == []


# --- B. ddrive_sizes : ordre des releves -------------------------------------

def _write_snapshot(path, utc, free, dev_bytes, claudish_bytes, vllm_bytes):
    body = ("### utc=%sZ drive=D free_bytes=%d\n"
            "L1\td:\\dev\t%d\nL2\td:\\dev\\claudish\t%d\nL2\td:\\dev\\vllm\t%d\n"
            % (utc, free, dev_bytes, claudish_bytes, vllm_bytes))
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)


# 3 releves : 05:00:00, puis deux dans la meme seconde 06:10:00 (garde de
# collision `_2` = le plus recent). Entre 05:00 et 06:10:00_2, `claudish`
# (niveau 2) grossit de 5 Go et `d:\dev` (niveau 1, qui le CONTIENT) aussi.
_GB = 1000 ** 3
_FX = {
    "ddrive_sizes_20261126T050000Z.txt": ("2026-11-26 05:00:00", 482_387_259_392,
                                          1400 * _GB, 400 * _GB, 14_516_331_968),
    "ddrive_sizes_20261126T061000Z.txt": ("2026-11-26 06:10:00", 477_387_259_392,
                                          1404 * _GB, 404 * _GB, 14_516_331_968),
    "ddrive_sizes_20261126T061000Z_2.txt": ("2026-11-26 06:10:00", 477_387_259_392,
                                            1405 * _GB, 405 * _GB, 14_516_331_968),
}


def _run_diff(tmp):
    pwsh = shutil.which("pwsh")
    assert pwsh, "pwsh absent : test non mesurable ici"
    return subprocess.run([pwsh, "-NoProfile", "-File", DD_SRC, "-Mode", "diff",
                           "-OutDir", tmp], capture_output=True, text=True, timeout=180)


def test_ddiff_orders_by_header_time_and_skips_same_second():
    tmp = tempfile.mkdtemp(prefix="ddrive_fixture_")
    try:
        for name, (utc, free, dev, claudish, vllm) in _FX.items():
            _write_snapshot(os.path.join(tmp, name), utc, free, dev, claudish, vllm)
        proc = _run_diff(tmp)
        out = proc.stdout
        assert proc.returncode == 0, (proc.returncode, out, proc.stderr)
        # a horodatage egal, le suffixe le plus haut a ete ecrit en second
        assert "### apres : ddrive_sizes_20261126T061000Z_2.txt" in out, out
        # l'autre releve de la meme seconde est saute, le 05:00 est compare
        assert "### avant : ddrive_sizes_20261126T050000Z.txt" in out, out
        assert "en 70 min" in out, out
        assert "meme seconde" in out, out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ddiff_balance_counts_level_1_only():
    # `claudish` (L2) est DANS `d:\dev` (L1) : les additionner annonce deux
    # fois la meme croissance (mesure reelle 26/11 : +36,22 Go pour -18,58 Go).
    tmp = tempfile.mkdtemp(prefix="ddrive_fixture_")
    try:
        for name, (utc, free, dev, claudish, vllm) in _FX.items():
            _write_snapshot(os.path.join(tmp, name), utc, free, dev, claudish, vllm)
        proc = _run_diff(tmp)
        assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
        # 5 * 10^9 octets = 4,66 Gio, une seule fois ; 9,31 = le double compte
        assert re.search(r"net \+4[.,]66 Go ; libre -4[.,]66 Go", proc.stdout), proc.stdout
        assert not re.search(r"net \+9[.,]31 Go", proc.stdout), proc.stdout
        # les listes par dossier gardent les deux niveaux
        assert "[L1] d:\\dev" in proc.stdout and "[L2] d:\\dev\\claudish" in proc.stdout, proc.stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ddiff_reports_single_timestamp_instead_of_fake_zero_rate():
    tmp = tempfile.mkdtemp(prefix="ddrive_fixture_")
    try:
        for name in ("ddrive_sizes_20261126T061000Z.txt", "ddrive_sizes_20261126T061000Z_2.txt"):
            utc, free, dev, claudish, vllm = _FX[name]
            _write_snapshot(os.path.join(tmp, name), utc, free, dev, claudish, vllm)
        proc = _run_diff(tmp)
        assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
        assert "un seul horodatage distinct" in proc.stdout, proc.stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS: {fn.__name__}", flush=True)
        except Exception as exc:
            failed += 1
            print(f"FAIL: {fn.__name__}: {exc!r}", flush=True)
    print(f"{len(fns) - failed}/{len(fns)} tests OK", flush=True)
    sys.exit(1 if failed else 0)
