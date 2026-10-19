"""E4 - LLM baselines on the same benchmark, for a rule-vs-model comparison.

HALLMARK ships LLM baselines that were published against GPT-5.1 / Claude
Sonnet 4.6 / OpenRouter models.  None of those endpoints is reachable from this
machine, so this experiment substitutes an OpenAI-compatible gateway
(``https://opencode.ai/zen/go/v1``) and reports every number as an **adaptation
under a substituted model**, never as a reproduction of the published value.

Three conditions are run so the comparison isolates something useful:

``llm_zeroshot``   the model alone, prompted with the BibTeX entry and asked for
                   a verdict plus a hallucination type.  No tools, no retrieval.
``llm_agentic``    the model with the upstream tool set (DOI resolution,
                   Crossref/OpenAlex/arXiv search), up to 5 tool calls.
``rule_then_llm``  the deterministic cascade: Stage 1 bibtex-check, Stage 2 the
                   model, i.e. the same architecture as the paper's headline
                   baseline.  (Produced by ``exp2_cascade``; referenced here.)

Cost is recorded per entry (API calls, wall clock) so the accuracy/cost trade-off
can be plotted rather than asserted.

Usage::

    python -m hallmark_repro.exp4_llm --mode zeroshot --model deepseek-v4.1-flash --n 200
    python -m hallmark_repro.exp4_llm --mode agentic  --model glm-5.3-flash      --n 200
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from hallmark_repro.common import (
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

logger = setup_logging("exp4_llm")

CKPT_DIR = RESULTS_DIR / "checkpoints"
SAMPLE_DIR = RESULTS_DIR / "samples"
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)


#: The substituted models are heavy reasoners: ``deepseek-v4.1-flash`` spends the
#: entire default 1024-token budget on hidden ``reasoning_content`` and returns an
#: empty visible answer with ``finish_reason=length``.  Measured on this gateway,
#: 1024 tokens gave 1/8 usable replies and 8192 tokens gave 6/6, so the budget is
#: raised for every LLM condition.  The upstream default is left untouched for the
#: published models, which are not reasoning models in this sense.
MAX_COMPLETION_TOKENS = 8192


def fixed_sample(split: str, n: int, seed: int = 20261018) -> list[str]:
    """A stratified sample whose ids are frozen before any model runs.

    Proportional over (label, hallucination type).  The ids are written to disk
    so that the same subset can be handed to every model and every mode — the
    assignment requires the sample rule to be fixed in advance and reported,
    and it requires the excluded entries to stay visible rather than vanish.
    """
    from hallmark_repro.exp3_subtests import stratified_subsample

    path = SAMPLE_DIR / f"sample_{split}_{n}_{seed}.json"
    if path.exists():
        # Reuse the frozen ids: every baseline and every model must see exactly
        # the same subset, and the sample must not move between runs.
        return json.loads(path.read_text(encoding="utf-8"))["ids"]
    entries = load_split(split)
    picked = stratified_subsample(entries, n, seed=seed)
    ids = [e.bibtex_key for e in picked]
    from collections import Counter

    payload = {
        "split": split, "n": len(ids), "requested": n, "seed": seed,
        "rule": "proportional stratified over (label, hallucination_type), "
                "entries sorted by bibtex_key then shuffled with the seed",
        "ids": ids,
        "composition": {
            "label": dict(Counter(e.label for e in picked)),
            "type": dict(Counter(e.hallucination_type for e in picked if e.hallucination_type)),
            "tier": dict(Counter(str(e.difficulty_tier) for e in picked if e.difficulty_tier)),
            "generation_method": dict(Counter(e.generation_method for e in picked)),
        },
    }
    write_json(path, payload)
    return ids


def subset_entries(split: str, ids: list[str]) -> list:
    wanted = set(ids)
    entries = load_split(split)
    by_key = {e.bibtex_key: e for e in entries}
    missing = wanted - set(by_key)
    if missing:
        raise KeyError(f"{len(missing)} sampled ids are not in {split}: {sorted(missing)[:5]}")
    # Preserve the frozen sample order.
    return [by_key[k] for k in ids]


def run_zeroshot(split: str, model: str, n: int, workers: int = 4, force: bool = False) -> dict:
    from hallmark.baselines.concurrency import parallel_run_baseline

    cfg = configure_environment(LLMConfig(model=model))
    tag = f"llm_zeroshot_{cfg.slug}"
    ids = fixed_sample(split, n)
    entries = subset_entries(split, ids)
    ckpt = CKPT_DIR / f"{tag}__{split}_{n}"
    ckpt.mkdir(parents=True, exist_ok=True)

    if not force and metrics_path(tag, f"{split}_{n}").exists():
        log("skip %s (already scored)", tag)
        from hallmark_repro.common import load_predictions

        return load_predictions(tag, f"{split}_{n}")

    log("zeroshot %s on %d sampled entries of %s", cfg.model, len(entries), split)
    t0 = time.time()
    predictions = parallel_run_baseline(
        "llm_openai", entries, workers=workers, checkpoint_dir=ckpt, split=split,
        progress_every=20, model=cfg.model, api_key=cfg.api_key,
        max_completion_tokens=MAX_COMPLETION_TOKENS,
    )
    elapsed = time.time() - t0
    log("zeroshot done in %.1fs", elapsed)

    save_predictions(predictions, tag, f"{split}_{n}")
    res = score(entries, predictions, tag, f"{split}_{n}", eval_mode="conservative",
                extra={"mode": "zeroshot", "model": cfg.model, "base_url": cfg.base_url,
                       "sample_size": len(ids), "sample_seed": 20261018,
                       "wall_clock_seconds": round(elapsed, 2), "workers": workers,
                       "max_completion_tokens": MAX_COMPLETION_TOKENS})
    log("  DR=%.3f FPR=%.3f F1=%.3f tierW=%.3f cov=%.3f uncertain=%d",
        res["detection_rate"], res["false_positive_rate"] or 0.0, res["f1_hallucination"],
        res["tier_weighted_f1"], res.get("coverage", 0), res.get("num_uncertain", 0))
    return predictions


def run_agentic(split: str, model: str, n: int, workers: int = 4, force: bool = False) -> dict:
    from hallmark.baselines.concurrency import parallel_run_baseline

    cfg = configure_environment(LLMConfig(model=model))
    tag = f"llm_agentic_{cfg.slug}"
    ids = fixed_sample(split, n)
    entries = subset_entries(split, ids)
    ckpt = CKPT_DIR / f"{tag}__{split}_{n}"
    ckpt.mkdir(parents=True, exist_ok=True)

    if not force and metrics_path(tag, f"{split}_{n}").exists():
        log("skip %s (already scored)", tag)
        from hallmark_repro.common import load_predictions

        return load_predictions(tag, f"{split}_{n}")

    log("agentic %s on %d sampled entries of %s", cfg.model, len(entries), split)
    t0 = time.time()
    predictions = parallel_run_baseline(
        "llm_agentic_openai", entries, workers=workers, checkpoint_dir=ckpt, split=split,
        progress_every=10, model=cfg.model, api_key=cfg.api_key,
        max_completion_tokens=MAX_COMPLETION_TOKENS,
    )
    elapsed = time.time() - t0
    log("agentic done in %.1fs", elapsed)

    save_predictions(predictions, tag, f"{split}_{n}")
    res = score(entries, predictions, tag, f"{split}_{n}", eval_mode="conservative",
                extra={"mode": "agentic", "model": cfg.model, "base_url": cfg.base_url,
                       "sample_size": len(ids), "sample_seed": 20261018,
                       "wall_clock_seconds": round(elapsed, 2), "workers": workers,
                       "max_completion_tokens": MAX_COMPLETION_TOKENS})
    log("  DR=%.3f FPR=%.3f F1=%.3f tierW=%.3f cov=%.3f uncertain=%d api_calls=%.1f",
        res["detection_rate"], res["false_positive_rate"] or 0.0, res["f1_hallucination"],
        res["tier_weighted_f1"], res.get("coverage", 0), res.get("num_uncertain", 0),
        res.get("mean_api_calls", 0))
    return predictions


def main() -> None:
    ap = argparse.ArgumentParser(description="LLM baselines under a substituted model")
    ap.add_argument("--mode", choices=["zeroshot", "agentic"], required=True)
    ap.add_argument("--model", default="deepseek-v4.1-flash")
    ap.add_argument("--split", default="test_public", choices=SPLITS)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if args.mode == "zeroshot":
        run_zeroshot(args.split, args.model, args.n, args.workers, args.force)
    else:
        run_agentic(args.split, args.model, args.n, args.workers, args.force)


if __name__ == "__main__":
    main()
