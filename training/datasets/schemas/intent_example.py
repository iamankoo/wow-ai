"""Schema for an intent training example: a single utterance mapped to the
structured intent/context/action the WOW Brain should predict for it.

Covers both the "intent examples" and "context examples" categories from
the training spec - a context-switching utterance is just an intent
example whose intent is SET_CONTEXT/CLEAR_CONTEXT/GET_CONTEXT with a
populated context_mode.
"""

from pydantic import BaseModel, Field, field_validator

from training.datasets.schemas.common import Language
from training.wow_taxonomy import Action, ContextMode, Intent


class IntentExample(BaseModel):
    text: str = Field(min_length=1, description="The raw user/caller utterance.")
    language: Language
    intent: Intent
    context_mode: ContextMode | None = None
    call_handling: bool | None = Field(
        default=None,
        description="Whether this utterance implies call-handling automation should be on.",
    )
    action: Action | None = None
    parameters: dict = Field(default_factory=dict)
    notes: str | None = Field(
        default=None,
        description="Free-text note, e.g. why this example is ambiguous/a correction/a follow-up.",
    )

    @field_validator("text")
    @classmethod
    def _strip_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("text must not be blank")
        return v
