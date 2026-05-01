"""Validate JSON files in a directory and report any that fail to parse.

By default this is a read-only check: it lists invalid files and writes a CSV
report. Pass `--delete` to also remove invalid files (this is destructive and
unrecoverable).
"""

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


def validate_json_files(directory_path: str, delete: bool = False) -> Tuple[int, int, Optional[Path]]:
    """Validate every *.json file in `directory_path`.

    Returns (total_files, invalid_count, csv_report_path_or_None).
    Only deletes invalid files when `delete=True`.
    """
    dir_path = Path(directory_path)
    if not dir_path.is_dir():
        raise ValueError(f"'{directory_path}' is not a valid directory")

    total_files = 0
    invalid_files: List[dict] = []

    for file_path in dir_path.glob("*.json"):
        total_files += 1
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                json.load(f)
        except json.JSONDecodeError as e:
            invalid_files.append({
                "file_path": file_path,
                "file_name": file_path.name,
                "error_message": str(e),
                "error_line": e.lineno,
                "error_column": e.colno,
            })
        except Exception as e:
            invalid_files.append({
                "file_path": file_path,
                "file_name": file_path.name,
                "error_message": f"Error reading file: {e}",
                "error_line": "N/A",
                "error_column": "N/A",
            })

    if not invalid_files:
        return total_files, 0, None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_csv = dir_path / f"invalid_json_report_{timestamp}.csv"

    fieldnames = ["file_name", "error_message", "error_line", "error_column"]
    with open(output_csv, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for info in invalid_files:
            writer.writerow({k: info[k] for k in fieldnames})

    if delete:
        deletion_errors = []
        for info in invalid_files:
            try:
                info["file_path"].unlink()
            except Exception as e:
                deletion_errors.append(f"Could not delete {info['file_name']}: {e}")
        if deletion_errors:
            print("\nWarning: Some files could not be deleted:")
            for err in deletion_errors:
                print(err)

    return total_files, len(invalid_files), output_csv


def main() -> int:
    p = argparse.ArgumentParser(
        description="Validate JSON files in a directory. Read-only by default."
    )
    p.add_argument("directory", help="Directory containing JSON files to validate")
    p.add_argument(
        "--delete",
        action="store_true",
        help="Also delete invalid files (destructive, no undo).",
    )
    args = p.parse_args()

    try:
        total, invalid_count, output_path = validate_json_files(args.directory, delete=args.delete)
    except Exception as e:
        print(f"Error: {e}")
        return 1

    print("\nValidation complete:")
    print(f"  Total JSON files processed: {total}")
    print(f"  Invalid JSON files found:   {invalid_count}")
    if output_path:
        print(f"  Report: {output_path}")
        if args.delete:
            print("  Invalid files have been deleted.")
        else:
            print("  Run again with --delete to remove invalid files.")
    else:
        print("  All files are valid JSON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
