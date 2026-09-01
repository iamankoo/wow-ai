"""Tests for training/preprocessing/stats.py's distribution computations."""

from training.preprocessing import stats as stats_module


def test_distribution_counts_and_sorts_by_frequency_desc():
    records = [
        {"intent": "A"}, {"intent": "A"}, {"intent": "A"},
        {"intent": "B"}, {"intent": "B"},
        {"intent": "C"},
    ]
    dist = stats_module._distribution(records, "intent")
    assert dist == {"A": 3, "B": 2, "C": 1}
    assert list(dist.keys()) == ["A", "B", "C"]


def test_distribution_ignores_none_values():
    records = [{"context_mode": "BUSY"}, {"context_mode": None}, {"context_mode": "BUSY"}]
    dist = stats_module._distribution(records, "context_mode")
    assert dist == {"BUSY": 2}


def test_compute_stats_on_the_real_dataset_is_internally_consistent():
    stats = stats_module.compute_stats()

    assert stats["total_records"] == sum(stats["intent_distribution"].values())
    # Not every record has an action label, so action counts can be <= total,
    # but never more.
    assert sum(stats["action_distribution"].values()) <= stats["total_records"]
    assert stats["num_intent_classes"] == len(stats["intent_distribution"])
    assert set(stats["intent_distribution"]) <= _ALL_INTENTS
    assert stats["min_examples_per_intent"] == min(stats["intent_distribution"].values())
    assert stats["train_records"] + stats["val_records"] <= stats["total_records"]


from training.wow_taxonomy import Intent  # noqa: E402

_ALL_INTENTS = {i.value for i in Intent}
