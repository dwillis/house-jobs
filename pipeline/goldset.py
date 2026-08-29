"""Sample and prefill gold-set examples for GEPA optimization.

    uv run python -m pipeline.goldset sample --n 30
    uv run python -m pipeline.goldset prefill
    uv run python -m pipeline.goldset sample-classify --n 50

`sample` picks a stratified set of chunks (by bulletin type and year) and
writes them to gold/extraction/NNN.txt. `prefill` looks up each chunk's job
id in json_qwen/ then json/ to seed a best-effort gold/extraction/NNN.json,
falling back to a live extractor call (requires OLLAMA_API_KEY) or an empty
template. The user hand-corrects the .json files before optimize.py runs.

`sample-classify` builds gold/classification/labels.jsonl from the existing
corpora with a heuristic keyword-based category guess (no API key needed)
for the user to correct.
"""

import argparse
import json
import random
import re
from pathlib import Path

from config import GOLD_DIR, JSON_DIR, TEXT_DIR
from pipeline.chunking import is_bulletin, split_into_job_chunks
from pipeline.schema import JobListing

JSON_QWEN_DIR = "json_qwen"
YEAR_RE = re.compile(r"(20\d{2})")
MEM_ID_RE = re.compile(r"MEM-\d{3}-\d{2}")

KEYWORD_CATEGORIES = {
    "administrative": [
        "office manager", "scheduler", "scheduling", "human resources", "executive assistant",
        "office administrator", "operations", "receptionist", "staff assistant", "office coordinator",
    ],
    "legislative": [
        "legislative assistant", "legislative correspondent", "legislative director", "policy advisor",
        "policy analyst", "legislative counsel", "committee counsel", "legislative aide",
    ],
    "communications": [
        "communications director", "press secretary", "press assistant", "digital director",
        "social media", "communications assistant", "media relations",
    ],
    "constituent_services": [
        "constituent services", "caseworker", "case worker", "field representative",
        "district director", "outreach coordinator", "constituent liaison",
    ],
}


def _year_of(filename: str) -> str:
    m = YEAR_RE.search(filename)
    return m.group(1) if m else "unknown"


def _bulletin_type(filename: str) -> str:
    return "intern" if "intern" in filename.lower() else "member"


def sample_chunks(n: int = 30, seed: int = 0) -> list[tuple[str, str]]:
    """Stratified sample of (filename, chunk_text) across bulletin type and year."""
    text_dir = Path(TEXT_DIR)
    files = sorted(f for f in text_dir.iterdir() if is_bulletin(f.name))

    buckets: dict[tuple[str, str], list[Path]] = {}
    for f in files:
        key = (_bulletin_type(f.name), _year_of(f.name))
        buckets.setdefault(key, []).append(f)

    rng = random.Random(seed)
    for lst in buckets.values():
        rng.shuffle(lst)

    picked: list[tuple[str, str]] = []
    keys = list(buckets)
    i = 0
    guard = 0
    while len(picked) < n and any(buckets.values()) and guard < 100_000:
        guard += 1
        key = keys[i % len(keys)]
        lst = buckets[key]
        if lst:
            f = lst.pop()
            chunks = split_into_job_chunks(f.read_text(encoding="utf-8"))
            if chunks:
                picked.append((f.name, rng.choice(chunks)))
        i += 1
    return picked


def cmd_sample(args: argparse.Namespace) -> None:
    out_dir = Path(GOLD_DIR) / "extraction"
    out_dir.mkdir(parents=True, exist_ok=True)
    picked = sample_chunks(n=args.n, seed=args.seed)
    for idx, (filename, chunk) in enumerate(picked, 1):
        path = out_dir / f"{idx:03d}.txt"
        path.write_text(f"{filename}\n{chunk}", encoding="utf-8")
    print(f"Wrote {len(picked)} chunk sample(s) to {out_dir}/")


def _load_id_index(directory: str) -> dict[str, dict]:
    index: dict[str, dict] = {}
    d = Path(directory)
    if not d.is_dir():
        return index
    for path in d.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for job in data:
            job_id = job.get("id")
            if job_id and job_id not in index:
                index[job_id] = job
    return index


def _to_job_listing(raw: dict) -> JobListing:
    fields = set(JobListing.model_fields)
    filtered = {k: v for k, v in raw.items() if k in fields}
    return JobListing(**filtered)


