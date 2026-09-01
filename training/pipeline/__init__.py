"""Production-grade dataset pipeline for WOW's long-term (1M+) call/voice-
command dataset track ("v3+"). See docs/DATASET.md for the full design.

This is deliberately separate from training/generation/build_seed_dataset.py
and the v0/v1/v1.1 pipeline under training/preprocessing/ - those stay
exactly as they are (already prepared for v1.1 training). This package is
the more general infrastructure needed to grow a dataset from thousands of
hand-authored examples toward millions, from multiple sources, with real
quality/dedup/PII/versioning gates - not a replacement for the existing
pipeline, an addition alongside it.
"""
