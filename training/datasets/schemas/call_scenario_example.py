"""Schema for a caller-identification scenario: given a caller description
and relationship, what should WOW conclude about how to handle the call."""

from pydantic import BaseModel, Field

from training.datasets.schemas.common import Language, Urgency
from training.wow_taxonomy import Action, CallerRelationship, Intent


class CallScenarioExample(BaseModel):
    caller_description: str = Field(min_length=1)
    caller_relationship: CallerRelationship
    language: Language
    expected_intent: Intent
    expected_action: Action
    urgency: Urgency
    notes: str | None = None
