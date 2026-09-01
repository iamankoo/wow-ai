import json

import pytest

from training.pipeline import versioning as versioning_module
from training.pipeline.annotation.prepare_training_set import (
    build_duplicate_clusters,
    build_report,
    compute_leakage_check,
    load_approved_records,
    prepare_and_write,
    run_quality_gates,
    stratified_group_split,
)
from training.pipeline.annotation.store import apply_action, connect, init_store


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _make_records(n_per_intent=20):
    """Builds a realistic-shaped 33K-style fixture: three intents at
    different scales, three languages, and one deliberate exact-duplicate
    pair so leakage prevention has something real to catch."""
    relevant, rb, v1 = [], [], []
    idx = 0
    intents = [("SET_CONTEXT", "SET_CONTEXT", "BUSY", n_per_intent), ("CALL_PERSON", "ANSWER_CALL", None, n_per_intent),
               ("CANCEL_REQUEST", "NO_ACTION", None, 3)]
    for intent, action, context, n in intents:
        for i in range(n):
            lang = ["en", "hi", "hinglish"][i % 3]
            rid = f"r{idx}"
            text = f"{intent} example number {i} in {lang}"
            relevant.append({"id": rid, "text": text, "language": lang, "source_file": f"{lang}_dataset_1.txt", "source_line": idx, "source_order": idx})
            rb.append({"id": rid, "candidate_intent": intent, "candidate_context": context, "candidate_action": action,
                       "label_source": "candidate_rule_based", "label_confidence": "rule_matched"})
            idx += 1
    # A deliberate exact duplicate of the first SET_CONTEXT/en example, so
    # duplicate-cluster grouping has a real pair to merge.
    dup_id = f"r{idx}"
    relevant.append({"id": dup_id, "text": relevant[0]["text"], "language": relevant[0]["language"],
                      "source_file": "en_dataset_1.txt", "source_line": idx, "source_order": idx})
    rb.append({"id": dup_id, "candidate_intent": "SET_CONTEXT", "candidate_context": "BUSY", "candidate_action": "SET_CONTEXT",
               "label_source": "candidate_rule_based", "label_confidence": "rule_matched"})
    return relevant, rb, v1


@pytest.fixture
def store(tmp_path):
    relevant, rb, v1 = _make_records()
    relevant_path, rb_path, v1_path = tmp_path / "relevant.jsonl", tmp_path / "rb.jsonl", tmp_path / "v1.jsonl"
    _write_jsonl(relevant_path, relevant)
    _write_jsonl(rb_path, rb)
    _write_jsonl(v1_path, v1)

    db_path = tmp_path / "test.db"
    init_store(db_path=db_path, relevant_path=relevant_path, rb_path=rb_path, v1_path=v1_path)
    conn = connect(db_path)
    with conn:
        conn.execute(
            "UPDATE annotations SET review_status='approved', label_source='candidate', approved_by='test_bulk', confidence=5"
        )
    yield conn
    conn.close()


def test_load_approved_records_resolves_candidate_labels(store):
    records = load_approved_records(store)
    assert len(records) == 44  # 20+20+3+dup
    assert all(r["intent"] for r in records)
    assert all(r["approved_by"] == "test_bulk" for r in records)


def test_load_approved_records_excludes_pending(store):
    with store:
        store.execute("UPDATE annotations SET review_status='pending' WHERE id='r0'")
    records = load_approved_records(store)
    assert not any(r["id"] == "r0" for r in records)


def test_run_quality_gates_finds_the_deliberate_duplicate(store):
    records = load_approved_records(store)
    quality, exact_pairs, near_pairs, _ = run_quality_gates(records)
    assert quality["exact_duplicate_pairs"] >= 1
    assert quality["status_counts"].get("pass", 0) > 0


def test_build_duplicate_clusters_groups_the_exact_duplicate_together(store):
    records = load_approved_records(store)
    _, exact_pairs, near_pairs, _ = run_quality_gates(records)
    clusters = build_duplicate_clusters(len(records), exact_pairs, near_pairs)
    multi = [c for c in clusters if len(c) > 1]
    assert len(multi) == 1
    assert len(multi[0]) == 2


def test_stratified_group_split_never_splits_a_cluster_across_sets(store):
    records = load_approved_records(store)
    _, exact_pairs, near_pairs, _ = run_quality_gates(records)
    clusters = build_duplicate_clusters(len(records), exact_pairs, near_pairs)
    split = stratified_group_split(records, clusters)

    idx_to_split = {}
    for name, idx_list in (("train", split["train_idx"]), ("val", split["val_idx"]), ("test", split["test_idx"])):
        for i in idx_list:
            idx_to_split[i] = name

    for cluster in clusters:
        splits_used = {idx_to_split[i] for i in cluster}
        assert len(splits_used) == 1, f"cluster {cluster} spans multiple splits: {splits_used}"


