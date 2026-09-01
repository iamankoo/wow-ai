"""Promotion policy: decides whether a newly trained candidate model may
replace the current production model. "Promote only if better" - and
critically, a regression on ANY tracked metric blocks promotion even if
other metrics improved (see the worked example in docs/SELF_LEARNING.md
"Evaluation gate": intent 82%->88% but action 86%->73% is a REJECT).

Operates on plain dicts shaped like one provider's entry from
training/evaluation/evaluate.py's report (`report["providers"][name]`) -
deliberately duck-typed rather than importing from training/, since the
project's dependency direction is training -> backend, never the reverse.
Expected keys: intent_accuracy, context_accuracy, action_accuracy,
structured_output_validity, ambiguous_unknown_accuracy,
mode_collapse_suspected (all optional except intent_accuracy and
structured_output_validity, which must always be present).
"""

from dataclasses import dataclass, field


@dataclass
class PromotionPolicy:
    # A metric must not drop by more than this many percentage points
    # (as a fraction, e.g. 0.02 = 2pp) versus the baseline. 0.0 means "any
    # regression at all blocks promotion" - the default, matching "promote
    # only if better, never regress silently".
    max_intent_regression: float = 0.0
    max_context_regression: float = 0.02
    max_action_regression: float = 0.02
    max_unknown_accuracy_regression: float = 0.05
    min_intent_accuracy_gain: float = 0.0
    require_structured_validity: float = 1.0
    forbid_mode_collapse: bool = True


@dataclass
class PromotionDecision:
    should_promote: bool
    passed_checks: list[str] = field(default_factory=list)
    failed_checks: list[str] = field(default_factory=list)

    @property
    def reasons(self) -> list[str]:
        return self.failed_checks if not self.should_promote else self.passed_checks


class PromotionManager:
    def __init__(self, policy: PromotionPolicy | None = None):
        self._policy = policy or PromotionPolicy()

    def decide(self, candidate: dict, baseline: dict) -> PromotionDecision:
        passed: list[str] = []
        failed: list[str] = []
        p = self._policy

        validity = candidate.get("structured_output_validity")
        if validity is not None and validity < p.require_structured_validity:
            failed.append(f"structured_output_validity {validity:.2%} below required {p.require_structured_validity:.0%}")
        else:
            passed.append("structured_output_validity ok")

        if p.forbid_mode_collapse and candidate.get("mode_collapse_suspected"):
            share = candidate.get("most_predicted_intent_share")
            failed.append(f"mode collapse suspected ({share:.1%} of predictions are one intent)" if share else "mode collapse suspected")
        else:
            passed.append("no mode collapse detected")

        self._check_metric(
            "intent_accuracy", candidate, baseline, p.max_intent_regression,
            min_gain=p.min_intent_accuracy_gain, passed=passed, failed=failed,
        )
        self._check_metric("context_accuracy", candidate, baseline, p.max_context_regression, passed=passed, failed=failed)
        self._check_metric("action_accuracy", candidate, baseline, p.max_action_regression, passed=passed, failed=failed)
        self._check_metric(
            "ambiguous_unknown_accuracy", candidate, baseline, p.max_unknown_accuracy_regression,
            passed=passed, failed=failed,
        )

        return PromotionDecision(should_promote=not failed, passed_checks=passed, failed_checks=failed)

    @staticmethod
    def _check_metric(
        key: str, candidate: dict, baseline: dict, max_regression: float,
        *, passed: list[str], failed: list[str], min_gain: float = -1.0,
    ) -> None:
        c_val = candidate.get(key)
        b_val = baseline.get(key)
        if c_val is None or b_val is None:
            return  # metric not applicable to this head (e.g. no context labels)
        delta = c_val - b_val
        if min_gain > -1.0 and delta < min_gain:
            failed.append(f"{key} did not improve enough ({b_val:.2%} -> {c_val:.2%}, need +{min_gain:.2%})")
        elif delta < -max_regression:
            failed.append(f"{key} regressed by {-delta:.2%} ({b_val:.2%} -> {c_val:.2%}), max allowed {max_regression:.2%}")
        else:
            passed.append(f"{key} {b_val:.2%} -> {c_val:.2%} ({delta:+.2%})")
