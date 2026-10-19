"""E2b - Complete the cascade without re-running Stage 1.

The upstream ``cascade_db_diagnosis`` runs Stage 1 (bibtex-check) and then
routes the entries Stage 1 could not settle to a Stage 2 LLM diagnoser.  Running
the whole thing end to end costs roughly four hours here, and Stage 1 is
deterministic given its disk cache, so this script reconstructs the cascade from
the Stage 1 output that has already been scored:

1. read the Stage 1 predictions and their per-entry statuses;
2. route to Stage 2 exactly the statuses upstream routes (``ROUTE_TO_STAGE2``),
   imported from the upstream module rather than copied, so a change in the
   upstream vocabulary cannot silently diverge from this reconstruction;
3. run the Stage 2 model on only those entries;
4. combine, and score under both stances.

What this reproduces and what it adapts
---------------------------------------
* The **routing rule and the combination** are the upstream ones: an entry
  Stage 1 answered keeps its Stage 1 verdict, an entry Stage 1 deferred gets a
  Stage 2 verdict, and aggressive scoring promotes whatever is still unresolved.
* The **Stage 2 model is substituted** (see ``llm_client``): the published runs
  used Claude Sonnet 4.6 through OpenRouter, which is unreachable here.  This
  script also uses the zero-shot verification prompt rather than the agentic
  tool-use harness, because Stage 2's tools (OpenAlex, Semantic Scholar) are the
  very sources that are degraded in this environment; giving the model tools
  that return 429 would measure the outage, not the method.
* Consequently the cascade numbers here are an **adaptation**, reported beside
  the published values but never as a reproduction of them.

Usage::

    python -m hallmark_repro.exp2b_cascade_from_stage1 --split test_public
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from hallmark_repro.common import (
    RESULTS_DIR,
    load_split,
    log,
    metrics_path,
    predictions_path,
    save_predictions,
    score,
    setup_logging,
    write_json,
)
from hallmark_repro.llm_client import LLMConfig, configure_environment

logger = setup_logging("exp2b_cascade")

STAGE1_TAG = "bibtexupdater"
OUT_DIR = RESULTS_DIR / "cascade"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_stage1(split: str):
    """Stage 1 predictions plus the per-entry status map."""
    metrics = json.loads(metrics_path(STAGE1_TAG, split).read_text(encoding="utf-8"))
    raw = ((metrics.get("_extra") or {}).get("tool_run") or {}).get("raw_records") or []
    status_map = {r["key"]: str(r.get("status")) for r in raw}

    preds: dict[str, dict] = {}
    with open(predictions_path(STAGE1_TAG, split), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rec = json.loads(line)
                preds[rec["bibtex_key"]] = rec
    return preds, status_map, metrics


def route(status_map: dict[str, str]) -> tuple[set[str], set[str]]:
    """Split keys into Stage-1-resolved and Stage-2-deferred, using upstream's rule."""
    from hallmark.baselines.cascade import ROUTE_TO_STAGE2

    deferred = {k for k, s in status_map.items() if s in ROUTE_TO_STAGE2}
    resolved = set(status_map) - deferred
    return resolved, deferred


def run_stage2(entries: list, split: str, model: str, workers: int, force: bool) -> dict[str, dict]:
    """Run the zero-shot verifier on the deferred entries only."""
    from hallmark_repro.exp4_llm import MAX_COMPLETION_TOKENS
    from hallmark_repro.parallel_runner import run_parallel

    tag = f"cascade_stage2_{model.replace('.', '').replace('/', '_')}"
    ckpt = RESULTS_DIR / "checkpoints" / f"{tag}__{split}.jsonl"

    if force and ckpt.exists():
        ckpt.unlink()

    log("Stage 2 on %d deferred entries of %s with %s", len(entries), split, model)
    t0 = time.time()
    preds = run_parallel(
        "llm_openai", entries, workers=workers, checkpoint_path=ckpt, split=split,
        progress_every=20, model=model, max_completion_tokens=MAX_COMPLETION_TOKENS,
    )
    log("Stage 2 finished in %.0fs", time.time() - t0)
    return {p.bibtex_key: p.to_dict() for p in preds}


