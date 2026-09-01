"""Inference-time device selection for LocalWOWModelProvider.

Deliberately separate from training/training/device.py (the training-side
equivalent): training and inference devices are independent settings by
design. A model trained on a GPU almost always still needs to *serve*
predictions on whatever hardware WOW is actually deployed on - for Phase 1
that's a normal CPU (a personal server or phone-adjacent box), not a GPU.
Defaulting inference to CPU regardless of TRAINING_DEVICE avoids silently
requiring GPU hardware just to run the trained model. See
docs/TRAINING.md "Training vs inference device".

torch is only imported inside these functions, matching
LocalWOWModelProvider's existing lazy-import discipline - importing this
module must not require torch/transformers to be installed.
"""

SUPPORTED_DEVICES = ("auto", "cpu", "cuda", "mps")


def resolve_inference_device(requested: str = "cpu"):
    """Returns a torch.device for `requested`. Defaults to "cpu" (unlike
    training's default of "auto") - inference should never silently start
    requiring a GPU just because one happened to be present."""
    import torch

    requested = (requested or "cpu").lower()
    if requested not in SUPPORTED_DEVICES:
        raise ValueError(
            f"Unsupported inference_device '{requested}'. Expected one of: "
            f"{', '.join(SUPPORTED_DEVICES)}."
        )

    if requested == "cpu":
        return torch.device("cpu")
    if requested == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError(
                "inference_device=cuda was requested but CUDA is not available "
                "on this machine."
            )
        return torch.device("cuda")
    if requested == "mps":
        if not (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()):
            raise RuntimeError(
                "inference_device=mps was requested but MPS is not available "
                "on this machine."
            )
        return torch.device("mps")

    # auto
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")
