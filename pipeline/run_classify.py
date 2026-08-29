"""Bulk classification of jobs in json_v3/ with the DSPy classification module.

    uv run python -m pipeline.run_classify --eval
    uv run python -m pipeline.run_classify --dir json_v3 --workers 8
"""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import dspy

from config import GOLD_DIR, JSON_V3_DIR
from pipeline.goldset import job_text_from_dict
from pipeline.lm import DEFAULT_MODEL, make_lm
from pipeline.signatures import Classifier

COMPILED_PATH = Path(__file__).parent / "compiled" / "classifier.json"
RETRY_DELAYS = [2.0, 8.0]


def load_classifier(compiled_path: Path | None) -> Classifier:
    program = Classifier()
    if compiled_path and compiled_path.exists():
        program.load(str(compiled_path))
        print(f"Loaded compiled classifier from {compiled_path}")
    else:
        print("Using unoptimized classifier (no compiled artifact found).")
    return program


def classify_one(program: Classifier, job_text: str) -> tuple[str | None, str | None]:
    last_error = None
    for attempt, delay in enumerate([0.0] + RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            pred = program(job_text=job_text)
            return pred.job_category, None
        except Exception as e:
            last_error = str(e)
    return None, last_error


def cmd_eval(program: Classifier) -> None:
    labels_path = Path(GOLD_DIR) / "classification" / "labels.jsonl"
    records = [json.loads(l) for l in labels_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    correct = 0
    for r in records:
        pred, error = classify_one(program, r["job_text"])
        ok = pred == r["job_category"]
        correct += ok
        if not ok:
            print(f"  MISS id={r['id']} pred={pred!r} gold={r['job_category']!r} error={error}")
    print(f"\nAccuracy: {correct}/{len(records)} = {correct / len(records):.3f}")


def _needs_classify(job: dict, no_skip: bool) -> bool:
    return no_skip or not job.get("job_category")


def cmd_run(program: Classifier, out_dir: Path, workers: int, no_skip: bool, max_calls: int | None) -> None:
    failures_path = out_dir / "_classify_failures.jsonl"
    total, updated, failed = 0, 0, 0
    budget_spent = 0
    stopped_early = False

    def classify_job_dict(job: dict) -> dict:
        if not _needs_classify(job, no_skip):
            return job
        category, error = classify_one(program, job_text_from_dict(job))
        if category:
            job["job_category"] = category
        else:
            job["job_category"] = "unclassified"
        return job

    with failures_path.open("a", encoding="utf-8") as fail_log:
        for path in sorted(out_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            jobs = json.loads(path.read_text(encoding="utf-8"))
            if not jobs:
                continue

            pending = sum(1 for j in jobs if _needs_classify(j, no_skip))
            if pending == 0:
                continue
            if max_calls is not None and budget_spent > 0 and budget_spent + pending > max_calls:
                stopped_early = True
                break
            budget_spent += pending
            total += len(jobs)

            if workers > 1:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    new_jobs = list(pool.map(classify_job_dict, jobs))
            else:
                new_jobs = [classify_job_dict(j) for j in jobs]

            for j in new_jobs:
                if j.get("job_category") == "unclassified":
                    failed += 1
                    fail_log.write(json.dumps({"file": path.name, "id": j.get("id")}) + "\n")
                else:
                    updated += 1

            tmp_path = path.with_suffix(".json.tmp")
            tmp_path.write_text(json.dumps(new_jobs, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp_path.replace(path)
            print(f"  {path.name}: {len(jobs)} job(s) classified")

    note = f" (stopped early at ~{budget_spent} call budget; re-run to continue)" if stopped_early else ""
    print(f"\nDone. {updated}/{total} classified, {failed} failed (see {failures_path}).{note}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", default=JSON_V3_DIR)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--compiled", default=str(COMPILED_PATH))
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--no-skip", action="store_true", help="reclassify jobs that already have a job_category")
    p.add_argument(
        "--max-calls",
        type=int,
        default=None,
        help="stop before a file whose unclassified jobs would push the cumulative count over this budget",
    )
    p.add_argument("--eval", action="store_true", help="report accuracy against gold labels instead of running")
    p.add_argument(
        "--max-tokens",
        type=int,
        default=16000,
        help="LM output token budget; raise if glm-5.2 reasoning truncates (warning about max_tokens)",
    )
    args = p.parse_args()

    dspy.configure(lm=make_lm(model=args.model, max_tokens=args.max_tokens))
    program = load_classifier(Path(args.compiled) if args.compiled else None)

    if args.eval:
        cmd_eval(program)
    else:
        cmd_run(program, Path(args.dir), args.workers, args.no_skip, args.max_calls)


if __name__ == "__main__":
    main()
