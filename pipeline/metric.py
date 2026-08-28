"""Hybrid GEPA metric: programmatic rule checks + gold-set field scoring.

Used both as a GEPA feedback metric (returns a score + textual feedback
naming which checks failed) and as a plain scorer for eval/reporting.
"""

import difflib
import re
from typing import Any

import dspy

from pipeline.schema import JobListing

ID_RE = re.compile(r"^MEM-\d{3}-\d{2}$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
OFFICE_DISTRICT_RE = re.compile(r"\([A-Z]{2}-\d{2}\)")
SALARY_RE = re.compile(r"^\$[\d,]+(-\$[\d,]+)? per year")
OCR_ARTIFACT_RE = re.compile(
    r"[a-z]&[a-z]|o2ice|sta2|sta5|e2ort|enicient|onicial|diniculty|eEort|enective", re.IGNORECASE
)

NULLABLE_FIELDS = ["office", "location", "posting_date", "how_to_apply", "salary_info", "contact"]
STRING_FIELDS = [
    "office",
    "location",
    "posting_date",
    "description",
    "how_to_apply",
    "salary_info",
    "contact",
    "equal_opportunity",
]


def _all_text(job: JobListing) -> str:
    parts = [job.position_title, job.description] + job.responsibilities + job.qualifications
    for f in STRING_FIELDS:
        v = getattr(job, f)
        if v:
            parts.append(v)
    return "\n".join(parts)


def programmatic_score(job: JobListing) -> tuple[float, list[str]]:
    """Composite 0-1 score from mechanical formatting rules. Returns (score, failures)."""
    checks: list[tuple[bool, str]] = []

    checks.append((bool(ID_RE.match(job.id)), f"id '{job.id}' does not match MEM-XXX-YY"))

    if job.posting_date is not None:
        checks.append(
            (bool(ISO_DATE_RE.match(job.posting_date)), f"posting_date '{job.posting_date}' is not ISO 8601")
        )

    if job.office is not None and "committee" not in job.office.lower():
        checks.append(
            (bool(OFFICE_DISTRICT_RE.search(job.office)), f"office '{job.office}' missing (ST-NN)")
        )

    if job.salary_info is not None:
        checks.append(
            (bool(SALARY_RE.match(job.salary_info)), f"salary_info '{job.salary_info}' not in '$X per year' format")
        )

    ocr_hit = OCR_ARTIFACT_RE.search(_all_text(job))
    checks.append((ocr_hit is None, f"OCR artifact left unrepaired: '{ocr_hit.group(0) if ocr_hit else ''}'"))

    checks.append((len(job.responsibilities) > 0, "responsibilities is empty"))
    checks.append((len(job.qualifications) > 0, "qualifications is empty"))

    null_count = sum(1 for f in NULLABLE_FIELDS if getattr(job, f) is None)
    null_penalty = null_count / len(NULLABLE_FIELDS)

    passed = [ok for ok, _ in checks]
    rule_score = sum(passed) / len(passed) if checks else 1.0
    score = max(0.0, rule_score - 0.15 * null_penalty)
    failures = [msg for ok, msg in checks if not ok]
    return score, failures


def _text_similarity(a: str | None, b: str | None) -> float:
    if a is None and b is None:
        return 1.0
    if a is None or b is None:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _list_similarity(a: list[str], b: list[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    remaining = list(b)
    total = 0.0
    for item in a:
        if not remaining:
            break
        best_idx, best_score = 0, 0.0
        for i, cand in enumerate(remaining):
            s = difflib.SequenceMatcher(None, item, cand).ratio()
            if s > best_score:
                best_idx, best_score = i, s
        total += best_score
        remaining.pop(best_idx)
    return total / max(len(a), len(b))


def gold_score(pred: JobListing, gold: JobListing) -> tuple[float, list[str]]:
    """Field-level similarity of a predicted job against a hand-corrected gold job."""
    scores: dict[str, float] = {}

    scores["id"] = 1.0 if pred.id == gold.id else 0.0
    scores["posting_date"] = 1.0 if pred.posting_date == gold.posting_date else 0.0
    scores["location"] = 1.0 if pred.location == gold.location else 0.0
    scores["office"] = 1.0 if pred.office == gold.office else _text_similarity(pred.office, gold.office)
    scores["contact"] = 1.0 if pred.contact == gold.contact else 0.0
    scores["salary_info"] = 1.0 if pred.salary_info == gold.salary_info else 0.0

    scores["position_title"] = _text_similarity(pred.position_title, gold.position_title)
    scores["description"] = _text_similarity(pred.description, gold.description)
    scores["how_to_apply"] = _text_similarity(pred.how_to_apply, gold.how_to_apply)
    scores["equal_opportunity"] = _text_similarity(pred.equal_opportunity, gold.equal_opportunity)
    scores["responsibilities"] = _list_similarity(pred.responsibilities, gold.responsibilities)
    scores["qualifications"] = _list_similarity(pred.qualifications, gold.qualifications)

    failures = [f"{field} mismatch (score={s:.2f})" for field, s in scores.items() if s < 0.7]
    return sum(scores.values()) / len(scores), failures


def extraction_metric(gold_example: dspy.Example, pred: dspy.Prediction, trace=None, pred_name=None, pred_trace=None):
    """GEPA-compatible metric for the extraction module. Aligns jobs by id when a gold example is provided."""
    pred_jobs: list[JobListing] = pred.jobs if hasattr(pred, "jobs") else pred

    if not pred_jobs:
        return dspy.Prediction(score=0.0, feedback="No jobs were extracted from this chunk.")

    prog_scores: list[float] = []
    prog_failures: list[str] = []
    for job in pred_jobs:
        s, fails = programmatic_score(job)
        prog_scores.append(s)
        prog_failures.extend(f"[{job.id}] {f}" for f in fails)
    prog_avg = sum(prog_scores) / len(prog_scores)

    gold_jobs: list[JobListing] = getattr(gold_example, "jobs", None) or []
    if not gold_jobs:
        score = prog_avg
        feedback = "Programmatic checks only (no gold labels for this example).\n" + "\n".join(prog_failures)
        return dspy.Prediction(score=score, feedback=feedback.strip())

    gold_by_id = {j.id: j for j in gold_jobs}
    gold_scores: list[float] = []
    gold_failures: list[str] = []
    matched_ids = set()
    for job in pred_jobs:
        gold_job = gold_by_id.get(job.id)
        if gold_job is None:
            gold_scores.append(0.0)
            gold_failures.append(f"[{job.id}] no matching gold job id")
            continue
        matched_ids.add(job.id)
        s, fails = gold_score(job, gold_job)
        gold_scores.append(s)
        gold_failures.extend(f"[{job.id}] {f}" for f in fails)

    for missing_id in set(gold_by_id) - matched_ids:
        gold_scores.append(0.0)
        gold_failures.append(f"gold job {missing_id} was not extracted at all")

    gold_avg = sum(gold_scores) / len(gold_scores) if gold_scores else 0.0
    score = 0.5 * prog_avg + 0.5 * gold_avg
    feedback = "\n".join(prog_failures + gold_failures) or "All checks passed."
    return dspy.Prediction(score=score, feedback=feedback)


def classification_metric(gold_example: dspy.Example, pred: dspy.Prediction, trace=None, pred_name=None, pred_trace=None):
    """GEPA-compatible metric for the classification module: exact-match accuracy."""
    correct = pred.job_category == gold_example.job_category
    score = 1.0 if correct else 0.0
    feedback = (
        "Correct."
        if correct
        else f"Predicted '{pred.job_category}' but the correct category is '{gold_example.job_category}'."
    )
    return dspy.Prediction(score=score, feedback=feedback)


def _self_test() -> None:
    job = JobListing(
        id="MEM-042-25",
        position_title="Legislative Assistant",
        office="Congresswoman Jane Smith (CA-12)",
        location="Washington, D.C.",
        posting_date="2025-03-10",
        description="Handles energy and environment policy.",
        responsibilities=["Draft legislation on energy issues"],
        qualifications=["Bachelor's degree required"],
        how_to_apply="Submit a resume to jobs@smith.house.gov",
        salary_info="$55,000-$65,000 per year",
        contact="jobs@smith.house.gov",
        equal_opportunity="Equal opportunity employer.",
    )
    prog, fails = programmatic_score(job)
    print(f"clean job programmatic score: {prog:.3f} (failures={fails})")
    assert prog >= 0.95, "clean job should score near 1.0"

    gold, fails = gold_score(job, job)
    print(f"job vs itself gold score: {gold:.3f} (failures={fails})")
    assert gold >= 0.99, "identical job should score 1.0"

    empty = JobListing(id="MEM-999-25", position_title="X", description="")
    prog_empty, fails_empty = programmatic_score(empty)
    print(f"empty-ish job programmatic score: {prog_empty:.3f} (failures={fails_empty})")
    assert prog_empty < 0.7, "empty responsibilities/qualifications should score low"

    print("self-test passed.")


if __name__ == "__main__":
    _self_test()
