"""Tests for backend/app/ml/device.py's inference-side device resolution."""

import pytest
import torch

from app.ml.device import resolve_inference_device


def test_default_is_cpu_even_with_no_argument():
    assert resolve_inference_device() == torch.device("cpu")


def test_rejects_unsupported_device_name():
    with pytest.raises(ValueError, match="Unsupported inference_device"):
        resolve_inference_device("tpu")


def test_explicit_cuda_raises_clearly_when_unavailable(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match="CUDA is not available"):
        resolve_inference_device("cuda")


def test_auto_falls_back_to_cpu_when_nothing_available(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    if hasattr(torch.backends, "mps"):
        monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)
    assert resolve_inference_device("auto") == torch.device("cpu")
