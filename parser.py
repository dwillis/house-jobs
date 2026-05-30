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
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List

import llm

from config import JSON_DIR, TEXT_DIR

MODEL_ID = "qwen3.5:397b-cloud"

SYSTEM_PROMPT = """\
You are an expert in parsing congressional job listings from text files split into chunks. \
Extract job listings into a structured JSON array where each listing is an object with consistent fields. \
Handle the following formatting requirements:
1. Convert any non-ASCII characters (including smartquotes, em-dashes, etc.) to their closest ASCII equivalent.
2. Normalize bullet points and list formatting into consistent structures.
3. Maintain hierarchical relationships in nested lists.
4. Preserve paragraph breaks in description fields.
5. Format all dates in ISO 8601 format (YYYY-MM-DD).
6. Fix OCR artifacts before populating any field. Common substitutions from PDF conversion errors include: \
"o2ice" -> "office", "sta2" -> "staff", "sta5" -> "staff", "StaG" -> "Staff", \
"eEorts" -> "efforts", "eEectively" -> "effectively", "enective" -> "effective", \
"enicient" -> "efficient", "onicials" -> "officials", "onicial" -> "official", \
"diniculty" -> "difficulty". Apply the same judgment to any other obvious OCR substitution errors.
7. Never output an empty array for responsibilities or qualifications. If the listing does not have a \
dedicated section for these, extract them from the description text.
8. Output exactly the 12 schema fields listed below and no others. Do not add fields such as \
"preferences", "benefits", "notes", etc. Merge any such content into the appropriate schema field.\
"""

USER_PROMPT = """\
Create a JSON array containing objects for each job listing with the following required fields:
- id: Job ID in format "MEM-XXX-YY", where XXX is the number from the listing (do not use literally XXX). \
Do not carry over IDs from one chunk to the next.
- position_title: Full position title in Title Case. Never use ALL CAPS.
- office: The most specific congressional office or committee name available. Always include the member's \
full name and state/district in the format "Congressman/Congresswoman [Name] ([ST]-[NN])" when identifiable \
from the listing. For committees, use the full formal name. Never use generic descriptors alone such as \
"Texas Democrat", "House GOP Member", "Senior Republican", or "Midwest Conservative Republican". \
If the text only provides a generic description with no name, use that text but note it is unresolved. \
Use null only if no office information whatsoever is present.
- location: Primary work location. Use "Washington, D.C." (with periods) for DC positions. \
Use null only if no location information is present anywhere in the listing.
- posting_date: Date derived from the filename provided at the top of the chunk (format: YYYY-MM-DD)
- description: Full job description
- responsibilities: Array of individual responsibility strings. Each item must be a single, \
actionable responsibility — not a section header (e.g., remove items like "Front Office" or \
"Additional Responsibilities:" that are headers, not responsibilities). Never output an empty array; \
extract items from the description if no dedicated section exists.
- qualifications: Array of individual qualification strings. Strip standalone section headers such as \
"Preferred:" or "Required Education:" from the array. Do not include compensation or benefits items \
(insurance, retirement plans, TSP, leave, student loan repayment) — those belong in salary_info. \
Never output an empty array; extract items from the description if no dedicated section exists.
- how_to_apply: Full application instructions
- salary_info: Salary information if provided. Format ranges as "$XX,000-$YY,000 per year" \
(no decimals; append "per year" if not already stated). Format single values as "$XX,000 per year". \
If benefits are described alongside salary, include them here. Use null if no salary information is present.
- contact: Primary contact for applications. If not stated explicitly, extract the email address \
from the how_to_apply text or anywhere else in the listing. Use null only if no contact information \
exists anywhere in the listing.
- equal_opportunity: Equal opportunity statement if present (use null if not specified)

Do not process introductory boilerplate language or subscribe/unsubscribe sections as job listings. \
Format all text fields as UTF-8 strings, convert bullet points to array elements, and maintain paragraph \
structure in longer text fields. Remove any formatting characters while preserving the semantic structure \
of the content.

GOOD OUTPUT EXAMPLE (one listing — use this as a model for all fields):
[
  {{
    "id": "MEM-042-25",
    "position_title": "Legislative Assistant",
    "office": "Congresswoman Jane Smith (CA-12)",
    "location": "Washington, D.C.",
    "posting_date": "2025-03-10",
    "description": "The office of Congresswoman Jane Smith seeks a Legislative Assistant to handle \
energy and environment policy. The ideal candidate is detail-oriented and has prior Hill experience.",
    "responsibilities": [
      "Draft legislation, amendments, and policy memos on energy and environment issues",
      "Monitor legislative developments and brief the Member on relevant bills",
      "Represent the office at hearings and coalition meetings",
      "Respond to constituent correspondence on assigned issue areas"
    ],
    "qualifications": [
      "Bachelor's degree required; advanced degree preferred",
      "Minimum two years of Capitol Hill or policy experience",
      "Strong written and verbal communication skills",
      "Familiarity with the legislative process"
    ],
    "how_to_apply": "Submit a resume, cover letter, and two writing samples to jobs@smith.house.gov \
with subject line 'Legislative Assistant Application'.",
    "salary_info": "$55,000-$65,000 per year",
    "contact": "jobs@smith.house.gov",
    "equal_opportunity": "This office is an equal opportunity employer and does not discriminate \
on the basis of race, color, religion, sex, national origin, age, or disability."
  }}
]\
"""


OLLAMA_API = "http://localhost:11434"


def _verify_ollama_model(model_id: str) -> None:
    """Refresh Ollama model list and verify model_id is available."""
    url = f"{OLLAMA_API}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
    except urllib.error.URLError as exc:
        raise SystemExit(f"Ollama is not reachable at {OLLAMA_API}: {exc}") from exc

    available = [m["name"] for m in data.get("models", [])]
    if model_id not in available:
        names = ", ".join(available) if available else "(none pulled)"
        raise SystemExit(
            f"Model '{model_id}' is not available in Ollama.\n"
            f"Available: {names}\n"
            f"Pull it with: ollama pull {model_id}"
        )
    print(f"Ollama model '{model_id}' confirmed available.")


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

    _verify_ollama_model(args.model)
    model = llm.get_model(args.model)
    needs_key = getattr(model, "needs_key", None)
    if needs_key:
        key = llm.get_key(needs_key) if hasattr(llm, "get_key") else None
        if not key:
            raise SystemExit(
                f"API key for '{needs_key}' is not configured.\n"
                f"Run: llm keys set {needs_key}"
            )
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
