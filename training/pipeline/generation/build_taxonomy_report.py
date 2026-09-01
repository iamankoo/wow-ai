"""Assembles the final 33K taxonomy analysis report from the pieces
produced by training/pipeline/taxonomy_analysis.py:
- rule-based candidate labels (wow_33k_candidate_labels.jsonl)
- the v1 cross-check summary (reports/wow_33k_v1_crosscheck.json)
- the gap/confusion/hard-negative scan (reports/_gap_scan_raw.json)

Writes training/datasets/reports/wow_33k_taxonomy_analysis.{json,md}.
Never trains anything - this is report assembly only.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from training.pipeline.taxonomy_analysis import (
    CANDIDATE_LABELS_PATH,
    REPORTS_DIR,
    _load_33k,
    label_with_rule_based,
    language_distribution,
    scan_confusion_pairs,
    scan_hard_negative_opportunities,
    scan_taxonomy_gaps,
)
from dataclasses import asdict

OUTPUT_JSON = REPORTS_DIR / "wow_33k_taxonomy_analysis.json"
OUTPUT_MD = REPORTS_DIR / "wow_33k_taxonomy_analysis.md"
CROSSCHECK_PATH = REPORTS_DIR / "wow_33k_v1_crosscheck.json"
CROSSCHECK_CONDITIONAL_PATH = REPORTS_DIR / "wow_33k_v1_crosscheck_conditional.json"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

    records = _load_33k()
    rule_based_summary = label_with_rule_based(records, CANDIDATE_LABELS_PATH)
    gaps = scan_taxonomy_gaps(records)
    confusions = scan_confusion_pairs(records)
    hard_negatives = scan_hard_negative_opportunities(records)
    lang_dist = language_distribution(records)

    v1_crosscheck = None
    if CROSSCHECK_PATH.exists():
        v1_crosscheck = json.loads(CROSSCHECK_PATH.read_text(encoding="utf-8"))
    v1_crosscheck_conditional = None
    if CROSSCHECK_CONDITIONAL_PATH.exists():
        v1_crosscheck_conditional = json.loads(CROSSCHECK_CONDITIONAL_PATH.read_text(encoding="utf-8"))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_examples": len(records),
        "language_distribution": lang_dist,
        "rule_based_candidate_labels": asdict(rule_based_summary),
        "v1_crosscheck_sample": v1_crosscheck,
        "v1_crosscheck_conditional_on_rule_based_commitment": v1_crosscheck_conditional,
        "taxonomy_gap_findings": [asdict(g) for g in gaps],
        "confusion_pair_findings": [asdict(c) for c in confusions],
        "hard_negative_opportunities": [asdict(h) for h in hard_negatives],
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    _write_markdown(report, OUTPUT_MD)
    print(f"Wrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_MD}")


def _write_markdown(report: dict, path: Path) -> None:
    lines = ["# WOW 33K Taxonomy Analysis", "", f"Generated: {report['generated_at']}",
              f"Total examples: {report['total_examples']}", ""]

    lines.append("## Language distribution")
    lines.append("")
    for k, v in report["language_distribution"]["by_source_file"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    rb = report["rule_based_candidate_labels"]
    lines.append("## Rule-based candidate labeling (full 33K coverage)")
    lines.append("")
    lines.append(f"- Candidates: {rb['candidate_count']} ({100*rb['candidate_count']/rb['total']:.1f}%)")
    lines.append(f"- Review (no rule matched): {rb['review_count']} ({100*rb['review_count']/rb['total']:.1f}%)")
    lines.append(f"- Intent distribution: {rb['intent_distribution']}")
    lines.append(f"- Per-file candidate rate: {rb['per_file_candidate_rate']}")
    lines.append("")

    if report["v1_crosscheck_sample"]:
        v1 = report["v1_crosscheck_sample"]
        lines.append("## v1 model cross-check (stratified sample)")
        lines.append("")
        lines.append(f"- Sample size: {v1['sample_size']}")
        lines.append(f"- Intent agreement with rule-based: {v1['intent_agreement_rate']:.1%}")
        lines.append(f"- Action agreement: {v1['action_agreement_rate']:.1%}")
        lines.append(f"- Context agreement: {v1['context_agreement_rate']:.1%}")
        lines.append(f"- Avg intent confidence: {v1['avg_intent_confidence']:.3f}")
        lines.append(f"- Low-confidence count (<0.6): {v1['low_confidence_count']}")
        lines.append("")
        lines.append(
            "**Caveat**: the raw intent agreement above is misleadingly low because "
            "rule_based defaults to UNKNOWN for ~92% of this dataset while v1 never "
            "abstains - see the conditional analysis below for the meaningful comparison."
        )
        lines.append("")

    cond = report.get("v1_crosscheck_conditional_on_rule_based_commitment")
    if cond:
        lines.append("## v1 vs rule-based agreement, conditional on rule-based actually committing to a label")
        lines.append("")
        lines.append(f"- Sample: {cond['n']} examples where rule_based's candidate_intent != UNKNOWN")
        lines.append(f"- Intent agreement: {cond['intent_agreement_conditional']:.1%}")
        lines.append(f"- Action agreement: {cond['action_agreement_conditional']:.1%}")
        lines.append(f"- Context agreement: {cond['context_agreement_conditional']:.1%} (n={cond['context_n']})")
        lines.append("")

    lines.append("## Taxonomy gap findings")
    lines.append("")
    lines.append("| Concept | Matches | Rate | Verdict |")
    lines.append("|---|---|---|---|")
    for g in report["taxonomy_gap_findings"]:
        lines.append(f"| {g['concept']} | {g['match_count']} | {g['match_rate']:.4f} | {g['verdict']} |")
    lines.append("")

    lines.append("## Confusion pair findings")
    lines.append("")
    lines.append("| Pair | Co-occurrence matches |")
    lines.append("|---|---|")
    for c in report["confusion_pair_findings"]:
        lines.append(f"| {c['pair']} | {c['match_count']} |")
    lines.append("")

    lines.append("## Hard-negative opportunities")
    lines.append("")
    for h in report["hard_negative_opportunities"]:
        lines.append(f"- {h['trigger_category']}: {h['match_count']} matches")
    lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
