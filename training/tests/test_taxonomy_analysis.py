"""Tests for training/pipeline/taxonomy_analysis.py's pure scanning/
labeling logic - synthetic records, no dependency on the real 33K files.
"""

from training.pipeline.taxonomy_analysis import (
    label_with_rule_based,
    scan_confusion_pairs,
    scan_hard_negative_opportunities,
    scan_taxonomy_gaps,
)


def _rec(text, source_file="hindi_dataset_1.txt", language="hi"):
    return {"id": "x", "text": text, "language": language, "source_file": source_file,
            "source_line": 1, "source_order": 1}


def test_rule_based_labeling_produces_candidate_for_matched_pattern(tmp_path):
    records = [_rec("I'm busy right now, take messages instead.", language="en")]
    summary = label_with_rule_based(records, tmp_path / "out.jsonl")
    assert summary.candidate_count == 1
    assert summary.review_count == 0


def test_rule_based_labeling_produces_review_for_unmatched_text(tmp_path):
    records = [_rec("मुझे सुबह चाय बनानी है क्योंकि आज मौसम अच्छा है।")]
    summary = label_with_rule_based(records, tmp_path / "out.jsonl")
    assert summary.candidate_count == 0
    assert summary.review_count == 1


def test_rule_based_labeling_writes_valid_jsonl_with_label_source(tmp_path):
    import json
    records = [_rec("I'm busy right now.", language="en"), _rec("random unrelated text", language="en")]
    out_path = tmp_path / "out.jsonl"
    label_with_rule_based(records, out_path)
    lines = [json.loads(l) for l in out_path.read_text(encoding="utf-8").splitlines()]
    assert lines[0]["label_source"] == "candidate_rule_based"
    assert lines[1]["label_source"] == "review"


def test_gap_scanner_finds_real_matches_for_callback_phrase():
    records = [_rec("Please call back later.", language="en") for _ in range(20)]
    findings = scan_taxonomy_gaps(records)
    callback = next(f for f in findings if f.concept == "CALLBACK_REQUEST")
    assert callback.match_count == 20
    assert callback.verdict == "supported"


def test_gap_scanner_reports_no_evidence_for_absent_concept():
    records = [_rec("I'm busy right now.", language="en")]
    findings = scan_taxonomy_gaps(records)
    block_caller = next(f for f in findings if f.concept == "BLOCK_CALLER")
    assert block_caller.match_count == 0
    assert block_caller.verdict == "no_evidence"


def test_gap_scanner_covers_every_proposed_concept():
    findings = scan_taxonomy_gaps([_rec("anything")])
    concepts = {f.concept for f in findings}
    assert "HOLD_CALL" in concepts
    assert "REDIAL" in concepts
    assert "CALLBACK_REQUEST" in concepts
    assert len(concepts) == 13


def test_confusion_pair_scanner_finds_cooccurrence():
    records = [_rec("This is urgent but honestly it's not that urgent, no rush.", language="en")]
    findings = scan_confusion_pairs(records)
    urgent_pair = next(f for f in findings if f.pair == "URGENT_CALL_vs_NON_URGENT_CALL")
    assert urgent_pair.match_count == 1


def test_confusion_pair_scanner_zero_when_only_one_signal_present():
    records = [_rec("This is urgent.", language="en")]
    findings = scan_confusion_pairs(records)
    urgent_pair = next(f for f in findings if f.pair == "URGENT_CALL_vs_NON_URGENT_CALL")
    assert urgent_pair.match_count == 0


def test_hard_negative_scanner_finds_negated_trigger():
    records = [_rec("It's not urgent at all.", language="en")]
    findings = scan_hard_negative_opportunities(records)
    urgent_finding = next(f for f in findings if f.trigger_category == "urgent")
    assert urgent_finding.match_count == 1


def test_hard_negative_scanner_zero_for_unnegated_trigger():
    records = [_rec("This is extremely urgent.", language="en")]
    findings = scan_hard_negative_opportunities(records)
    urgent_finding = next(f for f in findings if f.trigger_category == "urgent")
    assert urgent_finding.match_count == 0
