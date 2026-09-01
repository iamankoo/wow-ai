"""Smart (non-random) review-order prioritization for the annotation queue.

Every record is assigned to exactly one tier (lower tier number = reviewed
first). Tiers are numbered by review priority, but disagreement/ambiguity
is evaluated before the high-confidence check in code, since a numerically
confident v1 prediction that contradicts the rule-based candidate is still
ambiguous, not a quick win:

  1. high_confidence_candidate  - a candidate already exists and looks
                                   reliable (rule-based match, or v1
                                   confidence >= HIGH_CONF_THRESHOLD).
                                   Fast to verify - quick wins first.
  2. ambiguous                  - rule-based and v1 disagree, or v1's
                                   confidence sits in the uncertain band.
  3. hard_negative_opportunity  - text matches a known trigger-word +
                                   negation pattern (see taxonomy_analysis).
  4. underrepresented_intent    - candidate intent is among the least
                                   common in the corpus so far.
  5. underrepresented_context   - candidate context is among the least
                                   common in the corpus so far.
  6. language_edge_case         - Hinglish text, which is the hardest
                                   language boundary to get right.
  7. remaining                  - everything else, reviewed last.

This ordering exists purely to make limited human annotation time count for
more. It never assigns a label - only a queue position.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

HIGH_CONF_THRESHOLD = 0.75
AMBIGUOUS_LOW = 0.30
AMBIGUOUS_HIGH = 0.60
UNDERREPRESENTED_PERCENTILE = 0.25  # bottom quartile by frequency

TIER_NAMES = {
    1: "high_confidence_candidate",
    2: "ambiguous",
    3: "hard_negative_opportunity",
    4: "underrepresented_intent",
    5: "underrepresented_context",
    6: "language_edge_case",
    7: "remaining",
}


@dataclass
class PriorityContext:
    intent_freq: Counter
    context_freq: Counter
    underrepresented_intents: set
    underrepresented_contexts: set
    hard_negative_ids: set


def build_priority_context(records: list[dict], hard_negative_ids: set) -> PriorityContext:
    intent_freq: Counter = Counter()
    context_freq: Counter = Counter()
    for r in records:
        intent = r.get("candidate_intent") or r.get("rb_intent")
        if intent:
            intent_freq[intent] += 1
        context = r.get("candidate_context") or r.get("rb_context")
        if context:
            context_freq[context] += 1

    def _bottom_quartile(freq: Counter) -> set:
        if not freq:
            return set()
        sorted_items = sorted(freq.items(), key=lambda kv: kv[1])
        cutoff = max(1, int(len(sorted_items) * UNDERREPRESENTED_PERCENTILE))
        return {k for k, _ in sorted_items[:cutoff]}

    return PriorityContext(
        intent_freq=intent_freq,
        context_freq=context_freq,
        underrepresented_intents=_bottom_quartile(intent_freq),
        underrepresented_contexts=_bottom_quartile(context_freq),
        hard_negative_ids=hard_negative_ids,
    )


def assign_tier(record: dict, ctx: PriorityContext) -> int:
    rb_intent = record.get("rb_intent")
    v1_intent = record.get("v1_intent")
    v1_conf = record.get("v1_intent_conf")
    candidate_source = record.get("candidate_source", "none")
    candidate_conf = record.get("candidate_confidence")

    # Disagreement is checked before "high confidence" on purpose: a v1
    # prediction can be numerically confident yet still contradict the
    # deterministic rule-based candidate, and that contradiction is a
    # stronger ambiguity signal than v1's own confidence score - the 33K
    # cross-check found v1 and rule-based agree only ~13-19% of the time
    # even when rule-based commits, so a disagreeing "confident" v1 label is
    # not actually a quick win.
    disagree = bool(rb_intent) and bool(v1_intent) and rb_intent != v1_intent
    uncertain_v1 = v1_conf is not None and AMBIGUOUS_LOW <= v1_conf <= AMBIGUOUS_HIGH
    if disagree or uncertain_v1:
        return 2

    is_high_conf = (
        candidate_source == "rule_based"
        or (candidate_source == "v1" and candidate_conf is not None and candidate_conf >= HIGH_CONF_THRESHOLD)
    )
    if is_high_conf:
        return 1

    if record["id"] in ctx.hard_negative_ids:
        return 3

    intent = record.get("candidate_intent") or rb_intent
    if intent and intent in ctx.underrepresented_intents:
        return 4

    context = record.get("candidate_context") or record.get("rb_context")
    if context and context in ctx.underrepresented_contexts:
        return 5

    if record.get("language") == "hinglish":
        return 6

    return 7


def priority_score(tier: int, source_order: int) -> float:
    """Ascending sort key: tier dominates, source_order breaks ties so the
    ordering is deterministic and reproducible across runs."""
    return tier + (source_order / 10_000_000.0)