def cmd_prefill(args: argparse.Namespace) -> None:
    ext_dir = Path(GOLD_DIR) / "extraction"
    txt_files = sorted(ext_dir.glob("*.txt"))
    if not txt_files:
        raise SystemExit(f"No sampled chunks found in {ext_dir}/. Run `sample` first.")

    print("Indexing existing corpora for prefill lookups...")
    qwen_index = _load_id_index(JSON_QWEN_DIR)
    json_index = _load_id_index(JSON_DIR)

    lm = None
    filled, from_qwen, from_json, from_live, empty = 0, 0, 0, 0, 0
    for txt_path in txt_files:
        json_path = txt_path.with_suffix(".json")
        if json_path.exists() and not args.overwrite:
            continue

        content = txt_path.read_text(encoding="utf-8")
        m = MEM_ID_RE.search(content)
        job_id = m.group(0) if m else None

        raw = qwen_index.get(job_id) if job_id else None
        source = "json_qwen"
        if raw is None:
            raw = json_index.get(job_id) if job_id else None
            source = "json"

        if raw is not None:
            job = _to_job_listing(raw)
            json_path.write_text(json.dumps([job.model_dump()], indent=2, ensure_ascii=False), encoding="utf-8")
            filled += 1
            from_qwen += source == "json_qwen"
            from_json += source == "json"
            continue

        if args.live:
            import dspy

            from pipeline.lm import make_lm
            from pipeline.signatures import Extractor

            if lm is None:
                lm = make_lm()
                dspy.configure(lm=lm)
            try:
                lines = content.split("\n", 1)
                filename = lines[0]
                pred = Extractor()(chunk_text=content)
                jobs = [j.model_dump() for j in pred.jobs]
                json_path.write_text(json.dumps(jobs, indent=2, ensure_ascii=False), encoding="utf-8")
                filled += 1
                from_live += 1
                continue
            except Exception as e:
                print(f"  live extraction failed for {txt_path.name}: {e}")

        template = JobListing(
            id=job_id or "MEM-000-00",
            position_title="TODO",
            description="TODO",
        )
        json_path.write_text(json.dumps([template.model_dump()], indent=2, ensure_ascii=False), encoding="utf-8")
        empty += 1

    print(
        f"Prefilled {filled} ({from_qwen} from json_qwen, {from_json} from json, {from_live} live), "
        f"{empty} left as empty templates for hand-labeling."
    )


def _heuristic_category(job_text: str) -> str:
    lowered = job_text.lower()
    for category, keywords in KEYWORD_CATEGORIES.items():
        if any(kw in lowered for kw in keywords):
            return category
    return "administrative"


def job_text_from_dict(job: dict) -> str:
    resp = job.get("responsibilities") or []
    quals = job.get("qualifications") or []
    resp_text = " ".join(resp) if isinstance(resp, list) else str(resp)
    quals_text = " ".join(quals) if isinstance(quals, list) else str(quals)
    return (
        f"Position Title: {job.get('position_title', '')}\n"
        f"Office: {job.get('office', '')}\n"
        f"Description: {job.get('description', '')}\n"
        f"Responsibilities: {resp_text}\n"
        f"Qualifications: {quals_text}"
    )


def cmd_sample_classify(args: argparse.Namespace) -> None:
    out_dir = Path(GOLD_DIR) / "classification"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "labels.jsonl"

    existing_ids: set[str] = set()
    if args.append and out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing_ids.add(json.loads(line).get("id"))
        print(f"Appending to {len(existing_ids)} existing label(s).")

    merged: dict[str, dict] = _load_id_index(args.dir)
    if not merged:
        # fall back to legacy corpora if the requested dir has no jobs
        merged.update(_load_id_index(JSON_DIR))
        merged.update(_load_id_index(JSON_QWEN_DIR))
    jobs = [j for j in merged.values() if j.get("id") not in existing_ids]

    rng = random.Random(args.seed)
    rng.shuffle(jobs)

    if args.balanced:
        # round-robin across heuristic-guessed categories for even representation
        by_cat: dict[str, list[dict]] = {}
        for job in jobs:
            by_cat.setdefault(_heuristic_category(job_text_from_dict(job)), []).append(job)
        picked: list[dict] = []
        cats = list(by_cat)
        i = 0
        while len(picked) < args.n and any(by_cat.values()):
            bucket = by_cat[cats[i % len(cats)]]
            if bucket:
                picked.append(bucket.pop())
            i += 1
    else:
        picked = jobs[: args.n]

    mode = "a" if args.append else "w"
    with out_path.open(mode, encoding="utf-8") as f:
        for job in picked:
            job_text = job_text_from_dict(job)
            record = {
                "id": job.get("id"),
                "position_title": job.get("position_title"),
                "job_text": job_text,
                "job_category": _heuristic_category(job_text),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    verb = "Appended" if args.append else "Wrote"
    print(f"{verb} {len(picked)} classification sample(s) to {out_path}. Hand-correct 'job_category' before optimizing.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    p_sample = sub.add_parser("sample", help="sample chunks for the extraction gold set")
    p_sample.add_argument("--n", type=int, default=30)
    p_sample.add_argument("--seed", type=int, default=0)
    p_sample.set_defaults(func=cmd_sample)

    p_prefill = sub.add_parser("prefill", help="prefill sampled chunks from existing corpora")
    p_prefill.add_argument("--live", action="store_true", help="fall back to a live extractor call when no match is found")
    p_prefill.add_argument("--overwrite", action="store_true", help="re-prefill files that already have a .json")
    p_prefill.set_defaults(func=cmd_prefill)

    p_cls = sub.add_parser("sample-classify", help="sample jobs for the classification gold set")
    p_cls.add_argument("--n", type=int, default=50)
    p_cls.add_argument("--seed", type=int, default=0)
    p_cls.add_argument("--dir", default="json_v3", help="corpus to sample jobs from")
    p_cls.add_argument("--append", action="store_true", help="append to labels.jsonl, skipping already-labeled ids")
    p_cls.add_argument("--balanced", action="store_true", help="round-robin across heuristic categories for class balance")
    p_cls.set_defaults(func=cmd_sample_classify)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
