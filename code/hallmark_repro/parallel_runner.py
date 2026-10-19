"""A small, fault-tolerant parallel runner for HALLMARK baselines.

The upstream ``parallel_run_baseline`` fans out through
``registry.run_baseline(name, [entry])`` and lets an exception from any single
entry propagate out of ``ThreadPoolExecutor.map``, which aborts the whole split.
On the network used for this reproduction that happened repeatedly: the
connection to doi.org is reset in bursts, ``retry_with_backoff`` exhausts its
three attempts, and one dead entry takes 1,100 live ones with it.

This runner keeps the same per-entry contract but adds three things the
experiment needs:

* **per-entry error isolation** - a failed entry is recorded as an abstention
  (``UNCERTAIN``, ``evaluated=False``) and the run continues.  The assignment
  requires failures to be reported rather than silently dropped, so they are
  written to the prediction file and counted by the scorer.
* **durable checkpointing** - every finished entry is appended to a JSONL file
  immediately, so an interrupted run resumes instead of restarting.
* **bounded retries at the entry level** - a transient burst is retried a few
  times before the entry is written off.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from hallmark_repro.common import log

_LOCK = threading.Lock()


def _load_done(path: Path) -> dict[str, dict]:
    done: dict[str, dict] = {}
    if not path.exists():
        return done
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            done[rec["bibtex_key"]] = rec
    return done


def _append(path: Path, payload: dict) -> None:
    with _LOCK, open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        f.flush()


def run_parallel(
    name: str,
    entries: Sequence,
    *,
    workers: int,
    checkpoint_path: Path,
    split: str | None = None,
    retries: int = 3,
    retry_backoff: float = 3.0,
    progress_every: int = 25,
    **kwargs,
):
    """Run ``name`` over ``entries`` with ``workers`` threads.

    Args:
        name: registered baseline name.
        entries: benchmark entries (labels are hidden before dispatch).
        workers: concurrent threads.
        checkpoint_path: JSONL file for per-entry resume.
        split: forwarded to the baseline runner.
        retries: how many times a failing entry is retried.
        retry_backoff: seconds between entry-level retries, doubled each time.
        **kwargs: forwarded to the baseline runner.
    """
    from hallmark.baselines import registry
    from hallmark.dataset.schema import Prediction

    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    done = _load_done(checkpoint_path)
    todo = [e for e in entries if e.bibtex_key not in done]
    log("%s: %d/%d entries to run (%d resumed from checkpoint)",
        name, len(todo), len(entries), len(done))

    if not todo:
        return [Prediction.from_dict(v) for v in done.values()]

    counter = {"n": 0}
    t_start = time.time()

    def one(entry):
        # ``registry.run_baseline`` hides the labels itself (``_to_blind``), so
        # handing it a BenchmarkEntry is the documented contract.
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                preds = registry.run_baseline(name, [entry], split=split, **kwargs)
                if not preds:
                    raise RuntimeError("baseline returned no prediction")
                return preds[0]
            except Exception as exc:                       # noqa: BLE001 - by design
                last_exc = exc
                if attempt < retries:
                    time.sleep(retry_backoff * (2 ** attempt))
        # Every attempt failed: record an abstention, never a guess.
        log("  entry %s failed after %d attempts: %s: %s",
            entry.bibtex_key, retries + 1, type(last_exc).__name__, str(last_exc)[:120])
        return Prediction(
            bibtex_key=entry.bibtex_key,
            label="UNCERTAIN",
            confidence=0.5,
            reason=f"[harness error] {type(last_exc).__name__}: {str(last_exc)[:200]}",
            evaluated=False,
        )

    if workers <= 1:
        for entry in todo:
            pred = one(entry)
            _append(checkpoint_path, pred.to_dict())
            done[entry.bibtex_key] = pred.to_dict()
            counter["n"] += 1
            if counter["n"] % progress_every == 0:
                _progress(name, counter["n"], len(todo), t_start)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(one, e): e for e in todo}
            for fut in as_completed(futures):
                entry = futures[fut]
                try:
                    pred = fut.result()
                except Exception as exc:                   # pragma: no cover
                    pred = Prediction(
                        bibtex_key=entry.bibtex_key, label="UNCERTAIN", confidence=0.5,
                        reason=f"[harness error] {type(exc).__name__}", evaluated=False,
                    )
                _append(checkpoint_path, pred.to_dict())
                done[entry.bibtex_key] = pred.to_dict()
                counter["n"] += 1
                if counter["n"] % progress_every == 0:
                    _progress(name, counter["n"], len(todo), t_start)

    log("%s: %d entries finished in %.1fs", name, counter["n"], time.time() - t_start)
    # Preserve the benchmark order so downstream scoring is deterministic.
    order = [e.bibtex_key for e in entries]
    return [Prediction.from_dict(done[k]) for k in order if k in done]


def _progress(name: str, n: int, total: int, t0: float) -> None:
    elapsed = time.time() - t0
    rate = n / elapsed if elapsed else 0
    eta = (total - n) / rate if rate else float("inf")
    log("  %s: %d/%d (%.1f entries/s, ETA %.0fs)", name, n, total, rate, eta)
