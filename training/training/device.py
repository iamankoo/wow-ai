"""Training-time device selection (CUDA -> MPS -> CPU).

Deliberately a small, standalone module with no dependency on
backend/app/ml/device.py (the inference-side equivalent) beyond both being
thin wrappers around the same torch APIs - forcing a cross-package import
for ~20 lines of pure torch logic would add sys.path coupling for no real
benefit, since there's no business logic here to keep in sync (unlike the
WOW taxonomy, which genuinely must have one source of truth).

This module only ever chooses where TRAINING runs. Inference device
selection is separate and defaults to CPU regardless of what training used
- see backend/app/ml/device.py and docs/TRAINING.md "Training vs inference
device".
"""

SUPPORTED_DEVICES = ("auto", "cpu", "cuda", "mps")


def resolve_training_device(requested: str = "auto"):
    """Returns a torch.device for `requested` (one of SUPPORTED_DEVICES).

    - "cpu"/"cuda"/"mps": used as-is; raises RuntimeError if the requested
      accelerator isn't actually available, rather than silently falling
      back to CPU and pretending GPU training happened.
    - "auto": CUDA -> MPS -> CPU, first available wins.
    """
    import torch

    requested = (requested or "auto").lower()
    if requested not in SUPPORTED_DEVICES:
        raise ValueError(
            f"Unsupported training_device '{requested}'. Expected one of: "
            f"{', '.join(SUPPORTED_DEVICES)}."
        )

    if requested == "cpu":
        return torch.device("cpu")

    if requested == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError(
                "training_device=cuda was requested but CUDA is not available "
                "on this machine (torch.cuda.is_available() is False). Install "
                "a CUDA-enabled torch build, or set training_device=auto/cpu."
            )
        return torch.device("cuda")

    if requested == "mps":
        if not _mps_available():
            raise RuntimeError(
                "training_device=mps was requested but MPS is not available "
                "on this machine. Set training_device=auto/cpu."
            )
        return torch.device("mps")

    # auto
    if torch.cuda.is_available():
        return torch.device("cuda")
    if _mps_available():
        return torch.device("mps")
    return torch.device("cpu")


def _mps_available() -> bool:
    import torch

    return hasattr(torch.backends, "mps") and torch.backends.mps.is_available()


def describe_device(device) -> dict:
    """Human/log-friendly device info: type, GPU name/memory where
    applicable, and raw CUDA/MPS availability (independent of what was
    actually selected) so the training log always shows the full picture."""
    import torch

    info = {
        "device": str(device),
        "cuda_available": torch.cuda.is_available(),
        "mps_available": _mps_available(),
    }
    if device.type == "cuda":
        idx = device.index if device.index is not None else 0
        info["gpu_name"] = torch.cuda.get_device_name(idx)
        props = torch.cuda.get_device_properties(idx)
        info["gpu_memory_gb"] = round(props.total_memory / (1024 ** 3), 2)
    return info
