"""Build the submission archive.

Bundles the code, the frozen data splits' audit trail, the per-entry
predictions, the metrics, the figures and the documents into one zip, and
writes a manifest listing every file with its SHA-256 so a recipient can check
that nothing was altered in transit.

Deliberately excluded: the upstream ``repos/hallmark`` clone (it is public and
large; the README records the exact commit), the ``venv_btu`` virtual
environment, the raw bibtex-check HTTP cache (13 MB of third-party API
responses whose redistribution terms are not ours to decide), and the
checkpoint files (intermediate state, superseded by ``results/predictions``).

Usage::

    python -m hallmark_repro.package --out ../dist
"""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from hallmark_repro.common import FIG_DIR, PROJECT_ROOT, RESULTS_DIR, log, setup_logging

logger = setup_logging("package")

INCLUDE_DIRS = [
    ("code", PROJECT_ROOT / "code"),
    ("results", RESULTS_DIR),
    ("figures", FIG_DIR),
    ("docs", PROJECT_ROOT / "docs"),
    ("logs", PROJECT_ROOT / "logs"),
]
INCLUDE_FILES = [
    PROJECT_ROOT / "README_复现说明.md",
]

EXCLUDE_PATTERNS = [
    "__pycache__", ".pyc", ".pytest_cache",
    # bibtex-check's HTTP response cache: 17 MB of third-party API payloads
    # whose redistribution terms are not ours to decide.  Rebuilt automatically
    # on the first run.
    ".cache.fact_checker",
    # Intermediate resume state; superseded by results/predictions.
    "checkpoints",
    # Credentials must never leave the machine inside a submission archive.
    ".env",
]


def _skip(path: Path, base: Path) -> bool:
    """Skip generated artefacts: caches, bytecode, and resume checkpoints."""
    parts = path.relative_to(base).parts
    return any(pat in part for part in parts for pat in EXCLUDE_PATTERNS)


def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def collect() -> list[tuple[Path, str]]:
    items: list[tuple[Path, str]] = []
    for prefix, base in INCLUDE_DIRS:
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_dir() or _skip(p, base):
                continue
            items.append((p, f"{prefix}/{p.relative_to(base).as_posix()}"))
    for p in INCLUDE_FILES:
        if p.exists():
            items.append((p, p.name))
    return items


def main() -> None:
    ap = argparse.ArgumentParser(description="Package the submission")
    ap.add_argument("--out", default=str(PROJECT_ROOT / "dist"))
    ap.add_argument("--name", default=None)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    name = args.name or f"citation-verification-reproduction-{stamp}"
    zip_path = out_dir / f"{name}.zip"

    items = collect()
    manifest_lines = ["path\tsize_bytes\tsha256"]
    total = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path, arcname in items:
            zf.write(path, arcname)
            size = path.stat().st_size
            total += size
            manifest_lines.append(f"{arcname}\t{size}\t{_sha256(path)}")

        header = (
            f"citation veracity verification reproduction package\n"
            f"built: {datetime.now(timezone.utc).isoformat()}\n"
            f"files: {len(items)}\n"
            f"uncompressed bytes: {total}\n"
            f"upstream: https://github.com/rpatrik96/hallmark @ 80ce8ded\n"
        )
        zf.writestr("MANIFEST.txt", header + "\n".join(manifest_lines) + "\n")

    log("packaged %d files (%.1f MB uncompressed) -> %s",
        len(items), total / 1e6, zip_path)
    log("archive size: %.1f MB", zip_path.stat().st_size / 1e6)


if __name__ == "__main__":
    main()
