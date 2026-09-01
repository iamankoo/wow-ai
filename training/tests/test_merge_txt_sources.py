"""Tests for training/pipeline/ingest/merge_txt_sources.py, using small
synthetic source files under tmp_path rather than the real multi-million-
row corpus - fast, and exercises the exact same code path.
"""

import json

import pytest

import training.pipeline.ingest.merge_txt_sources as m


@pytest.fixture
def fake_datasets_dir(tmp_path, monkeypatch):
    datasets_dir = tmp_path / "datasets"
    datasets_dir.mkdir()
    (datasets_dir / "hindi_dataset_1.txt").write_text(
        "1. मैं अभी व्यस्त हूँ।\n2. मुझे सोना है।\n", encoding="utf-8",
    )
    (datasets_dir / "hinglish_dataset_1.txt").write_text(
        "1. Main abhi busy hoon.\n2. Main abhi busy hoon.\n",  # deliberate exact duplicate
        encoding="utf-8",
    )
    (datasets_dir / "english_dataset_1.txt").write_text(
        "1. Call me at 9876543210 please.\n2. \n3. I need to make tea because reasons.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(m, "DATASETS_DIR", datasets_dir)
    monkeypatch.setattr(m, "SOURCE_FILES", [
        ("hindi_dataset_1.txt", "hi"),
        ("hinglish_dataset_1.txt", "hinglish"),
        ("english_dataset_1.txt", "en"),
    ])
    return datasets_dir


def test_verify_source_files_finds_all_configured_files(fake_datasets_dir):
    reports = m.verify_source_files(compute_hash=False)
    assert len(reports) == 3
    assert all(r.exists for r in reports)
    assert [r.filename for r in reports] == [
        "hindi_dataset_1.txt", "hinglish_dataset_1.txt", "english_dataset_1.txt",
    ]  # processing order preserved


def test_verify_source_files_reports_missing_file(fake_datasets_dir, monkeypatch):
    monkeypatch.setattr(m, "SOURCE_FILES", m.SOURCE_FILES + [("does_not_exist.txt", "en")])
    reports = m.verify_source_files(compute_hash=False)
    missing = [r for r in reports if not r.exists]
    assert len(missing) == 1
    assert missing[0].filename == "does_not_exist.txt"


def test_ingest_to_master_processes_files_in_order_with_unique_ids(fake_datasets_dir, tmp_path):
    output = tmp_path / "master.jsonl"
    summary = m.ingest_to_master(output, progress_every=0)
    # 2 (hindi) + 2 (hinglish) + 3 (english: entries "1.", "2." with empty
    # text, and "3." - a numbered entry with no content after it is still
    # a distinct entry, just an empty one, flagged later by the quality
    # pass rather than silently skipped)
    assert summary.total_ingested == 7

    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    ids = [r["id"] for r in records]
    assert len(ids) == len(set(ids))  # all unique

    # processing order: hindi entries first, then hinglish, then english
    assert records[0]["source_file"] == "hindi_dataset_1.txt"
    assert records[2]["source_file"] == "hinglish_dataset_1.txt"
    assert records[4]["source_file"] == "english_dataset_1.txt"


def test_ingest_preserves_source_lineage(fake_datasets_dir, tmp_path):
    output = tmp_path / "master.jsonl"
    m.ingest_to_master(output, progress_every=0)
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    first = records[0]
    assert first["source_file"] == "hindi_dataset_1.txt"
    assert first["source_order"] == 1
    assert first["source_line"] == 1
    assert first["source_language"] == "hi"
    assert first["language"] == "hi"


def test_ingest_assigns_null_labels_not_guessed_ones(fake_datasets_dir, tmp_path):
    output = tmp_path / "master.jsonl"
    m.ingest_to_master(output, progress_every=0)
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    for r in records:
        assert r["intent"] is None
        assert r["context"] is None
        assert r["action"] is None
        assert r["label_source"] is None


def test_fully_blank_line_with_no_number_is_not_a_record(fake_datasets_dir, tmp_path, monkeypatch):
    """Distinct from "N. " with empty content (still a record, see
    test_ingest_to_master_processes_files_in_order_with_unique_ids) - a
    line that isn't numbered at all is a separator/header, never an
    entry."""
    (fake_datasets_dir / "hindi_dataset_1.txt").write_text(
        "1. First.\n\n\n2. Second.\n", encoding="utf-8",
    )
    monkeypatch.setattr(m, "SOURCE_FILES", [("hindi_dataset_1.txt", "hi")])
    output = tmp_path / "master.jsonl"
    summary = m.ingest_to_master(output, progress_every=0)
    assert summary.total_ingested == 2


def test_quality_pass_detects_exact_duplicate(fake_datasets_dir, tmp_path):
    master = tmp_path / "master.jsonl"
    clean = tmp_path / "clean.jsonl"
    review = tmp_path / "review.jsonl"
    m.ingest_to_master(master, progress_every=0)
    summary = m.run_quality_pass(master, clean, review, progress_every=0)
    assert summary.exact_duplicates == 1  # the two identical hinglish lines

    review_records = [json.loads(line) for line in review.read_text(encoding="utf-8").splitlines()]
    assert any("exact_duplicate" in r.get("review_reasons", []) for r in review_records)


def test_quality_pass_detects_pii_and_redacts_without_deleting(fake_datasets_dir, tmp_path):
    master = tmp_path / "master.jsonl"
    clean = tmp_path / "clean.jsonl"
    review = tmp_path / "review.jsonl"
    m.ingest_to_master(master, progress_every=0)
    summary = m.run_quality_pass(master, clean, review, progress_every=0)
    assert summary.pii_detected >= 1

    clean_records = [json.loads(line) for line in clean.read_text(encoding="utf-8").splitlines()]
    pii_record = next(r for r in clean_records if r.get("has_pii"))
    assert "9876543210" not in pii_record["redacted_text"]
    assert "9876543210" in pii_record["text"]  # original text never altered/deleted


def test_quality_pass_flags_empty_text_to_review_not_silently_dropped(fake_datasets_dir, tmp_path, monkeypatch):
    datasets_dir = fake_datasets_dir
    (datasets_dir / "hindi_dataset_1.txt").write_text("1. \n2. Real text here.\n", encoding="utf-8")
    monkeypatch.setattr(m, "SOURCE_FILES", [("hindi_dataset_1.txt", "hi")])

    master = tmp_path / "master.jsonl"
    clean = tmp_path / "clean.jsonl"
    review = tmp_path / "review.jsonl"
    ingest_summary = m.ingest_to_master(master, progress_every=0)
    assert ingest_summary.total_ingested == 2  # "1. " still parses as an entry (empty text)

    quality_summary = m.run_quality_pass(master, clean, review, progress_every=0)
    assert quality_summary.empty_or_invalid >= 1
    review_records = [json.loads(line) for line in review.read_text(encoding="utf-8").splitlines()]
    assert any("empty_or_too_short" in r.get("review_reasons", []) for r in review_records)


def test_no_records_lost_between_master_clean_and_review(fake_datasets_dir, tmp_path):
    master = tmp_path / "master.jsonl"
    clean = tmp_path / "clean.jsonl"
    review = tmp_path / "review.jsonl"
    ingest_summary = m.ingest_to_master(master, progress_every=0)
    quality_summary = m.run_quality_pass(master, clean, review, progress_every=0)
    assert quality_summary.clean_count + quality_summary.review_count == ingest_summary.total_ingested


def test_output_jsonl_is_valid_json_per_line(fake_datasets_dir, tmp_path):
    master = tmp_path / "master.jsonl"
    clean = tmp_path / "clean.jsonl"
    review = tmp_path / "review.jsonl"
    m.ingest_to_master(master, progress_every=0)
    m.run_quality_pass(master, clean, review, progress_every=0)
    for path in (master, clean, review):
        for line in path.read_text(encoding="utf-8").splitlines():
            json.loads(line)  # raises if invalid
