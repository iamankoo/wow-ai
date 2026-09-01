"""Schema for a call-summary training example."""

from pydantic import BaseModel, Field

from training.datasets.schemas.common import Language, Urgency


class SummaryExample(BaseModel):
    transcript: str = Field(min_length=1, description="The full call transcript being summarized.")
    reason_for_call: str = Field(min_length=1)
    important_facts: list[str] = Field(default_factory=list)
    requested_action: str = Field(min_length=1)
    urgency: Urgency
    summary: str = Field(min_length=1, description="The concise expected summary.")
    language: Language
