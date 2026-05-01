"""Compare two parser-output directories side-by-side.

Useful for A/B testing different LLMs on the same bulletins. For each bulletin
present in both directories, reports:

  - job count delta
  - job IDs present in one side but not the other
  - per-shared-job field diffs (missing/extra fields, length deltas for
    strings, count deltas for lists)

Usage:
    uv run python compare_parses.py json/ json_gemma_test/
    uv run python compare_parses.py json/ json_gemma_test/ --verbose
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


EXPECTED_FIELDS = [
    "id",
    "position_title",
    "office",
    "location",
    "posting_date",
    "description",
    "responsibilities",
    "qualifications",
    "how_to_apply",
    "salary_info",
    "contact",
    "equal_opportunity",
]


def load(path: Path) -> List[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ! could not load {path}: {e}")
        return []
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                return v
        return [data]
    return data if isinstance(data, list) else []


def index_by_id(jobs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for i, j in enumerate(jobs):
        key = j.get("id") or f"_no_id_{i}"
        out[key] = j
    return out


def field_value_summary(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, list):
        return f"list[{len(v)}]"
    if isinstance(v, str):
        return f"str[{len(v)}]"
    if isinstance(v, dict):
        return f"dict[{len(v)}]"
    return f"{type(v).__name__}({v!r})"


def diff_job(a: Dict[str, Any], b: Dict[str, Any]) -> List[str]:
    """Return human-readable diff lines for two job dicts (a vs b)."""
    notes: List[str] = []
    a_keys = set(a) | set(EXPECTED_FIELDS)
    b_keys = set(b) | set(EXPECTED_FIELDS)
    all_keys = sorted(a_keys | b_keys)

    for k in all_keys:
        in_a = k in a
        in_b = k in b
        va = a.get(k)
        vb = b.get(k)

        a_present = in_a and va not in (None, "", [], {})
        b_present = in_b and vb not in (None, "", [], {})

        if not a_present and not b_present:
            if k in EXPECTED_FIELDS:
                notes.append(f"    {k}: missing in BOTH")
            continue

        if a_present and not b_present:
            notes.append(f"    {k}: A={field_value_summary(va)}  B=missing")
            continue
        if b_present and not a_present:
            notes.append(f"    {k}: A=missing  B={field_value_summary(vb)}")
            continue

        # Both present — report meaningful structural deltas only.
        if isinstance(va, list) and isinstance(vb, list):
            if len(va) != len(vb):
                notes.append(f"    {k}: list lengths A={len(va)} B={len(vb)}")
        elif isinstance(va, str) and isinstance(vb, str):
            if va != vb:
                delta = len(vb) - len(va)
                notes.append(f"    {k}: text differs (len A={len(va)} B={len(vb)} delta={delta:+d})")
        elif type(va) is not type(vb):
            notes.append(f"    {k}: type A={type(va).__name__} B={type(vb).__name__}")
        elif va != vb:
            notes.append(f"    {k}: values differ ({va!r} vs {vb!r})")

    return notes


def compare_file(a_path: Path, b_path: Path, verbose: bool) -> Tuple[int, int]:
    """Return (num_shared_jobs, num_jobs_with_diffs)."""
    a_jobs = index_by_id(load(a_path))
    b_jobs = index_by_id(load(b_path))

    only_a = sorted(set(a_jobs) - set(b_jobs))
    only_b = sorted(set(b_jobs) - set(a_jobs))
    shared = sorted(set(a_jobs) & set(b_jobs))

    print(f"\n=== {a_path.name} ===")
    print(f"  jobs: A={len(a_jobs)}  B={len(b_jobs)}  shared={len(shared)}")
    if only_a:
        print(f"  only in A: {only_a}")
    if only_b:
        print(f"  only in B: {only_b}")

    diffed = 0
    for jid in shared:
        notes = diff_job(a_jobs[jid], b_jobs[jid])
        if notes:
            diffed += 1
            if verbose:
                print(f"  {jid}:")
                for n in notes:
                    print(n)
    if not verbose and diffed:
        print(f"  {diffed}/{len(shared)} shared jobs have field-level differences (use --verbose for detail)")

    return len(shared), diffed


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("dir_a", help="baseline parser-output directory")
    p.add_argument("dir_b", help="comparison parser-output directory")
    p.add_argument("--verbose", "-v", action="store_true", help="show per-field diffs for every differing job")
    args = p.parse_args()

    a_dir = Path(args.dir_a)
    b_dir = Path(args.dir_b)
    a_files = {p.name for p in a_dir.glob("*.json")}
    b_files = {p.name for p in b_dir.glob("*.json")}

    only_a = sorted(a_files - b_files)
    only_b = sorted(b_files - a_files)
    shared = sorted(a_files & b_files)

    print(f"Comparing A={a_dir}/  vs  B={b_dir}/")
    print(f"  files: A={len(a_files)}  B={len(b_files)}  shared={len(shared)}")
    if only_a:
        print(f"  only in A ({len(only_a)}): {only_a[:5]}{' ...' if len(only_a) > 5 else ''}")
    if only_b:
        print(f"  only in B ({len(only_b)}): {only_b[:5]}{' ...' if len(only_b) > 5 else ''}")

    total_shared = 0
    total_diffed = 0
    for fname in shared:
        shared_jobs, diffed = compare_file(a_dir / fname, b_dir / fname, args.verbose)
        total_shared += shared_jobs
        total_diffed += diffed

    print()
    print("=== summary ===")
    print(f"  bulletins compared: {len(shared)}")
    print(f"  shared jobs:        {total_shared}")
    print(f"  jobs with diffs:    {total_diffed} ({(total_diffed / total_shared * 100) if total_shared else 0:.1f}%)")


if __name__ == "__main__":
    main()
