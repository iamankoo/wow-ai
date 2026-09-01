"""Tests for the stratified train/val split in
training/preprocessing/build_training_set.py.
"""

from collections import Counter

from training.preprocessing.build_training_set import stratified_split


def _records(intent: str, n: int) -> list[dict]:
    return [{"text": f"{intent} example {i}", "intent": intent} for i in range(n)]


def test_every_sufficiently_large_class_appears_in_both_splits():
    records = _records("A", 20) + _records("B", 20) + _records("C", 20)
    train, val = stratified_split(records, val_fraction=0.15, seed=1,
                                   min_val_per_class=2, min_class_size_for_split=5)
    train_counts = Counter(r["intent"] for r in train)
    val_counts = Counter(r["intent"] for r in val)
    for intent in ("A", "B", "C"):
        assert train_counts[intent] > 0
        assert val_counts[intent] >= 2


def test_no_class_gets_exactly_one_validation_example():
    records = _records("A", 13) + _records("B", 27) + _records("C", 41)
    train, val = stratified_split(records, val_fraction=0.15, seed=7,
                                   min_val_per_class=2, min_class_size_for_split=5)
    val_counts = Counter(r["intent"] for r in val)
    for count in val_counts.values():
        assert count != 1


def test_tiny_classes_go_entirely_to_train():
    records = _records("RARE", 3) + _records("COMMON", 40)
    train, val = stratified_split(records, val_fraction=0.15, seed=3,
                                   min_val_per_class=2, min_class_size_for_split=5)
    train_counts = Counter(r["intent"] for r in train)
    val_counts = Counter(r["intent"] for r in val)
    assert train_counts["RARE"] == 3
    assert val_counts["RARE"] == 0
    assert val_counts["COMMON"] >= 2


def test_split_is_reproducible_given_the_same_seed():
    records = _records("A", 30) + _records("B", 30)
    train1, val1 = stratified_split(records, seed=42)
    train2, val2 = stratified_split(records, seed=42)
    assert [r["text"] for r in train1] == [r["text"] for r in train2]
    assert [r["text"] for r in val1] == [r["text"] for r in val2]


def test_split_covers_every_input_record_exactly_once():
    records = _records("A", 17) + _records("B", 9) + _records("C", 33)
    train, val = stratified_split(records, seed=5)
    all_texts = sorted(r["text"] for r in train + val)
    assert all_texts == sorted(r["text"] for r in records)
