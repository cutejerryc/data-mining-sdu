"""Driver: run every experiment in priority order, one at a time.

The experiments are network-bound and share upstream services (CrossRef,
Semantic Scholar, DBLP), so running them concurrently mostly produces rate
limiting rather than speed-up.  This driver sequences them and appends a
one-line status for each stage, so a partial run is still readable.

Ordering rationale
------------------
1. the deterministic baselines that the reproduction claim rests on;
2. the released cascade Stage 1, which is the paper's headline architecture;
3. the live sub-test re-derivation, which bounds how reproducible the
   annotation itself is;
4. the LLM baselines, which are the most expensive and the least comparable.

Usage::

    python -m hallmark_repro.run_experiments --from exp1 --to exp4
    python -m hallmark_repro.run_experiments --only exp2
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime

from hallmark_repro.common import PROJECT_ROOT, log, setup_logging

logger = setup_logging("run_experiments")

DRIVER_LOG = PROJECT_ROOT / "logs" / "driver.log"

STAGES: dict[str, list[list[str]]] = {
    # 1. deterministic baselines (degenerate rows are already scored and skipped).
    #    The multi-source baselines run on a frozen 300-entry stratified sample:
    #    Semantic Scholar is paced at 10 requests/minute without an API key, so a
    #    full split would need roughly three hours per baseline.  The sample rule
    #    and ids are frozen in results/samples/ before any model output is seen.
    "exp1": [
        ["-m", "hallmark_repro.exp1_baselines", "hallucitechecker", "checkifexist",
         "--splits", "test_public", "--workers", "4", "--sample", "300"],
        ["-m", "hallmark_repro.exp1_baselines", "title_oracle", "venue_oracle",
         "--splits", "test_public", "dev_public"],
    ],
    # 2. released cascade Stage 1 (bibtex-check) + scoring in both stances
    "exp2": [
        ["-m", "hallmark_repro.exp2_cascade", "--stage1-only", "--split", "test_public"],
        ["-m", "hallmark_repro.exp2_cascade", "--stage1-only", "--split", "dev_public"],
    ],
    # 3. live sub-test re-derivation on a frozen stratified subsample
    "exp3": [
        ["-m", "hallmark_repro.exp3_subtests", "--live", "--n", "180", "--workers", "6",
         "--split", "test_public"],
    ],
    # 4. LLM baselines under the substituted gateway model
    "exp4": [
        ["-m", "hallmark_repro.exp4_llm", "--mode", "zeroshot", "--n", "200",
         "--model", "deepseek-v4.1-flash", "--workers", "4"],
        ["-m", "hallmark_repro.exp4_llm", "--mode", "agentic", "--n", "200",
         "--model", "deepseek-v4.1-flash", "--workers", "4"],
    ],
    # 5. ensemble (combines doi_only + bibtex-check); runs after exp2 so that
    #    bibtex-check's own disk cache makes the second pass cheap
    "exp1b": [
        ["-m", "hallmark_repro.exp1_baselines", "ensemble",
         "--splits", "test_public", "dev_public", "--workers", "4"],
    ],
    # 6. cascade Stage 2 on top of the released Stage 1
    "exp2b": [
        ["-m", "hallmark_repro.exp2_cascade", "--cascade", "--split", "test_public",
         "--model", "deepseek-v4.1-flash"],
    ],
    # 7. agreement against the released reference results
    "exp5": [
        ["-m", "hallmark_repro.exp5_compare"],
    ],
    # 8. case extraction (needs the baselines above)
    "exp6": [
        ["-m", "hallmark_repro.exp6_cases", "--split", "test_public", "--limit", "16"],
    ],
}

ORDER = ["exp1", "exp2", "exp3", "exp4", "exp1b", "exp2b", "exp5", "exp6"]


def run_stage(name: str) -> bool:
    ok = True
    for cmd in STAGES[name]:
        full = [sys.executable, "-u"] + cmd
        log("=== %s :: %s", name, " ".join(cmd))
        _append(f"[{datetime.now():%H:%M:%S}] START {name} :: {' '.join(cmd)}")
        t0 = time.time()
        proc = subprocess.run(full, cwd=str(PROJECT_ROOT / "code"))
        dt = time.time() - t0
        status = "OK" if proc.returncode == 0 else f"FAIL(rc={proc.returncode})"
        log("=== %s :: %s in %.0fs", name, status, dt)
        _append(f"[{datetime.now():%H:%M:%S}] {status} {name} in {dt:.0f}s")
        if proc.returncode != 0:
            ok = False
    return ok


def _append(line: str) -> None:
    DRIVER_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(DRIVER_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the reproduction experiment suite")
    ap.add_argument("--from", dest="start", default=ORDER[0], choices=ORDER)
    ap.add_argument("--to", dest="end", default=ORDER[-1], choices=ORDER)
    ap.add_argument("--only", nargs="*", choices=ORDER, default=None)
    args = ap.parse_args()

    stages = args.only or ORDER[ORDER.index(args.start): ORDER.index(args.end) + 1]
    log("driver: running stages %s", stages)
    for stage in stages:
        run_stage(stage)
    log("driver: all requested stages finished")


if __name__ == "__main__":
    main()
