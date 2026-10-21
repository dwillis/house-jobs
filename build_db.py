#!/usr/bin/env python3
"""Build a SQLite database of House job listings from json_v3/ for Datasette.

Creates two tables, one row per unique listing ID:
  staff_jobs   - Member & Committee bulletins
  internships  - Internship bulletins

Weekly reposts are deduplicated by keeping the earliest-dated appearance of
each ID (same rule as skills/cluster_jobs.py:load_jobs), with first_seen,
last_seen and appearances tracked across bulletins.

Usage:
    uv run python build_db.py
    uv run datasette house_jobs.db -m metadata.yml
"""
import argparse
import json
import re
from pathlib import Path

import sqlite_utils

from config import JSON_V3_DIR

DEFAULT_DB = "house_jobs.db"

# Copied from skills/cluster_jobs.py (importing it pulls in hdbscan/umap).
_DATE_PATTERNS = [
    (re.compile(r'(\d{4})_(\d{2})_(\d{2})'),
     lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}"),
    (re.compile(r'^(\d{1,2})-(\d{2})-(\d{2})_'),
     lambda m: "{}-{}-{}".format(
         f"20{m.group(3)}" if int(m.group(3)) < 50 else f"19{m.group(3)}",
         m.group(1).zfill(2), m.group(2)
     )),
    (re.compile(r'(\d{1,2})\.(\d{2})\.(\d{4})'),
     lambda m: f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2)}"),
]


def _date_from_filename(name: str) -> str | None:
    stem = Path(name).stem
    for pat, fmt in _DATE_PATTERNS:
        m = pat.search(stem)
        if m:
            return fmt(m)
    return None


TABLES = {"staff": "staff_jobs", "internship": "internships"}

FIELDS = [
    "position_title", "office", "location", "posting_date", "job_category",
    "salary_info", "description", "responsibilities", "qualifications",
    "how_to_apply", "contact", "equal_opportunity",
]

FTS_COLUMNS = [
    "position_title", "office", "location", "description",
    "responsibilities", "qualifications",
]

INDEXES = ["job_category", "office", "year", "first_seen"]


def _route(filename: str) -> str:
    return "internship" if "intern" in filename.lower() else "staff"


def collect(json_dir: Path) -> tuple[dict[str, dict[str, dict]], int]:
    """Return {route: {id: row}} plus a count of listing_type/route mismatches."""
    appearances: list[tuple[str, str, str, dict]] = []  # (date, file, route, job)
    for path in sorted(json_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            jobs = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(jobs, list):
            continue
        fn_date = _date_from_filename(path.name)
        route = _route(path.name)
        for job in jobs:
            if not isinstance(job, dict) or not job.get("id"):
                continue
            date = fn_date or job.get("posting_date") or ""
            appearances.append((date, path.name, route, job))

    # Stable sort keeps within-file order, so the first copy in a file wins ties.
    appearances.sort(key=lambda a: (a[0] or "9999-99-99", a[1]))

    tables: dict[str, dict[str, dict]] = {r: {} for r in TABLES}
    files_seen: dict[tuple[str, str], set[str]] = {}
    mismatches = 0
    for date, filename, route, job in appearances:
        lt = job.get("listing_type")
        if lt and lt != route:
            mismatches += 1
        jid = job["id"]
        rows = tables[route]
        if jid not in rows:
            row = {"id": jid, **{f: job.get(f) for f in FIELDS}}
            row.update(
                first_seen=date or None,
                last_seen=date or None,
                year=int(date[:4]) if date[:4].isdigit() else None,
                source_file=filename,
                source_model=job.get("source_model"),
                parsed_at=job.get("parsed_at"),
            )
            rows[jid] = row
        elif date and (rows[jid]["last_seen"] or "") < date:
            rows[jid]["last_seen"] = date
        files_seen.setdefault((route, jid), set()).add(filename)

    for route, rows in tables.items():
        for jid, row in rows.items():
            row["appearances"] = len(files_seen[(route, jid)])
    return tables, mismatches


def build(json_dir: Path, db_path: str) -> None:
    tables, mismatches = collect(json_dir)
    db = sqlite_utils.Database(db_path)
    columns = {
        "id": str, **{f: str for f in FIELDS},
        "first_seen": str, "last_seen": str, "appearances": int, "year": int,
        "source_file": str, "source_model": str, "parsed_at": str,
    }
    for route, name in TABLES.items():
        # Dropping the table also drops its FTS triggers.
        for t in (name, f"{name}_fts"):
            db[t].drop(ignore=True)
        table = db[name]
        table.create(columns, pk="id")
        table.insert_all(tables[route].values(), pk="id", replace=True)
        for col in INDEXES:
            table.create_index([col], if_not_exists=True)
        table.enable_fts(FTS_COLUMNS, create_triggers=True)
        print(f"{name}: {table.count:,} rows")
    db.vacuum()
    print(f"listing_type/filename mismatches: {mismatches}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json-dir", default=JSON_V3_DIR)
    ap.add_argument("--db", default=DEFAULT_DB)
    args = ap.parse_args()
    build(Path(args.json_dir), args.db)


if __name__ == "__main__":
    main()
