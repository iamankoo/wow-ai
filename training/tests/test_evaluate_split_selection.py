"""Tests for training/evaluation/evaluate.py's --split/--config support:
run_evaluation must read the requested split (val or test) from the
requested dataset_dir, never silently fall back to a different file. Uses
a monkeypatched TrainingConfig.load so no real model or real dataset is
needed - these are pure file-selection/wiring tests, not accuracy tests.
"""

import json

import pytest

import training.evaluation.evaluate as evaluate_module
from training.evaluation.evaluate import run_evaluation


def _write_jsonl(path, records):
    path.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )


def _record(text, intent="GENERAL_CONVERSATION", language="en"):
    return {"text": text, "language": language, "intent": intent}


@pytest.fixture
def fake_dataset_dir(tmp_path, monkeypatch):
    """A tiny train/val/test.jsonl trio with distinguishable content, and
    TrainingConfig.load patched to point at it regardless of config_path -
    isolates these tests from needing a real model_config*.yaml on disk."""
    _write_jsonl(tmp_path / "train.jsonl", [_record("train example")])
    _write_jsonl(tmp_path / "val.jsonl", [_record("val example 1"), _record("val example 2")])
    _write_jsonl(tmp_path / "test.jsonl", [_record("test example")])

    class _FakeConfig:
        dataset_dir = tmp_path

    monkeypatch.setattr(evaluate_module.TrainingConfig, "load", lambda path=None: _FakeConfig())
    return tmp_path


@pytest.mark.asyncio
async def test_default_split_is_val(fake_dataset_dir):
    report = await run_evaluation([])
    assert report["eval_split"] == "val"
    assert report["eval_examples"] == 2


@pytest.mark.asyncio
async def test_split_test_reads_test_jsonl_not_val_jsonl(fake_dataset_dir):
    report = await run_evaluation([], split="test")
    assert report["eval_split"] == "test"
    assert report["eval_examples"] == 1
    assert report["providers"]["rule_based"]["total_examples"] == 1


@pytest.mark.asyncio
async def test_test_split_never_touches_val_or_train_files(fake_dataset_dir):
    val_before = (fake_dataset_dir / "val.jsonl").read_text(encoding="utf-8")
    train_before = (fake_dataset_dir / "train.jsonl").read_text(encoding="utf-8")

    await run_evaluation([], split="test")

    assert (fake_dataset_dir / "val.jsonl").read_text(encoding="utf-8") == val_before
    assert (fake_dataset_dir / "train.jsonl").read_text(encoding="utf-8") == train_before


@pytest.mark.asyncio
async def test_invalid_split_raises(fake_dataset_dir):
    with pytest.raises(ValueError):
        await run_evaluation([], split="bogus")


@pytest.mark.asyncio
async def test_report_includes_dataset_version_from_manifest(tmp_path, monkeypatch):
    _write_jsonl(tmp_path / "train.jsonl", [_record("t")])
    _write_jsonl(tmp_path / "test.jsonl", [_record("t")])
    (tmp_path / "MANIFEST.json").write_text("{}", encoding="utf-8")
    # A versioned dataset dir's own name IS its version (see
    # training.training.train._read_dataset_version) - name this tmp dir
    # accordingly by using its actual basename as the expectation.
    expected_version = tmp_path.name

    class _FakeConfig:
        dataset_dir = tmp_path

    monkeypatch.setattr(evaluate_module.TrainingConfig, "load", lambda path=None: _FakeConfig())

    report = await run_evaluation([], split="test")
    assert report["dataset_version"] == expected_version
