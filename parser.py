"""Parse House job-bulletin text files into structured JSON via LLM.

Splits each text file into chunks at MEM-XXX-YY boundaries and sends each
chunk to the configured model, then concatenates the resulting JSON arrays
into one file per bulletin.
"""

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List

import llm

from config import JSON_DIR, TEXT_DIR

MODEL_ID = "gemma4:26b"

SYSTEM_PROMPT = """\
You are an expert in parsing congressional job listings from text files split into chunks. \
Extract job listings into a structured JSON array where each listing is an object with consistent fields. \
Handle the following formatting requirements:
1. Convert any non-ASCII characters (including smartquotes, em-dashes, etc.) to their closest ASCII equivalent
2. Normalize bullet points and list formatting into consistent structures
3. Maintain hierarchical relationships in nested lists
4. Preserve paragraph breaks in description fields
5. Format all dates in ISO 8601 format (YYYY-MM-DD)\
"""

USER_PROMPT = """\
Create a JSON array containing objects for each job listing with the following required fields:
- id: Job ID in format "MEM-XXX-YY", where XXX is the number from the listing (do not use literally XXX). do not carry over IDs from one chunk to the next.
- position_title: Full position title
- office: Congressional office or committee name - do not use placeholders
- location: Primary work location
- posting_date: Date from filename (format: YYYY-MM-DD)
- description: Full job description
- responsibilities: Array of responsibilities
- qualifications: Array of required qualifications
- how_to_apply: Application instructions
- salary_info: Salary information if provided (use null if not specified)
- contact: Contact information for applications
- equal_opportunity: Equal opportunity statement if present (use null if not specified)
Do not process introductory boilerplate language or subscribe/unsubscribe sections as job listings. \
Format all text fields as UTF-8 strings, convert bullet points to array elements, and maintain paragraph \
structure in longer text fields. Remove any formatting characters while preserving the semantic structure of the content.\
"""


def split_into_job_chunks(text: str) -> List[str]:
    """Split text into chunks at each MEM- ID boundary."""
    chunks = re.split(r"(?=MEM-)", text)[1:]
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def process_chunk(model, chunk: str, filename: str) -> List[Dict]:
    """Send one chunk to the LLM and return the parsed JSON list."""
    chunk_with_filename = f"{filename}\n{chunk}"
    try:
        response = model.prompt(
            f"{USER_PROMPT}\n\n{chunk_with_filename}",
            system=SYSTEM_PROMPT,
            json_object=True,
        )
        text = response.text()
    except Exception as e:
        print(f"  LLM call failed: {e}")
        return []

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  JSON decode error: {e}")
        print(f"  Raw output (first 500 chars): {text[:500]}")
        return []

    # Some Gemini calls wrap the array in {"jobs": [...]} or similar.
    if isinstance(parsed, dict):
        for value in parsed.values():
            if isinstance(value, list):
                return value
        return [parsed]
    return parsed


def is_bulletin(filename: str) -> bool:
    """Process Member and Internship bulletins."""
    if not filename.endswith(".txt"):
        return False
    return ("Member" in filename) or ("Intern" in filename)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--model",
        default=MODEL_ID,
        help=f"llm model id to use (default: {MODEL_ID})",
    )
    p.add_argument(
        "--out",
        default=JSON_DIR,
        help=f"output directory for parsed JSON (default: {JSON_DIR})",
    )
    p.add_argument(
        "--limit",
        "-n",
        type=int,
        default=None,
        help="parse at most N bulletins (useful for model A/B tests)",
    )
    p.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="explicit text filenames to parse (in TEXT_DIR); overrides directory scan",
    )
    p.add_argument(
        "--no-skip",
        action="store_true",
        help="re-parse bulletins even if a JSON file already exists in --out",
    )
    p.add_argument(
        "--sleep-chunk",
        type=float,
        default=8.0,
        help="seconds to wait between chunks (default 8; set 0 for local models)",
    )
    p.add_argument(
        "--sleep-file",
        type=float,
        default=5.0,
        help="seconds to wait between bulletins (default 5; set 0 for local models)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.out)
    output_dir.mkdir(exist_ok=True)
    text_dir = Path(TEXT_DIR)

    already_done = set() if args.no_skip else {p.stem for p in output_dir.glob("*.json")}
    model = llm.get_model(args.model)
    print(f"Using model: {args.model}; writing to: {output_dir}/")

    if args.files:
        candidates = [f for f in args.files if (text_dir / f).exists()]
        missing = set(args.files) - set(candidates)
        for f in missing:
            print(f"  warning: {f} not found in {text_dir}/")
    else:
        candidates = [f for f in sorted(os.listdir(text_dir)) if is_bulletin(f)]

    queue = [f for f in candidates if Path(f).stem not in already_done]
    if args.limit is not None:
        queue = queue[: args.limit]
    print(f"Queued {len(queue)} bulletin(s).")

    for filename in queue:
        print(f"Processing {filename}")
        text = (text_dir / filename).read_text(encoding="utf-8")
        chunks = split_into_job_chunks(text)
        all_jobs: List[Dict] = []

        for i, chunk in enumerate(chunks, 1):
            print(f"  chunk {i}/{len(chunks)}")
            if args.sleep_chunk:
                time.sleep(args.sleep_chunk)
            all_jobs.extend(process_chunk(model, chunk, filename))

        out_path = output_dir / f"{Path(filename).stem}.json"
        out_path.write_text(json.dumps(all_jobs, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  wrote {out_path}")
        if args.sleep_file:
            time.sleep(args.sleep_file)


if __name__ == "__main__":
    main()
