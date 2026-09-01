"""Tests for the numbered-list TXT parser, using small synthetic fixtures
that reproduce every real structural pattern found in the actual source
files (header line, blank line, wrapped/continuation lines, clean files) -
verified by hand against training/datasets/hindi_dataset_1.txt (the one
real file with wraps) before this was written.
"""

from training.pipeline.ingest.numbered_txt import analyze_file, parse_numbered_txt


def test_parses_clean_numbered_entries(tmp_path):
    f = tmp_path / "clean.txt"
    f.write_text("1. First sentence.\n2. Second sentence.\n3. Third sentence.\n", encoding="utf-8")
    entries = list(parse_numbered_txt(f))
    assert [e.text for e in entries] == ["First sentence.", "Second sentence.", "Third sentence."]
    assert [e.source_order for e in entries] == [1, 2, 3]


def test_skips_header_line_before_first_entry(tmp_path):
    f = tmp_path / "header.txt"
    f.write_text("My Dataset Title\n\n1. First sentence.\n2. Second sentence.\n", encoding="utf-8")
    entries = list(parse_numbered_txt(f))
    assert len(entries) == 2
    assert entries[0].text == "First sentence."

    report = analyze_file(f)
    assert report.header_lines == ["My Dataset Title"]
    assert report.entry_count == 2
    assert report.blank_line_count == 1


def test_merges_wrapped_continuation_lines(tmp_path):
    f = tmp_path / "wrapped.txt"
    f.write_text(
        "1. First sentence.\n"
        "2. This is a long sentence that got wrapped onto a\n"
        "   continuation line without a leading number.\n"
        "3. Third sentence.\n",
        encoding="utf-8",
    )
    entries = list(parse_numbered_txt(f))
    assert len(entries) == 3
    assert entries[1].text == (
        "This is a long sentence that got wrapped onto a continuation line without a leading number."
    )
    assert entries[1].line_count == 2


def test_skips_blank_lines_between_entries(tmp_path):
    f = tmp_path / "blanks.txt"
    f.write_text("1. First.\n\n\n2. Second.\n", encoding="utf-8")
    entries = list(parse_numbered_txt(f))
    assert len(entries) == 2

    report = analyze_file(f)
    assert report.blank_line_count == 2


def test_source_line_tracks_physical_line_number(tmp_path):
    f = tmp_path / "lines.txt"
    f.write_text("Title\n\n1. First.\n2. Second.\n", encoding="utf-8")
    entries = list(parse_numbered_txt(f))
    assert entries[0].source_line == 3  # after title (line 1) + blank (line 2)
    assert entries[1].source_line == 4


def test_detects_duplicate_source_numbers(tmp_path):
    f = tmp_path / "dup_numbers.txt"
    f.write_text("1. First.\n2. Second.\n2. Second again with a different number reused.\n", encoding="utf-8")
    report = analyze_file(f)
    assert report.duplicate_source_orders == [2]
    assert report.entry_count == 3  # all entries still parsed, none silently dropped


def test_empty_file_yields_no_entries(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("", encoding="utf-8")
    assert list(parse_numbered_txt(f)) == []
    report = analyze_file(f)
    assert report.entry_count == 0


def test_malformed_line_without_number_prefix_treated_as_header_or_continuation(tmp_path):
    f = tmp_path / "malformed.txt"
    f.write_text("not a numbered line at all\n1. Real entry.\n", encoding="utf-8")
    entries = list(parse_numbered_txt(f))
    assert len(entries) == 1
    assert entries[0].text == "Real entry."
    report = analyze_file(f)
    assert report.header_lines == ["not a numbered line at all"]


def test_streaming_parse_does_not_read_whole_file_into_memory(tmp_path):
    """parse_numbered_txt is a generator - verify it yields incrementally
    rather than materializing a list internally, by checking the return
    type is a generator, not a list."""
    f = tmp_path / "big.txt"
    f.write_text("1. One.\n2. Two.\n", encoding="utf-8")
    result = parse_numbered_txt(f)
    import types
    assert isinstance(result, types.GeneratorType)
