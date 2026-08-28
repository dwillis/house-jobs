"""DSPy signatures and modules for extraction and classification."""

import dspy

from pipeline.schema import Category, JobListing


class ExtractJobs(dspy.Signature):
    """Extract congressional job or internship listings from one bulletin chunk.

    The chunk begins with the source filename on its own line, followed by
    text starting at a MEM-XXX-YY job ID; treat that ID as this chunk's job id
    and never carry an ID over from another chunk. Derive posting_date from
    the filename. Repair OCR/ligature damage before populating any field
    (e.g. "o2ice"/"O&ice" -> "office", "sta2"/"sta5"/"sta&" -> "staff",
    "eEorts"/"e&orts" -> "efforts", "enicient"/"e&icient" -> "efficient").
    Format office as "Congressman/Congresswoman Name (ST-NN)" when
    identifiable. Format salary as "$XX,000 per year" or
    "$XX,000-$YY,000 per year". Never leave responsibilities or
    qualifications empty if the description contains material that belongs
    there. Do not invent fields beyond the schema, and do not treat
    boilerplate or subscribe/unsubscribe text as a listing.
    """

    chunk_text: str = dspy.InputField(
        desc="Bulletin filename on the first line, then the chunk text starting at a MEM- id"
    )
    jobs: list[JobListing] = dspy.OutputField(desc="One or more job listings extracted from this chunk")


class ClassifyJob(dspy.Signature):
    """Classify a congressional job listing into exactly one category.

    - administrative: office management, HR, scheduling, administrative support
    - legislative: policy research, bill analysis, committee work, legal research
    - communications: press, media relations, social media, public outreach
    - constituent_services: casework, community engagement, district representation
    """

    job_text: str = dspy.InputField(desc="Position title, office, description, responsibilities, qualifications")
    job_category: Category = dspy.OutputField()


class Extractor(dspy.Module):
    def __init__(self) -> None:
        super().__init__()
        self.extract = dspy.ChainOfThought(ExtractJobs)

    def forward(self, chunk_text: str):
        return self.extract(chunk_text=chunk_text)


class Classifier(dspy.Module):
    def __init__(self) -> None:
        super().__init__()
        self.classify = dspy.Predict(ClassifyJob)

    def forward(self, job_text: str):
        return self.classify(job_text=job_text)
