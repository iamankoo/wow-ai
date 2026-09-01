"""LocalWOWModelProvider - runs WOW's own fine-tuned classification heads
(intent / context / action) locally, with zero dependency on any hosted
third-party AI API.

This is the second rung of the provider ladder:

    RuleBasedLanguageModelProvider (deterministic baseline, always available)
        -> LocalWOWModelProvider (this file - our own trained model)
            -> a future FutureWOWProprietaryModelProvider (larger self-trained/
               self-hosted model, same interface, drop-in replacement)

torch/transformers are only imported inside this module's methods, never at
module import time, so a backend deployment that never enables
MODEL_PROVIDER=local_wow does not need those packages installed at all.

If the trained model artifacts are missing, or torch/transformers are not
installed, this provider raises a clear RuntimeError at construction time -
it never silently falls back to pretending it has a trained model.
"""

import json
from pathlib import Path

from app.interfaces.llm import LanguageModelProvider, LLMMessage, LLMResponse


class ModelNotAvailableError(RuntimeError):
    """Raised when LocalWOWModelProvider cannot load a real trained model."""


class LocalWOWModelProvider(LanguageModelProvider):
    """Loads the intent/context/action classification heads produced by
    training/training/train.py from a model version directory (e.g.
    training/models/wow-brain/v0/) and predicts structured output locally.
    """

    def __init__(self, model_dir: str | Path, *, inference_device: str = "cpu"):
        self._model_dir = Path(model_dir)
        metadata_path = self._model_dir / "metadata.json"
        if not metadata_path.exists():
            raise ModelNotAvailableError(
                f"No WOW model found at {self._model_dir} (missing metadata.json). "
                "Train one with `python -m training.training.train`, or set "
                "MODEL_PROVIDER=rule_based to use the deterministic baseline."
            )

        try:
            import torch  # noqa: F401
            from transformers import AutoModelForSequenceClassification, AutoTokenizer  # noqa: F401
        except ImportError as e:
            raise ModelNotAvailableError(
                "LocalWOWModelProvider requires torch and transformers, which are not "
                "installed. Install backend/requirements-local-model.txt, or set "
                "MODEL_PROVIDER=rule_based to use the deterministic baseline."
            ) from e

        from app.ml.device import resolve_inference_device

        self._device = resolve_inference_device(inference_device)

        self._metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self._heads: dict[str, dict] = {}
        for head_meta in self._metadata.get("heads", []):
            head_name = head_meta["head"]
            head_dir = self._model_dir / head_name
            if not head_dir.exists():
                raise ModelNotAvailableError(
                    f"Model metadata references head '{head_name}' but {head_dir} is missing."
                )
            tokenizer = AutoTokenizer.from_pretrained(head_dir)
            model = AutoModelForSequenceClassification.from_pretrained(head_dir)
            model.to(self._device)
            model.eval()
            self._heads[head_name] = {
                "tokenizer": tokenizer,
                "model": model,
                "id2label": {int(i): label for i, label in model.config.id2label.items()},
            }

    def _predict_head(self, head_name: str, text: str) -> tuple[str | None, float]:
        import torch

        head = self._heads.get(head_name)
        if head is None:
            return None, 0.0

        tokenizer = head["tokenizer"]
        model = head["model"]
        inputs = tokenizer(text, truncation=True, max_length=64, return_tensors="pt")
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        with torch.no_grad():
            logits = model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)[0]
            confidence, pred_id = torch.max(probs, dim=-1)
        label = head["id2label"].get(int(pred_id.item()))
        return label, float(confidence.item())

    async def generate(
        self, messages: list[LLMMessage], *, context: dict | None = None
    ) -> LLMResponse:
        last_user_message = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )

        intent, intent_conf = self._predict_head("intent", last_user_message)
        context_mode, context_conf = self._predict_head("context", last_user_message)
        action, action_conf = self._predict_head("action", last_user_message)

        return LLMResponse(
            content="",  # v0 predicts structure, not free text - callers style the reply
            intent=intent,
            slots={
                "context_mode": context_mode,
                "action": action,
            },
            metadata={
                "provider": "local_wow_v0",
                "model_version": self._metadata.get("model_version"),
                "confidence": {
                    "intent": intent_conf,
                    "context_mode": context_conf,
                    "action": action_conf,
                },
            },
        )
