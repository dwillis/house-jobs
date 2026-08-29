"""One-time enrichment of an existing corpus directory in place.

    uv run python -m pipeline.backfill listing_type --dir json_v3

`listing_type` adds a "listing_type" field ("internship" or "staff") to every
job, derived from its source bulletin filename. New parses stamp this field
automatically (see run_parse.py); this backfills corpora parsed before it was
added. Writes each file atomically and is idempotent.
"""

import argparse
import json
from pathlib import Path

from config import JSON_V3_DIR
from pipeline.chunking import listing_type


def cmd_listing_type(args: argparse.Namespace) -> None:
    out_dir = Path(args.dir)
    changed_files = 0
    changed_jobs = 0
    counts = {"internship": 0, "staff": 0}

    for path in sorted(out_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        jobs = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(jobs, list):
            continue
        lt = listing_type(path.name)
        file_changed = False
        for job in jobs:
            counts[lt] += 1
            if job.get("listing_type") != lt:
                job["listing_type"] = lt
                changed_jobs += 1
                file_changed = True
        if file_changed:
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(jobs, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
            changed_files += 1

    print(f"listing_type backfill over {out_dir}/:")
    print(f"  internship jobs: {counts['internship']}")
    print(f"  staff jobs:      {counts['staff']}")
    print(f"  updated {changed_jobs} job(s) across {changed_files} file(s).")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    p_lt = sub.add_parser("listing_type", help="add listing_type (internship/staff) from source filename")
    p_lt.add_argument("--dir", default=JSON_V3_DIR)
    p_lt.set_defaults(func=cmd_listing_type)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
