"""Tests for training/training/train.py:_evaluate - the batched-validation
fix for the WOW Brain v2 training stall (previously one example at a time,
no batching at all; measured ~13 minutes for 3,378 val examples on CPU).

Uses a tiny hand-built torch model, not a real HuggingFace checkpoint, so
this stays fast and network-free like the rest of training/tests/.
"""

import torch
from torch.utils.data import Dataset

from training.training.train import _evaluate


class _FakeOutput:
    def __init__(self, logits):
        self.logits = logits


class _FakeModel(torch.nn.Module):
    """Ignores the actual input content and instead reads the class index
    to predict directly out of `input_ids[:, 0]` - lets a test encode an
    exact, known prediction per example instead of depending on real
    learned weights."""

    def __init__(self, num_classes: int):
        super().__init__()
        self.num_classes = num_classes
        self.dummy_param = torch.nn.Parameter(torch.zeros(1))  # so .to(device) has something to move

    def forward(self, input_ids):
        predicted_class = input_ids[:, 0]
        return _FakeOutput(torch.nn.functional.one_hot(predicted_class, num_classes=self.num_classes).float() * 10)


class _FakeDataset(Dataset):
    def __init__(self, items):
        self.items = items  # list of (predicted_class, true_label)

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        predicted_class, true_label = self.items[idx]
        return {"input_ids": torch.tensor([predicted_class]), "labels": torch.tensor(true_label)}


def test_evaluate_returns_none_for_empty_dataset():
    model = _FakeModel(num_classes=2)
    result = _evaluate(model, _FakeDataset([]), device=torch.device("cpu"))
    assert result is None


def test_evaluate_computes_correct_accuracy_all_correct():
    items = [(0, 0), (1, 1), (0, 0), (1, 1)]
    model = _FakeModel(num_classes=2)
    acc = _evaluate(model, _FakeDataset(items), device=torch.device("cpu"), batch_size=2)
    assert acc == 1.0


def test_evaluate_computes_correct_accuracy_partial_correct():
    # 3 correct, 1 wrong (last example predicts class 0 but true label is 1).
    items = [(0, 0), (1, 1), (0, 0), (0, 1)]
    model = _FakeModel(num_classes=2)
    acc = _evaluate(model, _FakeDataset(items), device=torch.device("cpu"), batch_size=2)
    assert acc == 0.75


def test_evaluate_is_correct_across_multiple_batches_not_just_one():
    # 10 examples, batch_size=3 -> 4 batches (3,3,3,1), with a known mix of
    # right/wrong spread across batch boundaries.
    items = [(i % 2, i % 2) for i in range(10)]
    items[0] = (1, 0)  # force one wrong prediction in the first batch
    items[9] = (0, 1)  # force one wrong prediction in the last (partial) batch
    model = _FakeModel(num_classes=2)
    acc = _evaluate(model, _FakeDataset(items), device=torch.device("cpu"), batch_size=3)
    assert acc == 0.8  # 8/10 correct


def test_evaluate_matches_unbatched_single_example_batch_size():
    items = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
    model = _FakeModel(num_classes=2)
    acc_batched = _evaluate(model, _FakeDataset(items), device=torch.device("cpu"), batch_size=32)
    acc_one_at_a_time = _evaluate(model, _FakeDataset(items), device=torch.device("cpu"), batch_size=1)
    assert acc_batched == acc_one_at_a_time
