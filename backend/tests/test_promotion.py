from app.learning.promotion import PromotionManager, PromotionPolicy


def _report(**kw) -> dict:
    defaults = dict(
        intent_accuracy=0.5, context_accuracy=0.5, action_accuracy=0.5,
        structured_output_validity=1.0, ambiguous_unknown_accuracy=0.5,
        mode_collapse_suspected=False, most_predicted_intent_share=0.2,
    )
    defaults.update(kw)
    return defaults


def test_clean_improvement_is_promoted():
    baseline = _report(intent_accuracy=0.33, action_accuracy=0.44)
    candidate = _report(intent_accuracy=0.70, action_accuracy=0.60)
    decision = PromotionManager().decide(candidate, baseline)
    assert decision.should_promote is True


def test_worked_example_intent_improves_but_action_regresses_is_rejected():
    """The exact example from the promotion-gate spec: v2 intent 82%->88%
    (improved) but action 86%->73% (regressed 13pp) - must reject despite
    the intent gain, because a significant regression on ANY tracked
    metric blocks promotion."""
    baseline = _report(intent_accuracy=0.82, action_accuracy=0.86)
    candidate = _report(intent_accuracy=0.88, action_accuracy=0.73)
    decision = PromotionManager().decide(candidate, baseline)
    assert decision.should_promote is False
    assert any("action_accuracy" in r for r in decision.failed_checks)


def test_invalid_structured_output_blocks_promotion():
    baseline = _report()
    candidate = _report(structured_output_validity=0.95)
    decision = PromotionManager().decide(candidate, baseline)
    assert decision.should_promote is False
    assert any("structured_output_validity" in r for r in decision.failed_checks)


def test_mode_collapse_blocks_promotion_even_with_higher_accuracy():
    baseline = _report(intent_accuracy=0.33)
    candidate = _report(intent_accuracy=0.90, mode_collapse_suspected=True, most_predicted_intent_share=0.9)
    decision = PromotionManager().decide(candidate, baseline)
    assert decision.should_promote is False
    assert any("mode collapse" in r for r in decision.failed_checks)


def test_small_regression_within_tolerance_is_allowed():
    policy = PromotionPolicy(max_action_regression=0.05)
    baseline = _report(action_accuracy=0.80)
    candidate = _report(action_accuracy=0.77, intent_accuracy=0.9)  # -3pp, within 5pp tolerance
    decision = PromotionManager(policy).decide(candidate, baseline)
    assert decision.should_promote is True


def test_intent_regression_beyond_zero_tolerance_blocks_by_default():
    baseline = _report(intent_accuracy=0.80)
    candidate = _report(intent_accuracy=0.79)  # tiny regression, default tolerance is 0.0
    decision = PromotionManager().decide(candidate, baseline)
    assert decision.should_promote is False


def test_metric_absent_from_either_report_is_skipped_not_failed():
    baseline = _report(context_accuracy=None)
    candidate = _report(context_accuracy=None, intent_accuracy=0.9)
    decision = PromotionManager().decide(candidate, baseline)
    assert decision.should_promote is True


def test_min_intent_accuracy_gain_can_require_strict_improvement():
    policy = PromotionPolicy(min_intent_accuracy_gain=0.05)
    baseline = _report(intent_accuracy=0.80)
    candidate = _report(intent_accuracy=0.81)  # improved, but not by 5pp
    decision = PromotionManager(policy).decide(candidate, baseline)
    assert decision.should_promote is False
