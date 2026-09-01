import json

from training.pipeline.versioning import build_manifest, verify_manifest, write_manifest


def test_manifest_records_checksum_and_line_count(tmp_path):
    f = tmp_path / "train.jsonl"
    f.write_text('{"a":1}\n{"a":2}\n{"a":3}\n', encoding="utf-8")

    manifest = build_manifest(tmp_path, [f])
    assert manifest["files"][0]["path"] == "train.jsonl"
    assert manifest["files"][0]["line_count"] == 3
    assert len(manifest["files"][0]["sha256"]) == 64
    assert manifest["total_lines"] == 3


def test_write_and_verify_manifest_round_trips(tmp_path):
    f = tmp_path / "train.jsonl"
    f.write_text('{"a":1}\n', encoding="utf-8")
    write_manifest(tmp_path, [f])

    ok, mismatches = verify_manifest(tmp_path)
    assert ok
    assert mismatches == []


def test_verify_manifest_detects_tampering(tmp_path):
    f = tmp_path / "train.jsonl"
    f.write_text('{"a":1}\n', encoding="utf-8")
    write_manifest(tmp_path, [f])

    f.write_text('{"a":2}\n', encoding="utf-8")  # tamper after manifest was written

    ok, mismatches = verify_manifest(tmp_path)
    assert not ok
    assert any("checksum mismatch" in m for m in mismatches)


def test_verify_manifest_detects_missing_file(tmp_path):
    f = tmp_path / "train.jsonl"
    f.write_text('{"a":1}\n', encoding="utf-8")
    write_manifest(tmp_path, [f])
    f.unlink()

    ok, mismatches = verify_manifest(tmp_path)
    assert not ok
    assert any("missing file" in m for m in mismatches)


def test_verify_manifest_missing_manifest_file(tmp_path):
    ok, mismatches = verify_manifest(tmp_path)
    assert not ok
    assert "no MANIFEST.json" in mismatches[0]
