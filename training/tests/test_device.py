"""Tests for training/training/device.py's device resolution logic.
Monkeypatches torch.cuda/mps availability rather than requiring real
hardware, so these pass identically on CPU-only and GPU-equipped machines.
"""

import pytest
import torch

from training.training.device import describe_device, resolve_training_device


def test_explicit_cpu_always_resolves_to_cpu():
    assert resolve_training_device("cpu") == torch.device("cpu")


def test_rejects_unsupported_device_name():
    with pytest.raises(ValueError, match="Unsupported training_device"):
        resolve_training_device("tpu")


def test_explicit_cuda_raises_clearly_when_unavailable(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match="CUDA is not available"):
        resolve_training_device("cuda")


def test_explicit_cuda_succeeds_when_available(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    assert resolve_training_device("cuda") == torch.device("cuda")


def test_explicit_mps_raises_clearly_when_unavailable(monkeypatch):
    monkeypatch.setattr(
        "training.training.device._mps_available", lambda: False
    )
    with pytest.raises(RuntimeError, match="MPS is not available"):
        resolve_training_device("mps")


def test_auto_prefers_cuda_over_mps_and_cpu(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr("training.training.device._mps_available", lambda: True)
    assert resolve_training_device("auto") == torch.device("cuda")


def test_auto_prefers_mps_over_cpu_when_no_cuda(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr("training.training.device._mps_available", lambda: True)
    assert resolve_training_device("auto") == torch.device("mps")


def test_auto_falls_back_to_cpu_when_nothing_available(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr("training.training.device._mps_available", lambda: False)
    assert resolve_training_device("auto") == torch.device("cpu")


def test_describe_device_reports_availability_flags(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr("training.training.device._mps_available", lambda: False)
    info = describe_device(torch.device("cpu"))
    assert info["device"] == "cpu"
    assert info["cuda_available"] is False
    assert info["mps_available"] is False
    assert "gpu_name" not in info