def combine(stage1: dict[str, dict], stage2: dict[str, dict],
            resolved: set[str], deferred: set[str]) -> list:
    """Stage 1 verdict where it answered, Stage 2 verdict where it deferred."""
    from hallmark.dataset.schema import Prediction

    out: list = []
    for key, p1 in stage1.items():
        if key in resolved:
            rec = dict(p1)
            rec["cascade_stage"] = "stage1_db"
            out.append(Prediction.from_dict(rec))
        else:
            p2 = stage2.get(key)
            if p2 is None:
                rec = dict(p1)
                rec["reason"] = f"[cascade] deferred by Stage 1, no Stage 2 verdict | {rec.get('reason', '')}"
                out.append(Prediction.from_dict(rec))
            else:
                rec = dict(p2)
                rec["cascade_stage"] = "stage2_diagnosis"
                rec["reason"] = f"[Stage 2] {rec.get('reason', '')}"
                out.append(Prediction.from_dict(rec))
    return out


def aggressive_variant(predictions: list) -> list:
    """Promote whatever is still unresolved, as the upstream aggressive stance does."""
    from hallmark.dataset.schema import Prediction

    out = []
    for p in predictions:
        if p.label == "UNCERTAIN" or not getattr(p, "evaluated", True):
            out.append(Prediction(
                bibtex_key=p.bibtex_key, label="HALLUCINATED", confidence=0.55,
                reason=f"[aggressive] unresolved after Stage 2 | {p.reason[:150]}",
                cascade_stage=p.cascade_stage, api_calls=p.api_calls,
                wall_clock_seconds=p.wall_clock_seconds,
                predicted_hallucination_type="plausible_fabrication",
            ))
        else:
            out.append(p)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Reconstruct the cascade from saved Stage 1 output")
    ap.add_argument("--split", default="test_public")
    ap.add_argument("--model", default=None)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    cfg = configure_environment(LLMConfig(model=args.model) if args.model else LLMConfig())
    entries = load_split(args.split)
    by_key = {e.bibtex_key: e for e in entries}
    stage1, status_map, s1_metrics = load_stage1(args.split)
    resolved, deferred = route(status_map)
    log("routing: %d resolved by Stage 1, %d deferred to Stage 2",
        len(resolved), len(deferred))

    tag = f"cascade_recon_{cfg.slug}"
    if metrics_path(tag, args.split).exists() and not args.force:
        log("already scored; use --force to redo")
        return

    deferred_entries = [by_key[k] for k in sorted(deferred) if k in by_key]
    stage2 = run_stage2(deferred_entries, args.split, cfg.model, args.workers, args.force)
    combined = combine(stage1, stage2, resolved, deferred)
    save_predictions(combined, tag, args.split)

    extra = {
        "stage": "cascade_reconstructed",
        "stage1_tag": STAGE1_TAG,
        "stage2_model": cfg.model,
        "stage2_base_url": cfg.base_url,
        "stage2_prompt": "zero-shot verification (agentic tool use not used; see docstring)",
        "stage2_adapted": True,
        "n_resolved_by_stage1": len(resolved),
        "n_deferred_to_stage2": len(deferred),
        "stage1_source_condition": (s1_metrics.get("_extra") or {}).get("source_condition"),
        "stage1_lookup_quality": (s1_metrics.get("_extra") or {}).get("lookup_quality"),
    }

    results = {}
    for mode, preds in (("conservative", combined), ("aggressive", aggressive_variant(combined))):
        res = score(entries, preds, tag, args.split, eval_mode=mode, extra=extra)
        results[mode] = res
        log("  [%s] DR=%.3f FPR=%.3f F1=%.3f tierW=%.3f cov=%.3f uncertain=%d",
            mode, res["detection_rate"], res["false_positive_rate"] or 0.0,
            res["f1_hallucination"], res["tier_weighted_f1"], res.get("coverage", 0),
            res.get("num_uncertain", 0))

    write_json(OUT_DIR / f"cascade_recon_summary__{args.split}.json", {
        "stage1": {k: s1_metrics.get(k) for k in
                   ("detection_rate", "false_positive_rate", "f1_hallucination",
                    "tier_weighted_f1", "mcc", "auroc", "coverage")},
        "cascade_conservative": {k: results["conservative"].get(k) for k in
                                 ("detection_rate", "false_positive_rate", "f1_hallucination",
                                  "tier_weighted_f1", "mcc", "auroc", "coverage")},
        "cascade_aggressive": {k: results["aggressive"].get(k) for k in
                               ("detection_rate", "false_positive_rate", "f1_hallucination",
                                "tier_weighted_f1", "mcc", "auroc", "coverage")},
        "n_resolved_by_stage1": len(resolved),
        "n_deferred_to_stage2": len(deferred),
    })


if __name__ == "__main__":
    main()
