from training.pipeline.dedup import deduplicate, find_exact_duplicates, find_near_duplicates
from training.pipeline.schema import RawExample


def _ex(text, language="en", intent="UNKNOWN"):
    return RawExample(text=text, language=language, intent=intent)


def test_finds_exact_duplicate_ignoring_case_and_punctuation():
    examples = [_ex("Call Rahul."), _ex("call rahul"), _ex("Something else entirely.")]
    dupes = find_exact_duplicates(examples)
    assert dupes == [(0, 1)]


def test_no_exact_duplicates_when_all_unique():
    examples = [_ex("a"), _ex("b"), _ex("c")]
    assert find_exact_duplicates(examples) == []


def test_finds_near_duplicate_with_small_wording_change():
    examples = [
        _ex("I'm busy right now, take messages instead."),
        _ex("I'm busy right now, please take messages instead."),
        _ex("Completely unrelated sentence about something else."),
    ]
    near = find_near_duplicates(examples, threshold=0.7)
    pairs = [(i, j) for i, j, _ in near]
    assert (0, 1) in pairs


def test_dissimilar_texts_are_not_near_duplicates():
    examples = [
        _ex("I'm busy right now, take messages instead."),
        _ex("Can you summarize what happened while I was out?"),
    ]
    assert find_near_duplicates(examples, threshold=0.7) == []


def test_deduplicate_report_counts_unique_correctly():
    examples = [_ex("Call Rahul."), _ex("call rahul"), _ex("Something else.")]
    report = deduplicate(examples)
    assert report.total == 3
    assert report.unique_count == 2
