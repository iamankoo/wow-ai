from training.pipeline.annotation.ordering import (
    assign_tier,
    build_priority_context,
    priority_score,
)


def _rec(id_, **overrides):
    base = {
        "id": id_, "language": "en", "candidate_source": "none",
        "candidate_confidence": None, "rb_intent": None, "v1_intent": None,
        "v1_intent_conf": None, "candidate_intent": None, "candidate_context": None,
        "rb_context": None,
    }
    base.update(overrides)
    return base


def test_rule_based_candidate_is_tier_1():
    records = [_rec("a", candidate_source="rule_based", candidate_intent="SET_CONTEXT")]
    ctx = build_priority_context(records, hard_negative_ids=set())
    assert assign_tier(records[0], ctx) == 1


def test_high_confidence_v1_is_tier_1():
    records = [_rec("a", candidate_source="v1", candidate_confidence=0.9, candidate_intent="SET_CONTEXT")]
    ctx = build_priority_context(records, hard_negative_ids=set())
    assert assign_tier(records[0], ctx) == 1


def test_disagreement_between_rb_and_v1_is_tier_2():
    records = [_rec("a", rb_intent="SET_CONTEXT", v1_intent="CLEAR_CONTEXT", candidate_source="v1", candidate_confidence=0.9)]
    ctx = build_priority_context(records, hard_negative_ids=set())
    assert assign_tier(records[0], ctx) == 2


def test_uncertain_v1_confidence_is_tier_2():
    records = [_rec("a", v1_intent="SET_CONTEXT", v1_intent_conf=0.45, candidate_source="v1", candidate_confidence=0.45)]
    ctx = build_priority_context(records, hard_negative_ids=set())
    assert assign_tier(records[0], ctx) == 2


def test_hard_negative_id_is_tier_3_when_not_high_confidence_or_ambiguous():
    records = [_rec("a")]
    ctx = build_priority_context(records, hard_negative_ids={"a"})
    assert assign_tier(records[0], ctx) == 3


def test_hinglish_with_no_other_signal_is_tier_6():
    records = [_rec("a", language="hinglish")]
    ctx = build_priority_context(records, hard_negative_ids=set())
    assert assign_tier(records[0], ctx) == 6


def test_no_signal_at_all_is_tier_7():
    records = [_rec("a", language="en")]
    ctx = build_priority_context(records, hard_negative_ids=set())
    assert assign_tier(records[0], ctx) == 7


def test_underrepresented_intent_scores_tier_4():
    # 10 examples of COMMON_INTENT, 1 of RARE_INTENT -> RARE_INTENT is bottom quartile.
    records = [_rec(f"c{i}", candidate_intent="COMMON_INTENT") for i in range(10)]
    records.append(_rec("r1", candidate_intent="RARE_INTENT"))
    ctx = build_priority_context(records, hard_negative_ids=set())
    assert assign_tier(records[-1], ctx) == 4


def test_priority_score_orders_lower_tier_first():
    assert priority_score(1, source_order=999) < priority_score(2, source_order=1)


def test_priority_score_breaks_ties_within_tier_by_source_order():
    assert priority_score(3, source_order=1) < priority_score(3, source_order=2)
