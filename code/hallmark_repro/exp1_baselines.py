"""E1 - Reproduce the deterministic (non-LLM) baselines of HALLMARK.

Each baseline is run on ``dev_public`` and ``test_public``, its per-entry
predictions are written to ``results/predictions/``, and it is scored with the
upstream evaluator so the numbers can be compared against the reference
results the authors ship in ``data/v1.2/baseline_results/``.

Two families are distinguished on purpose:

* **detectors** - strategies a real tool could run in production
  (``doi_only``, ``doi_presence_heuristic``, ``hallucitechecker``,
  ``checkifexist``, ``ensemble``, plus the two constant references).
* **leakage oracles** - ``title_oracle`` / ``venue_oracle`` look their answer up
  in a pool of *labelled* entries.  They are not methods; they measure how much
  of the benchmark is solvable by a shortcut that a real deployment cannot use.
  They are reported separately and never mixed into a comparison table.

Usage::

    python -m hallmark_repro.exp1_baselines --list
    python -m hallmark_repro.exp1_baselines doi_only checkifexist
    python -m hallmark_repro.exp1_baselines --all
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from hallmark_repro.common import (
    LOG_DIR,
    REFERENCE_YEAR,
    RESULTS_DIR,
    SPLITS,
    load_metrics,
    load_split,
    log,
    metrics_path,
    predictions_path,
    run_and_score,
    save_predictions,
    score,
    setup_logging,
    write_json,
)

logger = setup_logging("exp1_baselines")

#: Baselines we treat as production-plausible detectors.
DETECTORS = [
    "always_hallucinated",
    "always_valid",
    "random",
    "doi_presence_heuristic",
    "doi_only_no_prescreening",
    "doi_only",
    "hallucitechecker",
    "checkifexist",
    "ensemble",
]

#: Diagnostic baselines that consume ground-truth labels; kept apart.
ORACLES = ["title_oracle", "venue_oracle"]

#: Baselines that hit the network per entry and therefore benefit from threads.
NETWORK_BOUND = {"doi_only", "doi_only_no_prescreening", "hallucitechecker", "checkifexist", "ensemble"}

#: Baselines that query several scholarly services per entry, and are therefore
#: dominated by Semantic Scholar's 10 requests/minute unauthenticated budget.
MULTI_SOURCE = {"hallucitechecker", "checkifexist", "ensemble"}

#: Baselines whose cost we care about separately (API calls per entry).
DEFAULT_WORKERS = 6


def _run_parallel(tag: str, name: str, split: str, workers: int, **kwargs) -> dict:
    """Fan out a network-bound baseline across threads, then score it."""
    from hallmark_repro.parallel_runner import run_parallel

    entries = load_split(split)
    ckpt = RESULTS_DIR / "checkpoints" / f"{tag}__{split}.jsonl"

    log("running %s on %s (%d entries, %d workers) ...", name, split, len(entries), workers)
    t0 = time.time()
    predictions = run_parallel(
        name, entries, workers=workers, checkpoint_path=ckpt, split=split,
        progress_every=25, **kwargs,
    )
    elapsed = time.time() - t0
    log("%s on %s done in %.1fs (%d predictions)", name, split, elapsed, len(predictions))

    save_predictions(predictions, tag, split)
    extra = {"baseline_wall_clock_seconds": round(elapsed, 2), "workers": workers}
    out = score(entries, predictions, tag, split, eval_mode="conservative", extra=extra)
    log(
        "  [%s] DR=%.3f FPR=%.3f F1=%.3f tierW-F1=%.3f cov=%.3f api_calls=%.1f unevaluated=%d",
        split, out["detection_rate"], out["false_positive_rate"] or 0.0,
        out["f1_hallucination"], out["tier_weighted_f1"],
        out.get("coverage", float("nan")), out.get("mean_api_calls", 0),
        out.get("num_error_fallbacks", 0),
    )
    return out


def _run_subsample(tag: str, name: str, split: str, n: int, workers: int, **kwargs) -> dict:
    """Run a multi-source baseline on a frozen stratified subsample.

    Semantic Scholar is paced at 10 requests/minute without an API key, so a
    multi-source baseline needs roughly three hours per split.  The assignment
    permits a fixed subsample provided the rule is frozen in advance and the
    sample ids are reported, which is what ``exp4_llm.fixed_sample`` does; the
    ids are written to ``results/samples/`` and reused by every such baseline.
    """
    from hallmark_repro.exp4_llm import fixed_sample, subset_entries
    from hallmark_repro.parallel_runner import run_parallel

    ids = fixed_sample(split, n)
    entries = subset_entries(split, ids)
    ckpt = RESULTS_DIR / "checkpoints" / f"{tag}__{split}_{n}.jsonl"

    log("running %s on %s subsample (%d/%d entries, %d workers) ...",
        name, split, len(entries), len(load_split(split)), workers)
    t0 = time.time()
    predictions = run_parallel(
        name, entries, workers=workers, checkpoint_path=ckpt, split=split,
        progress_every=25, **kwargs,
    )
    elapsed = time.time() - t0
    log("%s on %s subsample done in %.1fs", name, split, elapsed)

    save_predictions(predictions, tag, f"{split}_{n}")
    extra = {
        "baseline_wall_clock_seconds": round(elapsed, 2), "workers": workers,
        "subsample": True, "sample_size": len(ids), "sample_seed": 20261018,
        "sample_file": f"results/samples/sample_{split}_{n}_20261018.json",
    }
    out = score(entries, predictions, tag, f"{split}_{n}", eval_mode="conservative", extra=extra)
    log(
        "  [%s/%d] DR=%.3f FPR=%.3f F1=%.3f tierW-F1=%.3f cov=%.3f",
        split, n, out["detection_rate"], out["false_positive_rate"] or 0.0,
        out["f1_hallucination"], out["tier_weighted_f1"], out.get("coverage", float("nan")),
    )
    return out


def _accepted_kwargs(name: str, kwargs: dict) -> dict:
    """Drop kwargs the registered runner does not accept.

    The constant baselines have no ``**_kw`` catch-all, so forwarding a
    reference year to them is a TypeError rather than a silent no-op.
    """
    import inspect

    from hallmark.baselines import registry

    runner = registry.get_registry()[name].runner
    try:
        sig = inspect.signature(runner)
    except (TypeError, ValueError):
        return kwargs
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return kwargs
    return {k: v for k, v in kwargs.items() if k in sig.parameters}


def run_one(name: str, split: str, workers: int, force: bool = False,
            sample: int = 0) -> dict | None:
    tag_split = f"{split}_{sample}" if sample else split
    if not force and metrics_path(name, tag_split).exists():
        log("skip %s on %s (already scored)", name, tag_split)
        return load_metrics(name, tag_split)

    kwargs: dict = {"reference_year": REFERENCE_YEAR}
    if name == "random":
        kwargs = {"seed": 42, "prevalence": 0.5}
    if name in ("title_oracle", "venue_oracle"):
        # These load their own reference pool (dev_public) inside the registry
        # wrapper; forwarding anything else trips the inner runner's signature.
        kwargs = {}
    kwargs = _accepted_kwargs(name, kwargs)

    if sample and name in MULTI_SOURCE:
        return _run_subsample(name, name, split, sample, workers, **kwargs)
    if name in NETWORK_BOUND and workers > 1:
        return _run_parallel(name, name, split, workers, **kwargs)
    res = run_and_score(name, split, eval_modes=("conservative",), **kwargs)
    return res["conservative"]


def main() -> None:
    ap = argparse.ArgumentParser(description="Run deterministic HALLMARK baselines")
    ap.add_argument("baselines", nargs="*", help="baseline names; default = all detectors")
    ap.add_argument("--splits", nargs="*", default=SPLITS)
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--oracles", action="store_true", help="also run the leakage oracles")
    ap.add_argument("--all", action="store_true", help="run every registered deterministic baseline")
    ap.add_argument("--force", action="store_true", help="re-run even when metrics exist")
    ap.add_argument("--sample", type=int, default=0,
                    help="restrict multi-source baselines to a frozen stratified subsample of "
                         "this size (0 = full split).  Needed because Semantic Scholar is paced "
                         "at 10 requests/minute without an API key.")
    ap.add_argument("--list", action="store_true", help="list the baselines this script runs")
    args = ap.parse_args()

    if args.list:
        print("detectors:", ", ".join(DETECTORS))
        print("oracles  :", ", ".join(ORACLES))
        return

    targets = args.baselines or (DETECTORS + ORACLES if args.all else DETECTORS)
    if args.oracles:
        targets = list(dict.fromkeys(targets + ORACLES))

    log("E1: %d baselines x %d splits (sample=%s)", len(targets), len(args.splits),
        args.sample or "full")
    summary: dict[str, dict] = {}
    for name in targets:
        for split in args.splits:
            try:
                res = run_one(name, split, args.workers, force=args.force, sample=args.sample)
                if res:
                    tag_split = f"{split}_{args.sample}" if args.sample and name in MULTI_SOURCE else split
                    summary[f"{name}__{tag_split}"] = {
                        "tool": name, "split": split,
                        "detection_rate": res["detection_rate"],
                        "fpr": res["false_positive_rate"],
                        "f1": res["f1_hallucination"],
                        "tier_weighted_f1": res["tier_weighted_f1"],
                        "coverage": res.get("coverage"),
                        "mean_api_calls": res.get("mean_api_calls"),
                        "ece": res.get("ece"),
                        "auroc": res.get("auroc"),
                        "subsample_size": args.sample if name in MULTI_SOURCE else None,
                    }
            except Exception as exc:                      # keep going on one bad baseline
                log("FAILED %s on %s: %s: %s", name, split, type(exc).__name__, exc)
                logger.exception("baseline %s on %s failed", name, split)

    write_json(RESULTS_DIR / "metrics" / "exp1_summary.json", summary)
    log("E1 summary written (%d rows)", len(summary))


if __name__ == "__main__":
    main()
