#!/usr/bin/env python
"""
Find duplicate job listings across JSON files using the "id" attribute.
Reports each duplicate ID with its count, files, and min/max posting dates.
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

from config import JSON_DIR


def find_duplicates(directory: str, csv_path: str = "data/duplicates.csv") -> None:
    data_path = Path(directory)
    if not data_path.exists():
        print(f"Error: Directory '{directory}' does not exist")
        sys.exit(1)

    # id -> list of {file, posting_date}
    id_occurrences: dict[str, list[dict]] = defaultdict(list)
    total_jobs = 0
    total_files = 0

    for json_file in sorted(data_path.glob("*.json")):
        try:
            jobs = json.load(open(json_file, encoding="utf-8"))
        except Exception as e:
            print(f"Warning: could not load {json_file.name}: {e}")
            continue

        if not isinstance(jobs, list):
            continue

        total_files += 1
        for job in jobs:
            job_id = job.get("id")
            if not job_id:
                continue
            total_jobs += 1
            id_occurrences[job_id].append(
                {
                    "office": job.get("office") or "",
                    "posting_date": job.get("posting_date") or "",
                    "position_title": job.get("position_title") or "",
                }
            )

    duplicates = {
        job_id: occurrences
        for job_id, occurrences in id_occurrences.items()
        if len(occurrences) > 1
    }

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"Files scanned : {total_files}")
    print(f"Total listings: {total_jobs}")
    print(f"Unique IDs    : {len(id_occurrences)}")
    print(f"Duplicate IDs : {len(duplicates)}")
    print(f"Extra copies  : {sum(len(v) - 1 for v in duplicates.values())}")

    if not duplicates:
        print("\nNo duplicates found.")
        return

    # ── CSV output ────────────────────────────────────────────────────────────
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "count", "min_date", "max_date", "position_title", "office"])
        for job_id, occurrences in sorted(duplicates.items()):
            dates = [o["posting_date"] for o in occurrences if o["posting_date"]]
            min_date = min(dates) if dates else ""
            max_date = max(dates) if dates else ""
            title = occurrences[0]["position_title"]
            office = occurrences[0]["office"]
            writer.writerow([job_id, len(occurrences), min_date, max_date, title, office])
    print(f"\nCSV saved to: {csv_path}")

    # ── Per-duplicate detail ──────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"{'ID':<20} {'Count':>5}  {'Min Date':<12}  {'Max Date':<12}  Title")
    print("-" * 70)

    for job_id, occurrences in sorted(duplicates.items()):
        dates = [o["posting_date"] for o in occurrences if o["posting_date"]]
        min_date = min(dates) if dates else "unknown"
        max_date = max(dates) if dates else "unknown"
        title = occurrences[0]["position_title"]
        print(
            f"{job_id:<20} {len(occurrences):>5}  {min_date:<12}  {max_date:<12}  {title}"
        )

    # ── Office breakdown ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("Office for each duplicate:\n")
    for job_id, occurrences in sorted(duplicates.items()):
        office = occurrences[0]["office"]
        print(f"  {job_id}  {office}")


if __name__ == "__main__":
    directory = sys.argv[1] if len(sys.argv) > 1 else JSON_DIR
    csv_path = sys.argv[2] if len(sys.argv) > 2 else "data/duplicates.csv"
    find_duplicates(directory, csv_path)
