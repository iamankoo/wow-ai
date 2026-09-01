"""Streaming ingestion adapters for the v3+ pipeline - converts a
source-specific format into RawExample records without ever loading a full
source file into memory. See training/pipeline/ingest/numbered_txt.py for
the format used by the hand_collected TXT sources under training/datasets/.
"""
