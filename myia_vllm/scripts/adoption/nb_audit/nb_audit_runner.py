#!/usr/bin/env python3
"""Scheduled pre-audit runner for the CoursIA #17073 campaign (mode (b), agreed 2026-09-23).

One run = one bounded batch, then exit; a user-level scheduled task calls it hourly.

  1. refresh the read-only CoursIA clone (fast-forward only);
  2. read the checklists of the configured series issues (gh, read-only) and keep the
     unchecked notebooks, in checklist order;
  3. skip every notebook whose current sha256 already has a record in the landing dir,
     so a record is only redone after a corrective push changed the file;
  4. run nb_audit_driver.py on at most --per-series notebooks per series;
  5. scan each record for secrets, then publish it to <landing>/<series>/ with a
     per-series index.json (notebook, owner bot, fingerprint, verdict, counts).

Nothing is posted anywhere: the bots read the landing dir, and their FULL READ decides.
A lock file prevents overlapping runs; a run killed mid-batch resumes at the next one.

    python nb_audit_runner.py --series 17107 17239 --per-series 4 --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRIVER = HERE / "nb_audit_driver.py"
SK_PY = Path("d:/roo-extensions/mcps/internal/servers/sk-agent/venv/Scripts/python.exe")
GH_REPO = "jsboige/CoursIA"
NB_ROOT = "MyIA.AI.Notebooks/"

# a record holds notebook text, model answers and script outputs; none of these should ever
# carry a credential, but the landing dir is shared, so the check is mechanical, not trusted
SECRET_PATTERNS = [
    r"\bsk-[A-Za-z0-9_-]{20,}", r"\bhf_[A-Za-z0-9]{30,}", r"\bghp_[A-Za-z0-9]{30,}",
    r"\bgithub_pat_[A-Za-z0-9_]{40,}", r"\bAKIA[0-9A-Z]{16}\b", r"\bxox[abp]-[A-Za-z0-9-]{20,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
]


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%SZ')}] {msg}", flush=True)


def slug(rel: str) -> str:  # same rule as the driver, which names its records with it
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", rel)[-120:]


def git(repo: Path, *a: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode:
        raise RuntimeError(f"git {' '.join(a)}: {p.stderr.strip()[:300]}")
    return p.stdout


def refresh_clone(repo: Path) -> str:
    if git(repo, "status", "--porcelain").strip():
        raise RuntimeError(f"{repo} has local changes; the audit clone must stay pristine")
    git(repo, "pull", "--ff-only", "--quiet")
    return git(repo, "rev-parse", "HEAD").strip()


def series_checklist(number: int) -> tuple[str, str, list[str]]:
    p = subprocess.run(["gh", "issue", "view", str(number), "--repo", GH_REPO, "--json", "title,body"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode:
        raise RuntimeError(f"gh issue view {number}: {p.stderr.strip()[:300]}")
    d = json.loads(p.stdout)
    m = re.search(r"partition\s+(\w+)", d["title"], re.I)
    owner = m.group(1) if m else "?"
    # series issues write items with or without backticks
    unchecked = re.findall(r"^\s*- \[ \]\s+`?([^`\s]+\.ipynb)`?", d["body"], re.M)
    return d["title"], owner, unchecked


def resolve(item: str, catalogue: list[str]) -> str | None:
    """Checklist items are a basename or a path relative to the series; match on suffix."""
    item = item.strip().lstrip("./")
    hits = [p for p in catalogue if p == item or p.endswith("/" + item)]
    return hits[0] if len(hits) == 1 else None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_index(d: Path) -> dict:
    f = d / "index.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {"records": {}}


def secret_hits(text: str) -> list[str]:
    return [pat for pat in SECRET_PATTERNS if re.search(pat, text)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--series", type=int, nargs="+", required=True, help="#17073 series issue numbers")
    ap.add_argument("--per-series", type=int, default=4, help="max notebooks per series and run")
    ap.add_argument("--concurrency", type=int, default=4,
                    help="6 once sk-agent's per-turn timeout is above 300 s (roo-extensions #3797)")
    ap.add_argument("--repo", default="d:/dev/CoursIA-skaudit")
    ap.add_argument("--landing", required=True, help="shared dir the bots read")
    ap.add_argument("--work-dir", default=str(Path(os.environ.get("TEMP", "/tmp")) / "nbaudit-runner"))
    ap.add_argument("--dry-run", action="store_true", help="select and print; no model call, no write")
    args = ap.parse_args()

    landing, work = Path(args.landing), Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    lock = work / "runner.lock"
    if lock.exists() and time.time() - lock.stat().st_mtime < 3 * 3600:
        log(f"another run holds {lock} (age {int(time.time() - lock.stat().st_mtime)} s); exit")
        return 0
    lock.write_text(str(os.getpid()), encoding="utf-8")
    try:
        repo = Path(args.repo)
        head = refresh_clone(repo) if not args.dry_run else git(repo, "rev-parse", "HEAD").strip()
        catalogue = [p for p in git(repo, "ls-files", "*.ipynb").splitlines() if p.startswith(NB_ROOT)]
        log(f"clone {repo} @ {head[:10]}, {len(catalogue)} notebooks")

        plan: list[tuple[int, str, str, str, str]] = []  # (issue, series slug, owner, rel, sha)
        for n in args.series:
            title, owner, unchecked = series_checklist(n)
            sdir = f"{n}-" + slug(re.sub(r"^\[Audit #17073\]\s*Série\s*|\s*—\s*partition.*$", "", title))[:60]
            index = load_index(landing / sdir)["records"]
            picked, unresolved = 0, []
            for item in unchecked:
                rel = resolve(item, catalogue)
                if rel is None:
                    unresolved.append(item)
                    continue
                digest = sha256(repo / rel)
                if index.get(rel, {}).get("sha256") == digest:
                    continue  # fresh record already published for this exact file
                plan.append((n, sdir, owner, rel, digest))
                picked += 1
                if picked >= args.per_series:
                    break
            log(f"#{n} {owner}: {len(unchecked)} unchecked, {picked} picked"
                + (f", {len(unresolved)} unresolved {unresolved[:3]}" if unresolved else ""))
        if not plan:
            log("nothing to do")
            return 0
        for n, sdir, owner, rel, digest in plan:
            log(f"  plan #{n} {owner} {rel} sha256:{digest[:12]}")
        if args.dry_run:
            log(f"DRY-RUN: {len(plan)} notebooks would be audited; nothing written")
            return 0

        # the driver resumes on parsed records: a per-run out dir forces a fresh audit
        run_dir = work / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
        cmd = [str(SK_PY), str(DRIVER), "--repo", str(repo), "--out-dir", str(run_dir),
               "--concurrency", str(args.concurrency), *[p[3] for p in plan]]
        t0 = time.time()
        rc = subprocess.run(cmd, cwd=str(HERE)).returncode
        log(f"driver rc={rc} in {time.time() - t0:.0f} s")

        published = 0
        for n, sdir, owner, rel, digest in plan:
            src = run_dir / f"{slug(rel)}.json"
            if not src.is_file():
                log(f"  no record for {rel}")
                continue
            text = src.read_text(encoding="utf-8")
            hits = secret_hits(text)
            if hits:
                log(f"  WITHHELD {rel}: secret-like pattern {hits}")
                continue
            rec = json.loads(text)
            if not rec.get("parsed") or (rec.get("fingerprint") or {}).get("sha256") != digest:
                log(f"  not published {rel}: parsed={rec.get('parsed')} error={rec.get('error')}")
                continue
            dest = landing / sdir
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest / src.name)
            idx = load_index(dest)
            nf = rec.get("findings") or []
            idx["records"][rel] = {
                "file": src.name, "owner": owner, "issue": n, "audited_at": rec.get("started"),
                **(rec.get("fingerprint") or {}), "verdict": rec.get("verdict"),
                "findings_valid": sum(bool(f.get("valid")) for f in nf), "findings_total": len(nf),
                "verifs_clean": sum(v.get("rc") == 0 for v in rec.get("verifs") or []),
                "verifs_total": len(rec.get("verifs") or []),
            }
            idx["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            (dest / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
            published += 1
        log(f"published {published}/{len(plan)} records under {landing}")
        return 0 if published or rc == 0 else 1
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
