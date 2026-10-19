"""Shared utilities for the HALLMARK reproduction experiments.

Every experiment script in this package imports from here so that the
provenance record (upstream commit, split hashes, run time) is written the
same way everywhere.  Nothing in this module touches ground-truth labels
before a prediction file has been produced by a baseline.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]          # .../project
REPO_ROOT = PROJECT_ROOT / "repos" / "hallmark"             # upstream clone
RESULTS_DIR = PROJECT_ROOT / "results"
PRED_DIR = RESULTS_DIR / "predictions"
METRIC_DIR = RESULTS_DIR / "metrics"
LOG_DIR = PROJECT_ROOT / "logs"
FIG_DIR = PROJECT_ROOT / "figures"

for _d in (RESULTS_DIR, PRED_DIR, METRIC_DIR, LOG_DIR, FIG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# --------------------------------------------------------------------------
# Run constants
# --------------------------------------------------------------------------

# HALLMARK pins the benchmark reference year to the dataset freeze date; we pass
# it explicitly so that a rerun in a later calendar year produces the same
# future-date verdicts as the released numbers.
REFERENCE_YEAR = 2026

#: Splits we evaluate.  ``*_blind`` files are what baselines actually receive;
#: we always evaluate on the full files so that labels stay available to the
#: scorer, and hand only ``to_blind()`` objects to the baselines.
SPLITS = ["dev_public", "test_public", "stress_test"]

DATA_VERSION = "v1.2"


# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------

def setup_logging(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(LOG_DIR / f"{name}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


def log(msg: str, *args: Any) -> None:
    """Timestamped progress line on stderr (kept out of machine-readable stdout)."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg % args if args else msg}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

def data_file(split: str) -> Path:
    from hallmark.dataset.loader import SPLIT_PATHS

    return REPO_ROOT / "data" / DATA_VERSION / SPLIT_PATHS[split]


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def load_split(split: str):
    """Load a split with ground-truth labels (scorer side only)."""
    from hallmark.dataset.loader import load_split as _load

    return _load(split, version=DATA_VERSION, data_dir=REPO_ROOT / "data")


def upstream_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30, check=True,
        )
        return out.stdout.strip()
    except Exception:                                          # pragma: no cover
        return "unknown"


def environment_record() -> dict[str, Any]:
    import hallmark

    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "hallmark_version": getattr(hallmark, "__version__", "unknown"),
        "hallmark_commit": upstream_commit(),
        "hallmark_repo": str(REPO_ROOT),
        "data_version": DATA_VERSION,
        "reference_year": REFERENCE_YEAR,
    }


# --------------------------------------------------------------------------
# Prediction I/O and scoring
# --------------------------------------------------------------------------

def predictions_path(tag: str, split: str) -> Path:
    return PRED_DIR / f"{tag}__{split}.jsonl"


def metrics_path(tag: str, split: str) -> Path:
    return METRIC_DIR / f"{tag}__{split}.json"


def save_predictions(predictions: Iterable, tag: str, split: str) -> Path:
    from hallmark.dataset.schema import save_predictions as _save

    path = predictions_path(tag, split)
    _save(list(predictions), path)
    return path


def load_predictions(tag: str, split: str):
    from hallmark.dataset.schema import load_predictions as _load

    return _load(predictions_path(tag, split))


