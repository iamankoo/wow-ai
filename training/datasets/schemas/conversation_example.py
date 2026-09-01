"""Schema for a single-turn caller<->WOW exchange with expected handling."""

from pydantic import BaseModel, Field

from training.datasets.schemas.common import Language
from training.wow_taxonomy import Action, CallerRelationship, ContextMode, Intent


class ConversationExample(BaseModel):
    caller_message: str = Field(min_length=1)
    wow_response: str = Field(min_length=1)
    context_mode: ContextMode
    caller_relationship: CallerRelationship
    language: Language
    expected_intent: Intent
    expected_action: Action
    expected_outcome: str = Field(min_length=1)
