"""Per-stage latency measurement for one agent turn (see docs
"Observability"). Deliberately content-free: `StageTimings` only ever
holds stage names and millisecond durations, never turn text - there is no
field on this class capable of carrying a transcript.
"""

import time
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class StageTimings:
    """Records how long each named stage of one agent turn took, in
    milliseconds. Use `measure("stage_name")` as a context manager around
    each stage; read `durations_ms` afterward."""

    durations_ms: dict[str, float] = field(default_factory=dict)

    @contextmanager
    def measure(self, stage: str):
        started = time.monotonic()
        try:
            yield
        finally:
            self.durations_ms[stage] = (time.monotonic() - started) * 1000
