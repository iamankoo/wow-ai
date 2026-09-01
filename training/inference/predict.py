"""Single-utterance prediction CLI - loads a trained WOW Brain model version
and prints its structured prediction (intent / context_mode / action, with
per-head confidence) for one piece of text. Useful for quickly sanity-
checking a model after training, without spinning up the backend.

Usage:
    python -m training.inference.predict "I'm sleeping, handle my calls"
    python -m training.inference.predict --model-dir training/models/wow-brain/v1.1 "Kal ka meeting cancel kar do"
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from training.training.config import REPO_ROOT

BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.interfaces.llm import LLMMessage  # noqa: E402


async def predict(model_dir: Path, text: str, inference_device: str = "cpu") -> dict:
    from app.providers.llm.local_wow import LocalWOWModelProvider

    provider = LocalWOWModelProvider(model_dir, inference_device=inference_device)
    response = await provider.generate([LLMMessage(role="user", content=text)])
    return {
        "text": text,
        "model_version": response.metadata.get("model_version"),
        "intent": response.intent,
        "context_mode": response.slots.get("context_mode"),
        "action": response.slots.get("action"),
        "confidence": response.metadata.get("confidence"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", help="The utterance to classify.")
    parser.add_argument(
        "--model-dir", type=Path,
        default=REPO_ROOT / "training" / "models" / "wow-brain" / "v1",
        help="Path to a trained model version directory (default: v1).",
    )
    parser.add_argument(
        "--inference-device", default="cpu",
        help="auto|cpu|cuda|mps - defaults to cpu, matching production inference. See docs/TRAINING.md.",
    )
    args = parser.parse_args()

    if not args.model_dir.exists():
        raise SystemExit(
            f"No model found at {args.model_dir}. Train one first (see docs/TRAINING.md), "
            "or pass --model-dir to point at an existing model version."
        )

    result = asyncio.run(predict(args.model_dir, args.text, args.inference_device))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
