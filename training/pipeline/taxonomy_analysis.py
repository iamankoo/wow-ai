"""Taxonomy analysis for the 33K on-topic dataset_1+dataset_2 examples -
candidate labeling, taxonomy-gap detection, confusion-pair analysis,
language analysis, and hard-negative opportunity scanning.

This module never trains anything. Candidate labels are produced by
reusing EXISTING inference-only infrastructure:
- RuleBasedLanguageModelProvider.classify_wow_taxonomy (deterministic,
  instant, already the evaluation baseline in training/evaluation/evaluate.py)
  for full 33K coverage.
- The already-trained v1 model (LocalWOWModelProvider, inference only - no
  weights are modified) for a bounded stratified cross-check sample, since
  running the 135M-parameter model on all 33K on CPU would take hours.

Every candidate carries label_source="candidate_rule_based" (or
"candidate_v1_crosscheck" for the sample) and is never presented as ground
truth - see docs/DATASET.md for the full methodology writeup.
"""

import json
import random
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from training.pipeline.normalize import normalize_for_comparison
from training.training.config import REPO_ROOT

DATASETS_DIR = Path(__file__).resolve().parents[1] / "datasets"
REPORTS_DIR = DATASETS_DIR / "reports"
THIRTY_THREE_K_PATH = DATASETS_DIR / "v3_raw" / "wow_33k_relevant.jsonl"
CANDIDATE_LABELS_PATH = DATASETS_DIR / "v3_raw" / "wow_33k_candidate_labels.jsonl"

BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.brain.taxonomy import Intent  # noqa: E402
from app.providers.llm.rule_based import RuleBasedLanguageModelProvider  # noqa: E402


_EDGE_PUNCT = ".,!?;:()\"'“”‘’।،…-–—[]{}"


def _tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text)
    return [w.strip(_EDGE_PUNCT) for w in text.split() if w.strip(_EDGE_PUNCT)]


def _contains_any(text: str, phrases: list[str]) -> str | None:
    """Substring match (not tokenized) - deliberately simple, phrases here
    are multi-word or short enough that this is safe and avoids missing
    Devanagari matches to the same tokenization pitfall documented in
    relevance.py."""
    lowered = text.lower()
    for p in phrases:
        if p.lower() in lowered or p in text:
            return p
    return None


def _load_33k() -> list[dict]:
    records = []
    with THIRTY_THREE_K_PATH.open(encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))
    return records


# ---------------------------------------------------------------------------
# Candidate labeling pass 1: rule-based, full coverage
# ---------------------------------------------------------------------------

@dataclass
class RuleBasedLabelSummary:
    total: int
    candidate_count: int
    review_count: int
    intent_distribution: dict
    action_distribution: dict
    context_distribution: dict
    per_file_candidate_rate: dict
    elapsed_seconds: float