def score(
    entries: list,
    predictions: list,
    tag: str,
    split: str,
    *,
    eval_mode: str = "conservative",
    compute_ci: bool = False,
    n_bootstrap: int = 1000,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score predictions with the upstream evaluator and persist the JSON.

    Returns the evaluation result as a plain dict, with a manifest block added.
    """
    from dataclasses import asdict

    from hallmark.evaluation.metrics import evaluate

    result = evaluate(
        entries,
        predictions,
        tool_name=tag,
        split_name=split,
        eval_mode=eval_mode,
        compute_ci=compute_ci,
        n_bootstrap=n_bootstrap,
        ci_seed=20261018,
    )
    payload = asdict(result)
    payload["_manifest"] = run_manifest(tag, split, entries, predictions, eval_mode)
    if extra:
        payload["_extra"] = extra
    out = metrics_path(tag, split) if eval_mode == "conservative" else (
        METRIC_DIR / f"{tag}__{split}__{eval_mode}.json"
    )
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def run_manifest(tag: str, split: str, entries: list, predictions: list, eval_mode: str) -> dict[str, Any]:
    from collections import Counter

    answered = [p for p in predictions if getattr(p, "evaluated", True) and p.label != "UNCERTAIN"]
    uncertain = [p for p in predictions if p.label == "UNCERTAIN"]
    unevaluated = [p for p in predictions if not getattr(p, "evaluated", True)]

    # Subsample runs are scored under a tag like ``test_public_200``; the hash
    # belongs to the underlying split file, so strip the size suffix.
    base_split = split
    try:
        data_file(base_split)
    except KeyError:
        base_split = split.rsplit("_", 1)[0]
    return {
        "tag": tag,
        "split": split,
        "data_split_hashed": base_split,
        "eval_mode": eval_mode,
        "n_entries": len(entries),
        "n_predictions": len(predictions),
        "n_answered": len(answered),
        "n_uncertain": len(uncertain),
        "n_unevaluated": len(unevaluated),
        "label_counts": dict(Counter(p.label for p in predictions)),
        "split_sha256": sha256_file(data_file(base_split)),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "api_calls": sum(p.api_calls for p in predictions),
        "wall_clock_seconds": round(sum(p.wall_clock_seconds for p in predictions), 2),
        "environment": environment_record(),
        "command": " ".join(sys.argv),
    }


# --------------------------------------------------------------------------
# Baseline execution
# --------------------------------------------------------------------------

def run_and_score(
    name: str,
    split: str,
    *,
    tag: str | None = None,
    eval_modes: tuple[str, ...] = ("conservative",),
    compute_ci: bool = False,
    save: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run a registered baseline on a split, persist predictions, then score it."""
    from hallmark.baselines import registry

    tag = tag or name
    entries = load_split(split)
    log("running baseline %s on %s (%d entries) ...", name, split, len(entries))

    t0 = time.time()
    predictions, tool_run = registry.run_baseline_with_tool_run(name, entries, split=split, **kwargs)
    elapsed = time.time() - t0
    log("baseline %s on %s finished in %.1fs (%d predictions)", name, split, elapsed, len(predictions))

    if save:
        save_predictions(predictions, tag, split)

    extra = {"baseline_wall_clock_seconds": round(elapsed, 2), "run_kwargs": {
        k: (str(v) if not isinstance(v, (int, float, bool, str, type(None))) else v)
        for k, v in kwargs.items()
    }}
    if tool_run is not None:
        try:
            from dataclasses import asdict as _asdict
            extra["tool_run"] = _asdict(tool_run)
        except Exception:
            extra["tool_run"] = str(tool_run)

    results: dict[str, Any] = {}
    for mode in eval_modes:
        res = score(entries, predictions, tag, split, eval_mode=mode, compute_ci=compute_ci, extra=extra)
        results[mode] = res
        log(
            "  [%s] DR=%.3f FPR=%s F1=%.3f tierW-F1=%.3f coverage=%.3f",
            mode,
            res["detection_rate"],
            f"{res['false_positive_rate']:.3f}" if res["false_positive_rate"] is not None else "n/a",
            res["f1_hallucination"],
            res["tier_weighted_f1"],
            res.get("coverage", float("nan")),
        )
    return results


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_metrics(tag: str, split: str, mode: str = "conservative") -> dict[str, Any]:
    p = metrics_path(tag, split) if mode == "conservative" else (
        METRIC_DIR / f"{tag}__{split}__{mode}.json"
    )
    return json.loads(p.read_text(encoding="utf-8"))
