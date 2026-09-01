"""CLI smoke tests - exercise the actual command functions (not the full
subprocess) against a tmp_path dataset file, since that's fast and still
verifies real wiring end to end.
"""

import json
from argparse import Namespace

import pytest

from training.pipeline import cli
from training.pipeline.schema import RawExample
from training.pipeline.versioning import VERSIONS_DIR


@pytest.fixture
def sample_file(tmp_path):
    examples = [
        RawExample(text="Call Rahul for me.", language="en", intent="CALL_PERSON", action="NO_ACTION"),
        RawExample(text="Priya ko call karo.", language="hi", intent="CALL_PERSON", action="NO_ACTION"),
        RawExample(text="Call Rahul for me.", language="en", intent="CALL_PERSON", action="NO_ACTION"),  # dup
    ]
    path = tmp_path / "sample.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex.to_dict(), ensure_ascii=False) + "\n")
    return path


def test_cmd_validate_reports_no_errors_for_valid_file(sample_file, capsys):
    code = cli.cmd_validate(Namespace(input=sample_file))
    assert code == 0
    assert "0 problem" in capsys.readouterr().out


def test_cmd_validate_reports_errors_for_invalid_intent(tmp_path, capsys):
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps({"text": "x", "language": "en", "intent": "NOT_REAL"}) + "\n", encoding="utf-8")
    code = cli.cmd_validate(Namespace(input=path))
    assert code == 1
    assert "invalid intent" in capsys.readouterr().out


def test_cmd_stats_writes_a_report(sample_file, tmp_path):
    output = tmp_path / "stats.json"
    cli.cmd_stats(Namespace(input=sample_file, output=output))
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["total_scored"] == 3
    assert report["exact_duplicate_count"] == 1


def test_cmd_dedupe_finds_the_planted_duplicate(sample_file, capsys):
    cli.cmd_dedupe(Namespace(input=sample_file))
    assert "Exact duplicates: 1" in capsys.readouterr().out


def test_cmd_filter_keeps_only_passing_examples(sample_file, tmp_path):
    output = tmp_path / "filtered.jsonl"
    cli.cmd_filter(Namespace(input=sample_file, status="pass", output=output))
    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2  # the exact duplicate is rejected, not passing


def test_cmd_split_writes_a_versioned_dataset_with_manifest(sample_file, tmp_path, monkeypatch):
    fake_versions_dir = tmp_path / "versions"
    monkeypatch.setattr(cli, "version_dir_for", lambda v: fake_versions_dir / v)
    code = cli.cmd_split(Namespace(input=sample_file, version="v-test", seed=42))
    assert code == 0
    version_dir = fake_versions_dir / "v-test"
    assert (version_dir / "MANIFEST.json").exists()
    assert (version_dir / "processed" / "train.jsonl").exists()
    assert (version_dir / "processed" / "STATS.json").exists()
