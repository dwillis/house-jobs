"""Structured schema for parsed job listings and classification categories."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

Category = Literal[
    "administrative",
    "legislative",
    "communications",
    "constituent_services",
]


class JobListing(BaseModel):
    id: str = Field(description='Job ID in the format "MEM-XXX-YY"')
    position_title: str = Field(description="Full position title in Title Case")
    office: Optional[str] = Field(
        default=None,
        description='Congressional office, e.g. "Congresswoman Jane Smith (CA-12)", or committee name',
    )
    location: Optional[str] = Field(default=None, description='Primary work location, e.g. "Washington, D.C."')
    posting_date: Optional[str] = Field(default=None, description="ISO 8601 date (YYYY-MM-DD)")
    description: str = Field(description="Full job description")
    responsibilities: list[str] = Field(default_factory=list, description="Individual responsibility strings")
    qualifications: list[str] = Field(default_factory=list, description="Individual qualification strings")
    how_to_apply: Optional[str] = Field(default=None, description="Application instructions")
    salary_info: Optional[str] = Field(default=None, description='e.g. "$55,000-$65,000 per year"')
    contact: Optional[str] = Field(default=None, description="Primary contact for applications")
    equal_opportunity: Optional[str] = Field(default=None, description="Equal opportunity statement, if present")
