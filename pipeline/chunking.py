"""Bulletin file selection and chunk splitting, shared by the DSPy pipeline."""

import re


def split_into_job_chunks(text: str) -> list[str]:
    """Split bulletin text into chunks at each MEM- ID boundary."""
    chunks = re.split(r"(?=MEM-)", text)[1:]
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def is_bulletin(filename: str) -> bool:
    """Process Member and Internship bulletins (case-insensitive)."""
    if not filename.endswith(".txt"):
        return False
    lowered = filename.lower()
    return ("member" in lowered) or ("intern" in lowered)
