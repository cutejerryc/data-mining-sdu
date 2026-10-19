"""E2 - Reproduce the database-first cascade of HALLMARK.

Stage 1 is ``bibtex-check`` (the bibtex-updater CLI) querying CrossRef, DBLP,
DataCite, OpenAlex and Semantic Scholar.  Stage 2 is an LLM diagnoser that is
only invoked for entries Stage 1 could not settle.  The paper's headline table
comes from exactly this pipeline, and it is the one place where the released
numbers can be checked against a re-run line by line.

What is reproduced, and what is adapted
---------------------------------------
* Stage 1 is the released tool, installed unmodified from PyPI
  (``bibtex-updater``).  Its version is recorded in every metrics file.
* Stage 2 is **adapted**: the published runs used Claude Sonnet 4.6 through
  OpenRouter, which is not reachable here.  This project substitutes an
  OpenAI-compatible gateway (see ``llm_client``), so Stage-2 numbers are
  reported as a substitution, never as a reproduction of the published value.
* Both scoring stances are reported.  ``conservative`` excludes abstentions
  from the classification metrics; ``aggressive`` treats every entry the
  database could not affirmatively confirm as HALLUCINATED.  The gap between
  them is the "database-indexing-lag tax" the paper discusses.

Usage::

    python -m hallmark_repro.exp2_cascade --stage1-only --split test_public
    python -m hallmark_repro.exp2_cascade --cascade --split test_public --workers 4
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from hallmark_repro.common import (
    PROJECT_ROOT,
    REFERENCE_YEAR,
    RESULTS_DIR,
    SPLITS,
    load_split,
    log,
    metrics_path,
    save_predictions,
    score,
    setup_logging,
    write_json,
)
from hallmark_repro.llm_client import LLMConfig, configure_environment

logger = setup_logging("exp2_cascade")

#: Isolated venv holding the released bibtex-updater CLI (see README).
BTU_VENV = PROJECT_ROOT / "venv_btu"
BTU_BIN = BTU_VENV / ("Scripts" if os.name == "nt" else "bin") / (
    "bibtex-check.exe" if os.name == "nt" else "bibtex-check"
)


def prepare_environment() -> None:
    """Put bibtex-check on PATH and point the wrapper at it explicitly."""
    if not BTU_BIN.exists():
        raise RuntimeError(
            f"bibtex-check not found at {BTU_BIN}. Create the isolated venv first:\n"
            f"  python -m venv {BTU_VENV} && {BTU_VENV}/Scripts/pip install bibtex-updater"
        )
    os.environ["HALLMARK_BIBTEX_CHECK_BIN"] = str(BTU_BIN)
    os.environ["PATH"] = str(BTU_BIN.parent) + os.pathsep + os.environ.get("PATH", "")
    # CrossRef polite pool: a contact address gets a higher rate limit.
    os.environ.setdefault("BIBTEX_CHECK_MAILTO", "reproduction@example.edu")
    # Rate limit is per-service requests/minute; 60 is the safe default for an
    # unauthenticated run without an S2_API_KEY.
    os.environ.setdefault("HALLMARK_BIBTEX_CHECK_RATE_LIMIT", "60")

    # The upstream tool exits 5 (and the wrapper raises SourceOutageError) when
    # more than 10% of entries had at least one source lookup that did not
    # complete.  On this network that threshold is always exceeded because the
    # OpenReview API answers HTTP 403 to every request -- a persistent block,
    # not a transient outage.  Two of the six sources are therefore degraded
    # (OpenReview blocked; Semantic Scholar throttled without an API key), and
    # the run has to be scored with the guard overridden.  The per-entry
    # ``coverage_incomplete`` flag and the incomplete-lookup share are captured
    # into the metrics file so the condition is reported rather than hidden.
    os.environ.setdefault("HALLMARK_ALLOW_SOURCE_OUTAGE", "1")


def _bibtex_check_version() -> str | None:
    from hallmark.baselines.bibtexupdater import bibtex_check_version

    return bibtex_check_version(str(BTU_BIN))


def run_stage1(split: str, *, tag: str = "bibtexupdater", force: bool = False,
               timeout: float = 7200.0) -> list:
    """Stage 1 only: the released bibtex-check wrapper, no LLM."""
    from hallmark.baselines.registry import run_baseline_with_tool_run

    if not force and metrics_path(tag, split).exists():
        log("skip %s on %s (already scored)", tag, split)
        from hallmark_repro.common import load_predictions

        return load_predictions(tag, split)

    entries = load_split(split)
    log("stage1 %s on %s: %d entries", tag, split, len(entries))
    t0 = time.time()
    predictions, tool_run = run_baseline_with_tool_run(
        "bibtexupdater", entries, split=split,
        academic_only=True, reference_year=REFERENCE_YEAR, timeout=timeout,
    )
    elapsed = time.time() - t0
    log("stage1 done in %.1fs", elapsed)

    save_predictions(predictions, tag, split)
    extra = {"stage": "stage1_only", "wall_clock_seconds": round(elapsed, 2),
             "bibtex_check_version": _bibtex_check_version()}
    if tool_run is not None:
        from dataclasses import asdict

        extra["tool_run"] = asdict(tool_run)
        extra["source_condition"] = getattr(tool_run, "condition", None)
        extra["lookup_quality"] = _lookup_quality(tool_run)
        log("  source condition: %s", getattr(tool_run, "condition", None))
        log("  lookup quality: %s", extra["lookup_quality"])
    for mode in ("conservative", "aggressive"):
        res = score(entries, predictions, tag, split, eval_mode=mode, extra=extra)
        log("  [%s] DR=%.3f FPR=%.3f F1=%.3f tierW=%.3f cov=%.3f uncertain=%d",
            mode, res["detection_rate"], res["false_positive_rate"] or 0.0,
            res["f1_hallucination"], res["tier_weighted_f1"], res.get("coverage", 0),
            res.get("num_uncertain", 0))
    return predictions


def _lookup_quality(tool_run) -> dict:
    """Summarise how complete the Stage-1 lookups were.

    The assignment requires retrieval failure to be recorded rather than folded
    into "not found", so the share of entries whose sweep was incomplete, and
    which sources caused it, are reported next to every Stage-1 number.
    """
    from collections import Counter

    records = getattr(tool_run, "raw_records", None) or []
    statuses = Counter(str(r.get("status")) for r in records)
    incomplete = sum(1 for r in records if r.get("coverage_incomplete"))
    failed: Counter = Counter()
    for r in records:
        for s in (r.get("sources_failed") or []):
            failed[str(s)] += 1
    n = len(records) or 1
    return {
        "n_records": len(records),
        "status_distribution": dict(statuses),
        "coverage_incomplete_entries": incomplete,
        "coverage_incomplete_share": round(incomplete / n, 4),
        "sources_failed_counts": dict(failed),
        "sources_failed_share": {k: round(v / n, 4) for k, v in failed.items()},
        "abstained_entries": sum(1 for r in records if r.get("abstained")),
        "verdict_share": {
            "verified": round(statuses.get("verified", 0) / n, 4),
            "problematic": round(
                sum(v for k, v in statuses.items()
                    if k not in {"verified", "not_found", "api_error", "network_error",
                                 "coverage_incomplete", "missing", "skipped"}) / n, 4),
        },
    }


def run_cascade(split: str, *, aggressive_run: bool = False, workers: int = 4,
                model: str | None = None, force: bool = False, timeout: float = 10800.0) -> list:
    """Stage 1 + adapted Stage 2 LLM diagnosis."""
    from hallmark.baselines.cascade import run_cascade_with_health

    cfg = configure_environment(LLMConfig(model=model) if model else LLMConfig())
    tag = f"cascade_{cfg.slug}"
    if aggressive_run:
        tag += "_aggressive"

    if not force and metrics_path(tag, split).exists():
        log("skip %s on %s (already scored)", tag, split)
        from hallmark_repro.common import load_predictions

        return load_predictions(tag, split)

    entries = load_split(split)
    ckpt = RESULTS_DIR / "checkpoints" / f"{tag}__{split}"
    ckpt.mkdir(parents=True, exist_ok=True)

    log("cascade on %s: %d entries, stage2=%s", split, len(entries), cfg.model)
    t0 = time.time()
    predictions, health = run_cascade_with_health(
        entries,
        stage2_baseline="llm_agentic_openai",
        aggressive=aggressive_run,
        stage2_kwargs={
            "model": cfg.model,
            "api_key": cfg.api_key,
            "base_url": cfg.base_url,
            "checkpoint_dir": ckpt,
        },
        checkpoint_dir=ckpt,
        academic_only=True,
        timeout=timeout,
    )
    elapsed = time.time() - t0
    log("cascade done in %.1fs; health=%s", elapsed, health)

    save_predictions(predictions, tag, split)
    extra = {
        "stage": "cascade",
        "stage2_model": cfg.model,
        "stage2_base_url": cfg.base_url,
        "stage2_adapted": True,
        "wall_clock_seconds": round(elapsed, 2),
        "bibtex_check_version": _bibtex_check_version(),
        "batch_health": {
            "suspected_transport_failure": getattr(health, "suspected_transport_failure", None),
            "no_evidence_share": getattr(health, "no_evidence_share", None),
        },
    }
    for mode in ("conservative", "aggressive"):
        res = score(entries, predictions, tag, split, eval_mode=mode, extra=extra)
        log("  [%s] DR=%.3f FPR=%.3f F1=%.3f tierW=%.3f cov=%.3f uncertain=%d",
            mode, res["detection_rate"], res["false_positive_rate"] or 0.0,
            res["f1_hallucination"], res["tier_weighted_f1"], res.get("coverage", 0),
            res.get("num_uncertain", 0))
    return predictions


def main() -> None:
    ap = argparse.ArgumentParser(description="HALLMARK cascade reproduction")
    ap.add_argument("--split", default="test_public", choices=SPLITS)
    ap.add_argument("--stage1-only", action="store_true")
    ap.add_argument("--cascade", action="store_true")
    ap.add_argument("--aggressive", action="store_true", help="run the aggressive variant")
    ap.add_argument("--model", default=None, help="Stage-2 model id on the gateway")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    prepare_environment()
    if args.stage1_only:
        run_stage1(args.split, force=args.force)
    if args.cascade:
        run_cascade(args.split, aggressive_run=False, workers=args.workers,
                    model=args.model, force=args.force)
        if args.aggressive:
            run_cascade(args.split, aggressive_run=True, workers=args.workers,
                        model=args.model, force=args.force)
    if not args.stage1_only and not args.cascade:
        log("nothing to do: pass --stage1-only and/or --cascade")


if __name__ == "__main__":
    main()
