"""Bulk re-parse bulletins into json_v3/ with the DSPy extraction module.

    uv run python -m pipeline.run_parse --out json_v3 --limit 10
    uv run python -m pipeline.run_parse --out json_v3 --workers 6
    uv run python -m pipeline.run_parse --out json_v3 --retry-failures
"""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import dspy

from config import JSON_V3_DIR, TEXT_DIR
from pipeline.chunking import is_bulletin, listing_type, split_into_job_chunks
from pipeline.lm import DEFAULT_MODEL, make_lm
from pipeline.signatures import Extractor

COMPILED_PATH = Path(__file__).parent / "compiled" / "extractor.json"
RETRY_DELAYS = [2.0, 8.0, 30.0]


def load_extractor(compiled_path: Path | None) -> Extractor:
    program = Extractor()
    if compiled_path and compiled_path.exists():
        program.load(str(compiled_path))
        print(f"Loaded compiled extractor from {compiled_path}")
    else:
        print("Using unoptimized extractor (no compiled artifact found).")
    return program


def process_chunk(program: Extractor, chunk: str, filename: str, model_id: str) -> tuple[list[dict], str | None]:
    """Return (job_dicts, error_or_None) for one chunk, with retries."""
    chunk_with_filename = f"{filename}\n{chunk}"
    last_error = None
    for attempt, delay in enumerate([0.0] + RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            pred = program(chunk_text=chunk_with_filename)
            provenance = {
                "source_model": model_id,
                "parsed_at": date.today().isoformat(),
                "listing_type": listing_type(filename),
            }
            jobs = [j.model_dump() | provenance for j in pred.jobs]
            return jobs, None
        except Exception as e:
            last_error = str(e)
    return [], last_error


def process_bulletin(
    program: Extractor, filename: str, text_dir: Path, out_dir: Path, workers: int, model_id: str
) -> tuple[int, list[dict]]:
    text = (text_dir / filename).read_text(encoding="utf-8")
    chunks = split_into_job_chunks(text)
    failures: list[dict] = []
    all_jobs: list[dict] = []

    def run_one(chunk: str) -> tuple[list[dict], str | None]:
        return process_chunk(program, chunk, filename, model_id)

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(run_one, chunks))
    else:
        results = [run_one(c) for c in chunks]

    for i, (jobs, error) in enumerate(results):
        if error:
            failures.append({"file": filename, "chunk_index": i, "error": error, "first_200_chars": chunks[i][:200]})
        all_jobs.extend(jobs)

    out_path = out_dir / f"{Path(filename).stem}.json"
    tmp_path = out_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(all_jobs, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(out_path)

    return len(all_jobs), failures


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default=JSON_V3_DIR)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--compiled", default=str(COMPILED_PATH))
    p.add_argument("--workers", type=int, default=6, help="concurrent chunk workers per bulletin")
    p.add_argument("--limit", "-n", type=int, default=None, help="parse at most N bulletins")
    p.add_argument(
        "--max-calls",
        type=int,
        default=None,
        help="stop queuing bulletins once their cumulative chunk count (~LM calls) would exceed this budget",
    )
    p.add_argument("--files", nargs="*", default=None)
    p.add_argument("--no-skip", action="store_true")
    p.add_argument("--retry-failures", action="store_true", help="only re-run entries from _failures.jsonl")
    p.add_argument(
        "--max-tokens",
        type=int,
        default=8000,
        help="LM output token budget per chunk; raise if glm-5.2 reasoning truncates output",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)
    text_dir = Path(TEXT_DIR)
    failures_path = out_dir / "_failures.jsonl"

    dspy.configure(lm=make_lm(model=args.model, max_tokens=args.max_tokens))
    program = load_extractor(Path(args.compiled) if args.compiled else None)

    if args.retry_failures:
        if not failures_path.exists():
            raise SystemExit(f"No {failures_path} to retry.")
        prior = [json.loads(line) for line in failures_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        candidates = sorted({f["file"] for f in prior})
        already_done: set[str] = set()
    else:
        already_done = set() if args.no_skip else {p.stem for p in out_dir.glob("*.json")}
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

    if args.max_calls is not None:
        budgeted_queue = []
        running_total = 0
        for filename in queue:
            n_chunks = len(split_into_job_chunks((text_dir / filename).read_text(encoding="utf-8")))
            if budgeted_queue and running_total + n_chunks > args.max_calls:
                break
            budgeted_queue.append(filename)
            running_total += n_chunks
        skipped = len(queue) - len(budgeted_queue)
        queue = budgeted_queue
        print(f"Budgeted {len(queue)} bulletin(s) (~{running_total} chunk/LM-call(s), {skipped} deferred to a later batch)")

    print(f"Queued {len(queue)} bulletin(s) -> {out_dir}/")

    total_jobs = 0
    total_failures = 0
    with failures_path.open("a", encoding="utf-8") as fail_log:
        for filename in queue:
            print(f"Processing {filename}")
            n_jobs, failures = process_bulletin(program, filename, text_dir, out_dir, args.workers, args.model)
            total_jobs += n_jobs
            total_failures += len(failures)
            for f in failures:
                fail_log.write(json.dumps(f, ensure_ascii=False) + "\n")
            print(f"  wrote {n_jobs} job(s), {len(failures)} failure(s)")

    print(f"\nDone. {total_jobs} job(s) written, {total_failures} chunk failure(s) (see {failures_path}).")


if __name__ == "__main__":
    main()
