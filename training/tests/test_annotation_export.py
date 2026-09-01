import json

import pytest

from training.pipeline.annotation.export import export_version
from training.pipeline.annotation.store import apply_action, connect, init_store
from training.pipeline import versioning as versioning_module


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


@pytest.fixture
def store(tmp_path, monkeypatch):
    relevant = tmp_path / "relevant.jsonl"
    rb = tmp_path / "rb.jsonl"
    v1 = tmp_path / "v1.jsonl"
    _write_jsonl(relevant, [
        {"id": "r1", "text": "Set me to busy.", "language": "en", "source_file": "english_dataset_1.txt", "source_line": 1, "source_order": 1},
        {"id": "r2", "text": "unrelated text", "language": "en", "source_file": "english_dataset_1.txt", "source_line": 2, "source_order": 2},
    ])
    _write_jsonl(rb, [
        {"id": "r1", "candidate_intent": "SET_CONTEXT", "candidate_context": "BUSY", "candidate_action": "SET_CONTEXT",
         "label_source": "candidate_rule_based", "label_confidence": "rule_matched"},
        {"id": "r2", "candidate_intent": "UNKNOWN", "candidate_context": None, "candidate_action": "NO_ACTION",
         "label_source": "review", "label_confidence": None},
    ])
    _write_jsonl(v1, [])

    versions_dir = tmp_path / "versions"
    monkeypatch.setattr(versioning_module, "VERSIONS_DIR", versions_dir)

    db_path = tmp_path / "test.db"
    init_store(db_path=db_path, relevant_path=relevant, rb_path=rb, v1_path=v1)
    conn = connect(db_path)
    apply_action(conn, "r1", "approve", annotator="alice")
    yield conn, versions_dir
    conn.close()


def test_export_writes_snapshot_and_train_ready_subset(store):
    conn, versions_dir = store
    result = export_version(conn, "v_test.0.0-annotated")
    assert result["written_all"] == 2
    assert result["written_ready"] == 1

    train_ready_path = versions_dir / "v_test.0.0-annotated" / "wow_annotation_train_ready.jsonl"
    lines = [json.loads(l) for l in train_ready_path.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 1
    assert lines[0]["id"] == "r1"
    assert lines[0]["intent"] == "SET_CONTEXT"


def test_export_writes_manifest_with_checksums(store):
    conn, versions_dir = store
    result = export_version(conn, "v_test.0.0-annotated")
    manifest = json.loads((versions_dir / "v_test.0.0-annotated" / "MANIFEST.json").read_text(encoding="utf-8"))
    assert len(manifest["files"]) == 3
    assert all(f["sha256"] for f in manifest["files"])
