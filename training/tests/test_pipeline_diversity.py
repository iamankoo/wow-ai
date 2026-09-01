from training.pipeline.diversity import diversity_by_intent
from training.pipeline.schema import RawExample


def _ex(text, intent):
    return RawExample(text=text, language="en", intent=intent)


def test_templated_examples_score_high_templating_risk():
    examples = [
        _ex("Call Rahul for me.", "CALL_PERSON"),
        _ex("Call Priya for me.", "CALL_PERSON"),
        _ex("Call Aman for me.", "CALL_PERSON"),
        _ex("Call Neha for me.", "CALL_PERSON"),
    ]
    report = diversity_by_intent(examples)
    assert len(report) == 1
    assert report[0].label == "CALL_PERSON"
    assert report[0].templating_risk in ("medium", "high")


def test_genuinely_diverse_examples_score_low_risk():
    examples = [
        _ex("Can you dial my mother right now?", "CALL_PERSON"),
        _ex("Zara Rahul ko call kar do.", "CALL_PERSON"),
        _ex("I really need to reach my sister, would you mind connecting me?", "CALL_PERSON"),
        _ex("Ring the office landline please.", "CALL_PERSON"),
    ]
    report = diversity_by_intent(examples)
    assert report[0].templating_risk == "low"


def test_single_example_label_has_zero_pairwise_similarity():
    report = diversity_by_intent([_ex("Only one example here.", "UNKNOWN")])
    assert report[0].count == 1
    assert report[0].avg_pairwise_similarity == 0.0
