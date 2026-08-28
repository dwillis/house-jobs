"""GEPA optimization runs for the extraction and classification modules.

    uv run python -m pipeline.optimize smoke-test
    uv run python -m pipeline.optimize extract
    uv run python -m pipeline.optimize classify
"""

import argparse
import json
from pathlib import Path

import dspy

from config import GOLD_DIR
from pipeline.lm import make_lm
from pipeline.metric import classification_metric, extraction_metric
from pipeline.schema import JobListing
from pipeline.signatures import Classifier, Extractor

COMPILED_DIR = Path(__file__).parent / "compiled"


def cmd_smoke_test(args: argparse.Namespace) -> None:
    dspy.configure(lm=make_lm())
    result = dspy.Predict("question -> answer")(question="Say the word OK and nothing else.")
    print(f"LM responded: {result.answer!r}")


def _load_extraction_examples() -> list[dspy.Example]:
    ext_dir = Path(GOLD_DIR) / "extraction"
    examples = []
    for txt_path in sorted(ext_dir.glob("*.txt")):
        json_path = txt_path.with_suffix(".json")
        if not json_path.exists():
            continue
        chunk_text = txt_path.read_text(encoding="utf-8")
        raw_jobs = json.loads(json_path.read_text(encoding="utf-8"))
        if any(j.get("position_title") == "TODO" for j in raw_jobs):
            continue  # unlabeled template, skip until hand-corrected
        jobs = [JobListing(**j) for j in raw_jobs]
        examples.append(dspy.Example(chunk_text=chunk_text, jobs=jobs).with_inputs("chunk_text"))
    return examples


def _load_classification_examples() -> list[dspy.Example]:
    labels_path = Path(GOLD_DIR) / "classification" / "labels.jsonl"
    if not labels_path.exists():
        return []
    examples = []
    for line in labels_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        examples.append(
            dspy.Example(job_text=record["job_text"], job_category=record["job_category"]).with_inputs("job_text")
        )
    return examples


def _split(examples: list[dspy.Example], val_fraction: float = 0.33) -> tuple[list, list]:
    n_val = max(1, int(len(examples) * val_fraction))
    return examples[:-n_val], examples[-n_val:]


def cmd_extract(args: argparse.Namespace) -> None:
    dspy.configure(lm=make_lm(model=args.model))
    reflection_lm = make_lm(model=args.reflection_model, temperature=1.0, max_tokens=32000)

    examples = _load_extraction_examples()
    if len(examples) < 4:
        raise SystemExit(
            f"Only {len(examples)} hand-corrected extraction examples found in {GOLD_DIR}/extraction/. "
            "Run `pipeline.goldset sample` + `prefill`, then hand-correct the .json files first."
        )
    train, val = _split(examples)
    print(f"Extraction gold set: {len(train)} train / {len(val)} val")

    program = Extractor()
    baseline_scores = [extraction_metric(ex, program(**ex.inputs())).score for ex in val]
    print(f"Baseline val score: {sum(baseline_scores) / len(baseline_scores):.3f}")

    gepa = dspy.GEPA(metric=extraction_metric, auto=args.auto, reflection_lm=reflection_lm, track_stats=True)
    optimized = gepa.compile(program, trainset=train, valset=val)

    optimized_scores = [extraction_metric(ex, optimized(**ex.inputs())).score for ex in val]
    print(f"Optimized val score: {sum(optimized_scores) / len(optimized_scores):.3f}")

    COMPILED_DIR.mkdir(exist_ok=True)
    out_path = COMPILED_DIR / "extractor.json"
    optimized.save(str(out_path))
    print(f"Saved compiled extractor to {out_path}")


def cmd_classify(args: argparse.Namespace) -> None:
    dspy.configure(lm=make_lm(model=args.model))
    reflection_lm = make_lm(model=args.reflection_model, temperature=1.0, max_tokens=32000)

    examples = _load_classification_examples()
    if len(examples) < 10:
        raise SystemExit(
            f"Only {len(examples)} classification labels found in {GOLD_DIR}/classification/labels.jsonl. "
            "Run `pipeline.goldset sample-classify` and hand-correct 'job_category' first."
        )
    train, val = _split(examples)
    print(f"Classification gold set: {len(train)} train / {len(val)} val")

    program = Classifier()
    baseline_scores = [classification_metric(ex, program(**ex.inputs())).score for ex in val]
    print(f"Baseline val accuracy: {sum(baseline_scores) / len(baseline_scores):.3f}")

    gepa = dspy.GEPA(metric=classification_metric, auto=args.auto, reflection_lm=reflection_lm, track_stats=True)
    optimized = gepa.compile(program, trainset=train, valset=val)

    optimized_scores = [classification_metric(ex, optimized(**ex.inputs())).score for ex in val]
    print(f"Optimized val accuracy: {sum(optimized_scores) / len(optimized_scores):.3f}")

    COMPILED_DIR.mkdir(exist_ok=True)
    out_path = COMPILED_DIR / "classifier.json"
    optimized.save(str(out_path))
    print(f"Saved compiled classifier to {out_path}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    p_smoke = sub.add_parser("smoke-test", help="verify LM connectivity")
    p_smoke.set_defaults(func=cmd_smoke_test)

    for name, fn in [("extract", cmd_extract), ("classify", cmd_classify)]:
        sp = sub.add_parser(name, help=f"run GEPA optimization for the {name} module")
        sp.add_argument("--model", default="glm-5.2", help="task LM")
        sp.add_argument("--reflection-model", default="glm-5.2", help="LM GEPA uses to propose new instructions")
        sp.add_argument("--auto", default="light", choices=["light", "medium", "heavy"])
        sp.set_defaults(func=fn)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
