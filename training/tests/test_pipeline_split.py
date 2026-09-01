from collections import Counter

from training.pipeline.schema import RawExample
from training.pipeline.split import stratified_three_way_split


def _examples(intent: str, n: int) -> list[RawExample]:
    return [RawExample(text=f"{intent} example {i}", language="en", intent=intent) for i in range(n)]


def test_every_large_class_appears_in_all_three_splits():
    examples = _examples("A", 30) + _examples("B", 40) + _examples("C", 50)
    result = stratified_three_way_split(examples, seed=1)
    train_intents = Counter(e.intent for e in result.train)
    val_intents = Counter(e.intent for e in result.val)
    test_intents = Counter(e.intent for e in result.test)
    for intent in ("A", "B", "C"):
        assert train_intents[intent] > 0
        assert val_intents[intent] >= 2
        assert test_intents[intent] >= 2


def test_tiny_classes_go_entirely_to_train():
    examples = _examples("RARE", 3) + _examples("COMMON", 40)
    result = stratified_three_way_split(examples, seed=3)
    assert all(e.intent == "RARE" for e in result.train if e.intent == "RARE")
    assert sum(1 for e in result.train if e.intent == "RARE") == 3
    assert sum(1 for e in result.val if e.intent == "RARE") == 0
    assert sum(1 for e in result.test if e.intent == "RARE") == 0


def test_split_covers_every_example_exactly_once():
    examples = _examples("A", 25) + _examples("B", 35)
    result = stratified_three_way_split(examples, seed=5)
    all_texts = sorted(e.text for e in result.train + result.val + result.test)
    assert all_texts == sorted(e.text for e in examples)


def test_split_is_reproducible_with_same_seed():
    examples = _examples("A", 30) + _examples("B", 30)
    r1 = stratified_three_way_split(examples, seed=42)
    r2 = stratified_three_way_split(examples, seed=42)
    assert [e.text for e in r1.train] == [e.text for e in r2.train]
    assert [e.text for e in r1.test] == [e.text for e in r2.test]


def test_test_set_and_val_set_never_overlap():
    examples = _examples("A", 40) + _examples("B", 60)
    result = stratified_three_way_split(examples, seed=7)
    val_ids = {id(e) for e in result.val}
    test_ids = {id(e) for e in result.test}
    assert not (val_ids & test_ids)
