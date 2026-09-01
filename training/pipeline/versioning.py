"""Dataset versioning: writes a version directory
(training/datasets/versions/<version>/) with raw + processed data plus a
MANIFEST.json carrying per-file SHA-256 checksums and counts, so any
dataset version is independently verifiable and reproducible - "did this
training run actually use the data I think it did" is always answerable by
recomputing a hash, not trusting a filename.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

VERSIONS_DIR = Path(__file__).resolve().parents[1] / "datasets" / "versions"


@dataclass
class ManifestEntry:
    path: str
    sha256: str
    size_bytes: int
    line_count: int


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _count_lines(path: Path) -> int:
    with path.open(encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def build_manifest(version_dir: Path, files: list[Path]) -> dict:
    entries = []
    for f in files:
        if not f.exists():
            continue
        entries.append(ManifestEntry(
            path=str(f.relative_to(version_dir)).replace("\\", "/"),
            sha256=_sha256_of_file(f),
            size_bytes=f.stat().st_size,
            line_count=_count_lines(f),
        ))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": [vars(e) for e in entries],
        "total_lines": sum(e.line_count for e in entries),
    }


def write_manifest(version_dir: Path, files: list[Path]) -> Path:
    manifest = build_manifest(version_dir, files)
    manifest_path = version_dir / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest_path


def verify_manifest(version_dir: Path) -> tuple[bool, list[str]]:
    """Recomputes every file's checksum and compares against MANIFEST.json.
    Returns (all_ok, list_of_mismatches)."""
    manifest_path = version_dir / "MANIFEST.json"
    if not manifest_path.exists():
        return False, [f"no MANIFEST.json in {version_dir}"]

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mismatches = []
    for entry in manifest["files"]:
        file_path = version_dir / entry["path"]
        if not file_path.exists():
            mismatches.append(f"missing file: {entry['path']}")
            continue
        actual = _sha256_of_file(file_path)
        if actual != entry["sha256"]:
            mismatches.append(f"checksum mismatch: {entry['path']}")
    return not mismatches, mismatches


def version_dir_for(version: str) -> Path:
    return VERSIONS_DIR / version