def label_with_rule_based(records: list[dict], output_path: Path) -> RuleBasedLabelSummary:
    provider = RuleBasedLanguageModelProvider()
    intent_counts: Counter = Counter()
    action_counts: Counter = Counter()
    context_counts: Counter = Counter()
    per_file_total: Counter = Counter()
    per_file_candidate: Counter = Counter()
    candidate_count = 0
    start = time.monotonic()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as out:
        for r in records:
            intent, context_mode, action = provider.classify_wow_taxonomy(r["text"])
            is_candidate = intent != Intent.UNKNOWN
            per_file_total[r["source_file"]] += 1
            if is_candidate:
                per_file_candidate[r["source_file"]] += 1
                candidate_count += 1
            intent_counts[intent.value] += 1
            action_counts[action.value] += 1
            if context_mode is not None:
                context_counts[context_mode.value] += 1

            record = {
                **r,
                "candidate_intent": intent.value,
                "candidate_context": context_mode.value if context_mode else None,
                "candidate_action": action.value,
                "label_source": "candidate_rule_based" if is_candidate else "review",
                "label_confidence": "rule_matched" if is_candidate else None,
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    per_file_rate = {
        f: round(per_file_candidate[f] / per_file_total[f], 4) for f in per_file_total
    }

    return RuleBasedLabelSummary(
        total=len(records),
        candidate_count=candidate_count,
        review_count=len(records) - candidate_count,
        intent_distribution=dict(intent_counts.most_common()),
        action_distribution=dict(action_counts.most_common()),
        context_distribution=dict(context_counts.most_common()),
        per_file_candidate_rate=per_file_rate,
        elapsed_seconds=time.monotonic() - start,
    )


# ---------------------------------------------------------------------------
# Candidate labeling pass 2: v1 model cross-check on a stratified sample
# ---------------------------------------------------------------------------

@dataclass
class V1CrossCheckSummary:
    sample_size: int
    intent_agreement_rate: float
    action_agreement_rate: float
    context_agreement_rate: float
    avg_intent_confidence: float
    avg_context_confidence: float
    avg_action_confidence: float
    low_confidence_count: int
    elapsed_seconds: float
    disagreement_examples: list[dict]


def _stratified_sample(records: list[dict], k: int, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    by_file: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_file[r["source_file"]].append(r)
    per_file_k = max(1, k // len(by_file))
    sample = []
    for f, items in by_file.items():
        sample.extend(rng.sample(items, min(per_file_k, len(items))))
    rng.shuffle(sample)
    return sample[:k]


async def run_v1_crosscheck(
    candidate_labeled_records: list[dict], sample_size: int = 2500, confidence_threshold: float = 0.6
) -> V1CrossCheckSummary:
    from app.providers.llm.local_wow import LocalWOWModelProvider
    from app.interfaces.llm import LLMMessage

    model_dir = REPO_ROOT / "training" / "models" / "wow-brain" / "v1"
    provider = LocalWOWModelProvider(model_dir, inference_device="cpu")

    sample = _stratified_sample(candidate_labeled_records, sample_size)
    start = time.monotonic()

    intent_matches = 0
    action_matches = 0
    context_matches = 0
    context_total = 0
    intent_confs, context_confs, action_confs = [], [], []
    low_conf_count = 0
    disagreements = []

    for r in sample:
        response = await provider.generate([LLMMessage(role="user", content=r["text"])])
        conf = response.metadata.get("confidence", {})
        intent_conf = conf.get("intent") or 0.0
        context_conf = conf.get("context_mode") or 0.0
        action_conf = conf.get("action") or 0.0
        intent_confs.append(intent_conf)
        context_confs.append(context_conf)
        action_confs.append(action_conf)
        if intent_conf < confidence_threshold:
            low_conf_count += 1

        v1_intent = response.intent
        v1_action = response.slots.get("action")
        v1_context = response.slots.get("context_mode")

        rb_intent = r["candidate_intent"]
        rb_action = r["candidate_action"]
        rb_context = r["candidate_context"]

        intent_agree = v1_intent == rb_intent
        action_agree = v1_action == rb_action
        if intent_agree:
            intent_matches += 1
        if action_agree:
            action_matches += 1
        if rb_context is not None:
            context_total += 1
            if v1_context == rb_context:
                context_matches += 1

        if not intent_agree and len(disagreements) < 40:
            disagreements.append({
                "text": r["text"], "source_file": r["source_file"],
                "rule_based_intent": rb_intent, "v1_intent": v1_intent,
                "v1_intent_confidence": round(intent_conf, 3),
            })

    n = len(sample)
    return V1CrossCheckSummary(
        sample_size=n,
        intent_agreement_rate=round(intent_matches / n, 4) if n else 0.0,
        action_agreement_rate=round(action_matches / n, 4) if n else 0.0,
        context_agreement_rate=round(context_matches / context_total, 4) if context_total else 0.0,
        avg_intent_confidence=round(sum(intent_confs) / n, 4) if n else 0.0,
        avg_context_confidence=round(sum(context_confs) / n, 4) if n else 0.0,
        avg_action_confidence=round(sum(action_confs) / n, 4) if n else 0.0,
        low_confidence_count=low_conf_count,
        elapsed_seconds=time.monotonic() - start,
        disagreement_examples=disagreements,
    )


# ---------------------------------------------------------------------------
# Taxonomy gap scanning: does this dataset contain real evidence of
# behaviors the current taxonomy can't represent? Phrase-based (English +
# Hindi/Hinglish), reports actual matching quotes - never assumed, always
# checked against real data.
# ---------------------------------------------------------------------------

GAP_CONCEPT_PHRASES: dict[str, list[str]] = {
    "HOLD_CALL": ["hold on", "please hold", "hold kar", "होल्ड कर", "थोड़ी देर रुकिए", "line pe raho", "लाइन पर रहो"],
    "RESUME_CALL": ["resume the call", "continue the call", "फिर से शुरू करो", "wapas call pe", "call resume"],
    "REJECT_CALL": ["reject the call", "decline the call", "call reject", "call mat lena", "उठाना मत", "ignore this call", "ye call mat utha"],
    "REDIAL": ["redial", "call again", "dobara call kar", "फिर से कॉल कर", "wapas call kar"],
    "CALLBACK_REQUEST": ["call back", "callback", "call kar lena baad", "call karunga baad", "वापस कॉल कर", "call karenge baad mein"],
    "SCREEN_CALL": ["screen my call", "screen the call", "calls filter kar", "कॉल्स छान"],
    "BLOCK_CALLER": ["block this number", "block kar do", "ब्लॉक कर दो", "isko block", "number block"],
    "PAUSE_WOW": ["pause wow", "wow ko rok", "रुक जाओ wow", "wow band kar", "assistant ko rok"],
    "TAKE_OVER_CALL": ["take over the call", "main khud sambhal", "let me take this call", "main khud le lunga"],
    "CHANGE_VOICE": ["change your voice", "आवाज़ बदलो", "aapki awaz badlo", "voice change kar"],
    "ASK_AVAILABILITY": ["are you available", "kab free ho", "कब उपलब्ध", "kab available"],
    "EXTEND_CONTEXT": ["extend the meeting", "thodi der aur chahiye", "meeting lambi", "extend busy", "aur samay chahiye", "थोड़ा और समय"],
    "INTERRUPT_WOW": ["let me speak", "मुझे बोलने दो", "i'll handle this myself", "main khud bol"],
}


@dataclass
class GapConceptFinding:
    concept: str
    match_count: int
    match_rate: float
    sample_quotes: list[dict]
    verdict: str  # "supported" | "weak_evidence" | "no_evidence"


def scan_taxonomy_gaps(records: list[dict], max_samples: int = 6) -> list[GapConceptFinding]:
    findings = []
    n = len(records)
    for concept, phrases in GAP_CONCEPT_PHRASES.items():
        matches = []
        for r in records:
            hit = _contains_any(r["text"], phrases)
            if hit:
                matches.append({"text": r["text"], "source_file": r["source_file"], "matched_phrase": hit})
        rate = len(matches) / n if n else 0.0
        if len(matches) >= 15:
            verdict = "supported"
        elif len(matches) >= 3:
            verdict = "weak_evidence"
        else:
            verdict = "no_evidence"
        findings.append(GapConceptFinding(
            concept=concept, match_count=len(matches), match_rate=round(rate, 5),
            sample_quotes=matches[:max_samples], verdict=verdict,
        ))
    return findings


# ---------------------------------------------------------------------------
# Confusion / overlap pair analysis - real examples where two taxonomy
# categories could both plausibly apply, found via keyword co-occurrence.
# ---------------------------------------------------------------------------

@dataclass
class ConfusionPairFinding:
    pair: str
    description: str
    match_count: int
    sample_quotes: list[dict]


_CONFUSION_PATTERNS: list[tuple[str, str, list[str], list[str]]] = [
    ("URGENT_CALL_vs_NON_URGENT_CALL",
     "Contains an urgency word but also a negation/de-escalation word in the same sentence.",
     ["urgent", "emergency", "ज़रूरी", "जरूरी", "turant", "अर्जेंट"],
     ["nahi", "not", "नहीं", "no rush", "koi jaldi nahi"]),
    ("KNOWN_CALLER_vs_UNKNOWN_CALLER",
     "Contains both a familiarity cue and an unfamiliarity cue.",
     ["dost", "friend", "bhai", "papa", "mummy", "जान-पहचान", "known"],
     ["anjaan", "unknown", "अनजान", "pehchana nahi", "not saved"]),
    ("SET_CONTEXT_vs_GENERAL_CONVERSATION",
     "Mentions a context-mode word but the sentence is phrased as a question ABOUT someone else's status, not a self-declaration.",
     ["busy", "sleeping", "so raha", "व्यस्त", "meeting"],
     ["is he", "is she", "kya woh", "क्या वह", "kya aniket"]),
    ("MESSAGE_FOR_USER_vs_COLLECT_MESSAGE",
     "Both concern relaying information - overlap between the intent (why the caller is talking) and the action (what WOW does).",
     ["bata dena", "keh dena", "tell him", "tell her", "बता देना"],
     ["message", "संदेश", "note"]),
    ("END_CALL_vs_END_CONVERSATION",
     "Contains both a farewell cue and an explicit call-termination cue.",
     ["bye", "goodbye", "अलविदा", "dhanyavaad", "thank you"],
     ["hang up", "end the call", "call kaat", "काट दो", "disconnect"]),
    ("HANDLE_CALLS_vs_ENABLE_CALL_ASSISTANT",
     "General call-management phrasing that could be read as either the intent or its resulting action.",
     ["sambhal", "handle my call", "calls dekh", "संभाल"],
     ["assistant", "sahayak", "enable", "on kar", "chalu kar"]),
    ("GET_CONTEXT_vs_GENERAL_CONVERSATION",
     "A status question that could be a genuine GET_CONTEXT query or just small talk.",
     ["kaisa hai", "kaise ho", "kya haal", "क्या हाल"],
     ["mode", "status", "available", "उपलब्ध"]),
    ("TRANSFER_CALL_vs_TRANSFER_TO_USER",
     "Both concern connecting the caller directly - overlap between the action name and the intent that triggers it.",
     ["transfer", "connect me", "seedha", "सीधे"],
     ["directly", "abhi", "right now", "turant"]),
]


def scan_confusion_pairs(records: list[dict], max_samples: int = 6) -> list[ConfusionPairFinding]:
    findings = []
    for pair, description, set_a, set_b in _CONFUSION_PATTERNS:
        matches = []
        for r in records:
            hit_a = _contains_any(r["text"], set_a)
            hit_b = _contains_any(r["text"], set_b)
            if hit_a and hit_b:
                matches.append({
                    "text": r["text"], "source_file": r["source_file"],
                    "signal_a": hit_a, "signal_b": hit_b,
                })
        findings.append(ConfusionPairFinding(
            pair=pair, description=description, match_count=len(matches),
            sample_quotes=matches[:max_samples],
        ))
    return findings


# ---------------------------------------------------------------------------
# Hard-negative opportunity scanning - negation near a taxonomy-trigger word,
# the same "surface keyword says one thing, real meaning is another" pattern
# used throughout training/generation/build_seed_dataset.py's hand-authored
# hard negatives, but mined from real data here rather than invented.
# ---------------------------------------------------------------------------

_NEGATION_MARKERS = ["nahi", "nahin", "not", "no ", "never", "नहीं", "mat "]
_TRIGGER_WORDS = {
    "urgent": ["urgent", "emergency", "ज़रूरी", "जरूरी", "turant", "अर्जेंट"],
    "busy": ["busy", "व्यस्त"],
    "sleeping": ["sleeping", "so raha", "so rahi", "सो रहा", "सो रही"],
    "end_call": ["bye", "end the call", "hang up", "call kaat"],
}


@dataclass
class HardNegativeOpportunity:
    trigger_category: str
    match_count: int
    sample_quotes: list[dict]


def scan_hard_negative_opportunities(records: list[dict], max_samples: int = 8) -> list[HardNegativeOpportunity]:
    findings = []
    for category, triggers in _TRIGGER_WORDS.items():
        matches = []
        for r in records:
            trigger_hit = _contains_any(r["text"], triggers)
            negation_hit = _contains_any(r["text"], _NEGATION_MARKERS)
            if trigger_hit and negation_hit:
                matches.append({
                    "text": r["text"], "source_file": r["source_file"],
                    "trigger": trigger_hit, "negation": negation_hit,
                })
        findings.append(HardNegativeOpportunity(
            trigger_category=category, match_count=len(matches), sample_quotes=matches[:max_samples],
        ))
    return findings


# ---------------------------------------------------------------------------
# Language-specific analysis - reuses the language-mismatch data already
# computed during ingestion (merge_txt_sources.py's quality pass), broken
# down per source file, rather than recomputing it.
# ---------------------------------------------------------------------------

def language_distribution(records: list[dict]) -> dict:
    lang_counts = Counter(r["language"] for r in records)
    file_counts = Counter(r["source_file"] for r in records)
    return {
        "by_language": dict(lang_counts),
        "by_source_file": dict(file_counts),
        "total": len(records),
    }