def test_stratified_group_split_covers_every_record_exactly_once(store):
    records = load_approved_records(store)
    _, exact_pairs, near_pairs, _ = run_quality_gates(records)
    clusters = build_duplicate_clusters(len(records), exact_pairs, near_pairs)
    split = stratified_group_split(records, clusters)
    all_idx = split["train_idx"] + split["val_idx"] + split["test_idx"]
    assert sorted(all_idx) == list(range(len(records)))


def test_stratified_group_split_gives_val_and_test_representation_to_large_classes(store):
    records = load_approved_records(store)
    _, exact_pairs, near_pairs, _ = run_quality_gates(records)
    clusters = build_duplicate_clusters(len(records), exact_pairs, near_pairs)
    split = stratified_group_split(records, clusters)

    val_intents = {records[i]["intent"] for i in split["val_idx"]}
    test_intents = {records[i]["intent"] for i in split["test_idx"]}
    assert "SET_CONTEXT" in val_intents
    assert "SET_CONTEXT" in test_intents
    assert "CALL_PERSON" in val_intents
    assert "CALL_PERSON" in test_intents


def test_compute_leakage_check_is_clean_for_a_valid_split(store):
    records = load_approved_records(store)
    _, exact_pairs, near_pairs, _ = run_quality_gates(records)
    clusters = build_duplicate_clusters(len(records), exact_pairs, near_pairs)
    split = stratified_group_split(records, clusters)
    leakage = compute_leakage_check(records, split)
    assert leakage["exact_text_leakage_groups"] == 0


def test_compute_leakage_check_detects_a_deliberately_broken_split(store):
    records = load_approved_records(store)
    # r0 and its duplicate rXX share identical text - force them into different splits.
    dup_index = next(i for i, r in enumerate(records) if r["text"] == records[0]["text"] and i != 0)
    bad_split = {"train_idx": [0], "val_idx": [dup_index], "test_idx": []}
    leakage = compute_leakage_check(records, bad_split)
    assert leakage["exact_text_leakage_groups"] == 1


def test_build_report_counts_are_internally_consistent(store):
    records = load_approved_records(store)
    quality, exact_pairs, near_pairs, _ = run_quality_gates(records)
    clusters = build_duplicate_clusters(len(records), exact_pairs, near_pairs)
    split = stratified_group_split(records, clusters)
    report = build_report(records, split, clusters, quality)

    total_from_splits = (
        report["splits"]["train"]["count"] + report["splits"]["val"]["count"] + report["splits"]["test"]["count"]
    )
    assert total_from_splits == report["total_approved_records"]
    assert report["splits"]["train"]["machine_approved_count"] + report["splits"]["train"]["human_reviewed_count"] == report["splits"]["train"]["count"]


def test_prepare_and_write_creates_versioned_files_with_manifest(store, tmp_path, monkeypatch):
    versions_dir = tmp_path / "versions"
    monkeypatch.setattr(versioning_module, "VERSIONS_DIR", versions_dir)

    result = prepare_and_write(store, "v_test.2.0-train-ready")
    version_dir = versions_dir / "v_test.2.0-train-ready"
    assert (version_dir / "train.jsonl").exists()
    assert (version_dir / "val.jsonl").exists()
    assert (version_dir / "test.jsonl").exists()
    assert (version_dir / "STATS.json").exists()

    manifest = json.loads((version_dir / "MANIFEST.json").read_text(encoding="utf-8"))
    assert len(manifest["files"]) == 4
    assert all(f["sha256"] for f in manifest["files"])

    train_lines = (version_dir / "train.jsonl").read_text(encoding="utf-8").splitlines()
    val_lines = (version_dir / "val.jsonl").read_text(encoding="utf-8").splitlines()
    test_lines = (version_dir / "test.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(train_lines) + len(val_lines) + len(test_lines) == 44

    first_train_record = json.loads(train_lines[0])
    assert "source_file" in first_train_record and "source_line" in first_train_record
    assert "id" in first_train_record
    assert "quality_status" in first_train_record
    assert "duplicate_cluster_id" in first_train_record


def test_per_record_quality_flags_are_attached_for_the_duplicate_pair(store, tmp_path, monkeypatch):
    versions_dir = tmp_path / "versions"
    monkeypatch.setattr(versioning_module, "VERSIONS_DIR", versions_dir)
    prepare_and_write(store, "v_test.2.1-train-ready")
    version_dir = versions_dir / "v_test.2.1-train-ready"

    all_records = []
    for name in ("train.jsonl", "val.jsonl", "test.jsonl"):
        all_records.extend(json.loads(l) for l in (version_dir / name).read_text(encoding="utf-8").splitlines())

    dup_records = [r for r in all_records if r["duplicate_cluster_size"] > 1]
    assert len(dup_records) == 2
    assert dup_records[0]["duplicate_cluster_id"] == dup_records[1]["duplicate_cluster_id"]
    assert any(r["is_exact_duplicate"] for r in dup_records)
