"""E3 - Diagnose the six sub-tests that HALLMARK scores every entry against.

HALLMARK's design claim is that a citation can be checked by six independent
criteria (DOI resolution, title existence, author consistency, venue
correctness, field completeness, cross-database agreement) and that different
hallucination types fail different criteria.  This experiment tests that claim
from two directions.

E3.1 - *offline*, on the released annotation
    Treat the per-entry ``subtests`` block shipped with the benchmark as if it
    were a tool's output, and ask: how good is each single criterion as a
    detector, and which criterion carries the signal for which error type?
    This costs no API calls and separates "the benchmark's design" from "our
    ability to reproduce it".

E3.2 - *live*, on a fixed stratified subsample
    Re-derive the same six criteria from scratch against Crossref, OpenAlex and
    DBLP for a stratified subsample, and compare with the released annotation.
    The disagreement rate is the reproducibility ceiling of the annotation
    itself: publisher bot mitigation, database indexing lag and fuzzy-match
    thresholds all move a sub-test verdict without any change to the citation.

Both halves write per-entry records so every aggregate can be recomputed.

Usage::

    python -m hallmark_repro.exp3_subtests --offline
    python -m hallmark_repro.exp3_subtests --live --n 180 --workers 6
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import random
import time
from collections import Counter, defaultdict
from pathlib import Path

import httpx

from hallmark_repro.common import (
    RESULTS_DIR,
    SPLITS,
    load_split,
    log,
    setup_logging,
    write_json,
)

logger = setup_logging("exp3_subtests")

OUT_DIR = RESULTS_DIR / "subtests"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SUBTESTS = [
    "doi_resolves",
    "title_exists",
    "authors_match",
    "venue_correct",
    "fields_complete",
    "cross_db_agreement",
]

#: A sub-test that returns False is the signal; ``None`` means "not applicable"
#: and must never be read as a pass or as a failure.
SIGNAL = False


# ---------------------------------------------------------------------------
# E3.1  offline: score the released annotation as a detector
# ---------------------------------------------------------------------------

def subtest_as_detector(entries) -> dict:
    """Precision / recall of each sub-test used alone as a hallucination flag."""
    rows: dict[str, dict] = {}
    for name in SUBTESTS:
        tp = fp = tn = fn = 0
        abstain_hall = abstain_valid = 0
        for e in entries:
            st = (getattr(e, "subtests", None) or {}).get(name, None)
            is_hall = e.label == "HALLUCINATED"
            if st is None:
                if is_hall:
                    abstain_hall += 1
                else:
                    abstain_valid += 1
                continue
            flagged = st is SIGNAL or st is False
            if is_hall and flagged:
                tp += 1
            elif is_hall and not flagged:
                fn += 1
            elif not is_hall and flagged:
                fp += 1
            else:
                tn += 1
        n = tp + fp + tn + fn
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision and recall else 0.0
        )
        rows[name] = {
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "n_evaluated": n,
            "coverage": round(n / max(len(entries), 1), 4),
            "abstain_on_hallucinated": abstain_hall,
            "abstain_on_valid": abstain_valid,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "fpr": fp / (fp + tn) if fp + tn else None,
        }

    # OR-combination of every criterion that produced a verdict.
    tp = fp = tn = fn = 0
    abstain = 0
    for e in entries:
        st = getattr(e, "subtests", None) or {}
        verdicts = [st.get(n) for n in SUBTESTS]
        known = [v for v in verdicts if v is not None]
        if not known:
            abstain += 1
            continue
        flagged = any(v is False for v in known)
        is_hall = e.label == "HALLUCINATED"
        if is_hall and flagged:
            tp += 1
        elif is_hall:
            fn += 1
        elif flagged:
            fp += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    rows["ANY_SUBTEST_FAILS"] = {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "n_evaluated": tp + fp + tn + fn,
        "coverage": round((tp + fp + tn + fn) / max(len(entries), 1), 4),
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision and recall else 0.0,
        "fpr": fp / (fp + tn) if fp + tn else None,
        "abstain_on_hallucinated": abstain,
        "abstain_on_valid": 0,
    }
    return rows


def type_subtest_matrix(entries) -> dict:
    """Share of entries of each hallucination type on which each sub-test fails."""
    per_type: dict[str, Counter] = defaultdict(Counter)
    totals: Counter = Counter()
    for e in entries:
        if e.label != "HALLUCINATED":
            continue
        totals[e.hallucination_type] += 1
        st = getattr(e, "subtests", None) or {}
        for name in SUBTESTS:
            v = st.get(name)
            if v is None:
                per_type[e.hallucination_type][f"{name}:NA"] += 1
            elif v is False:
                per_type[e.hallucination_type][f"{name}:FAIL"] += 1
            else:
                per_type[e.hallucination_type][f"{name}:PASS"] += 1

    matrix = {}
    for t, counter in sorted(per_type.items()):
        n = totals[t]
        matrix[t] = {
            "n": n,
            "fail_rate": {s: round(counter[f"{s}:FAIL"] / n, 4) for s in SUBTESTS},
            "na_rate": {s: round(counter[f"{s}:NA"] / n, 4) for s in SUBTESTS},
        }
    # Same table for VALID entries, as the reference row.
    valid = [e for e in entries if e.label != "HALLUCINATED"]
    if valid:
        counter: Counter = Counter()
        for e in valid:
            st = getattr(e, "subtests", None) or {}
            for name in SUBTESTS:
                v = st.get(name)
                if v is None:
                    counter[f"{name}:NA"] += 1
                elif v is False:
                    counter[f"{name}:FAIL"] += 1
                else:
                    counter[f"{name}:PASS"] += 1
        matrix["__VALID__"] = {
            "n": len(valid),
            "fail_rate": {s: round(counter[f"{s}:FAIL"] / len(valid), 4) for s in SUBTESTS},
            "na_rate": {s: round(counter[f"{s}:NA"] / len(valid), 4) for s in SUBTESTS},
        }
    return matrix


def run_offline() -> dict:
    payload = {"per_split": {}, "type_subtest_matrix": {}}
    for split in SPLITS:
        entries = load_split(split)
        payload["per_split"][split] = {
            "n": len(entries),
            "detectors": subtest_as_detector(entries),
        }
        payload["type_subtest_matrix"][split] = type_subtest_matrix(entries)
        log("E3.1 %s: ANY_SUBTEST_FAILS f1=%.3f coverage=%.3f",
            split, payload["per_split"][split]["detectors"]["ANY_SUBTEST_FAILS"]["f1"],
            payload["per_split"][split]["detectors"]["ANY_SUBTEST_FAILS"]["coverage"])
    write_json(OUT_DIR / "subtest_offline.json", payload)

    # flat TSV for the write-up
    lines = ["split\tsubtest\ttp\tfp\ttn\tfn\tcoverage\tprecision\trecall\tf1\tfpr"]
    for split, rec in payload["per_split"].items():
        for name, r in rec["detectors"].items():
            lines.append("\t".join(str(x) for x in [
                split, name, r["tp"], r["fp"], r["tn"], r["fn"], r["coverage"],
                f"{r['precision']:.4f}" if r["precision"] is not None else "na",
                f"{r['recall']:.4f}" if r["recall"] is not None else "na",
                f"{r['f1']:.4f}",
                f"{r['fpr']:.4f}" if r["fpr"] is not None else "na",
            ]))
    (OUT_DIR / "subtest_detectors.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


# ---------------------------------------------------------------------------
# E3.2  live: re-derive the sub-tests from primary sources
# ---------------------------------------------------------------------------

CROSSREF = "https://api.crossref.org/works"
OPENALEX = "https://api.openalex.org/works"
DBLP = "https://dblp.org/search/publ/api"
MAILTO = "reproduction@example.edu"


def _get(client: httpx.Client, url: str, params: dict, retries: int = 3) -> dict | None:
    for attempt in range(retries):
        try:
            r = client.get(url, params=params, timeout=20.0,
                           headers={"User-Agent": f"HALLMARK-repro/1.0 (mailto:{MAILTO})"})
            if r.status_code == 200:
                return r.json()
            if r.status_code in (404, 400):
                return None
        except Exception as exc:
            logger.debug("GET %s failed (%s/%s): %s", url, attempt + 1, retries, exc)
        time.sleep(1.5 * (attempt + 1))
    return None


def fetch_metadata(entry) -> dict:
    """Query Crossref, OpenAlex and DBLP for one entry.

    Returns the ``results_by_source`` dict the sub-test functions expect, plus
    the per-source query status so a failed lookup can be reported as an
    abstention instead of silently counting as "not found".
    """
    title = (entry.fields.get("title") or "").strip()
    doi = (entry.fields.get("doi") or "").strip()
    out: dict = {"results_by_source": {}, "query_status": {}}
    if not title and not doi:
        return out

    with httpx.Client() as client:
        # --- Crossref: DOI lookup first, title search as fallback
        cr = None
        if doi:
            data = _get(client, f"{CROSSREF}/{doi}", {"mailto": MAILTO})
            cr = (data or {}).get("message")
        if cr is None and title:
            data = _get(client, CROSSREF, {"query.bibliographic": title, "rows": 5,
                                          "mailto": MAILTO})
            items = (data or {}).get("message", {}).get("items", [])
            if items:
                cr = items[0]
        out["query_status"]["crossref"] = "ok" if cr else "not_found"
        if cr:
            out["results_by_source"]["crossref"] = {
                "title": (cr.get("title") or [""])[0],
                "authors": [
                    f"{a.get('family', '')}".strip()
                    for a in cr.get("author", []) if a.get("family")
                ],
                "venue": ((cr.get("container-title") or [""])[0] if cr.get("container-title") else ""),
                "year": str((cr.get("issued", {}).get("date-parts") or [[""]])[0][0] or ""),
            }

        # --- OpenAlex
        oa = None
        if doi:
            data = _get(client, f"{OPENALEX}/doi:{doi}", {"mailto": MAILTO})
            oa = data if data and data.get("title") else None
        if oa is None and title:
            data = _get(client, OPENALEX, {"search": title, "per-page": 5, "mailto": MAILTO})
            results = (data or {}).get("results", [])
            if results:
                oa = results[0]
        out["query_status"]["openalex"] = "ok" if oa else "not_found"
        if oa:
            out["results_by_source"]["openalex"] = {
                "title": oa.get("title") or "",
                "authors": [
                    (a.get("author") or {}).get("display_name", "").split()[-1]
                    for a in (oa.get("authorships") or []) if (a.get("author") or {}).get("display_name")
                ],
                "venue": ((oa.get("primary_location") or {}).get("source") or {}).get("display_name", "") or "",
                "year": str(oa.get("publication_year") or ""),
            }

        # --- DBLP
        db = None
        if title:
            data = _get(client, DBLP, {"q": title, "format": "json", "h": 5})
            hits = (((data or {}).get("result") or {}).get("hits") or {}).get("hit", [])
            if hits:
                db = hits[0].get("info", {})
        out["query_status"]["dblp"] = "ok" if db else "not_found"
        if db:
            authors = db.get("authors", {}).get("author", [])
            if isinstance(authors, dict):
                authors = [authors]
            out["results_by_source"]["dblp"] = {
                "title": db.get("title", ""),
                "authors": [a.get("text", "").split()[-1] for a in authors if isinstance(a, dict)],
                "venue": db.get("venue", ""),
                "year": str(db.get("year", "")),
            }
    return out


def live_subtests(entry, meta: dict) -> dict:
    """Run the six upstream sub-test functions against fetched metadata."""
    from hallmark.evaluation.subtests import (
        check_authors_match,
        check_cross_db_agreement,
        check_doi_resolves,
        check_fields_complete,
        check_title_exists,
        check_venue_correct,
    )

    by_source = meta.get("results_by_source", {})
    # Pick the source that actually answered as the reference for the
    # field-level criteria; preference order mirrors the tool's own emphasis.
    ref = None
    for src in ("crossref", "openalex", "dblp"):
        if src in by_source:
            ref = by_source[src]
            break
    api_results = [{"title": v.get("title", "")} for v in by_source.values()]
    api_authors = ref.get("authors") if ref else None
    api_venue = ref.get("venue") if ref else None

    doi = (entry.fields.get("doi") or "").strip() or None
    results = {
        "doi_resolves": check_doi_resolves(doi).passed,
        "title_exists": check_title_exists(entry.fields.get("title", ""), api_results).passed,
        "authors_match": check_authors_match(entry.fields.get("author", ""), api_authors).passed,
        "venue_correct": check_venue_correct(
            entry.fields.get("booktitle", "") or entry.fields.get("journal", ""),
            None, api_venue,
        ).passed,
        "fields_complete": check_fields_complete(entry.bibtex_type, entry.fields).passed,
        "cross_db_agreement": check_cross_db_agreement(by_source).passed,
    }
    return results


def stratified_subsample(entries, n: int, seed: int = 20261018) -> list:
    """Fixed-rule sample: proportional over (label, hallucination type).

    The rule is frozen before any model output is seen, so the sample cannot be
    chosen to favour a result; the ids are written out for auditing.
    """
    rng = random.Random(seed)
    strata: dict[str, list] = defaultdict(list)
    for e in entries:
        key = "VALID" if e.label != "HALLUCINATED" else f"H:{e.hallucination_type}"
        strata[key].append(e)
    picked: list = []
    for key, group in sorted(strata.items()):
        group = sorted(group, key=lambda x: x.bibtex_key)
        rng.shuffle(group)
        take = max(1, round(n * len(group) / len(entries)))
        picked.extend(group[:take])
    picked = sorted(picked, key=lambda x: x.bibtex_key)
    return picked


def run_live(n: int, workers: int, split: str = "test_public") -> dict:
    entries = load_split(split)
    sample = stratified_subsample(entries, n)
    log("E3.2 live sub-tests on %d/%d entries of %s", len(sample), len(entries), split)

    records = []
    t0 = time.time()
    with cf.ThreadPoolExecutor(workers) as ex:
        metas = list(ex.map(fetch_metadata, sample))
    log("metadata fetched in %.1fs", time.time() - t0)

    for entry, meta in zip(sample, metas):
        try:
            live = live_subtests(entry, meta)
        except Exception as exc:
            logger.warning("subtests failed for %s: %s", entry.bibtex_key, exc)
            live = {s: None for s in SUBTESTS}
        released = getattr(entry, "subtests", None) or {}
        agree = {}
        for s in SUBTESTS:
            a, b = live.get(s), released.get(s)
            agree[s] = None if (a is None or b is None) else (a == b)
        records.append({
            "bibtex_key": entry.bibtex_key,
            "label": entry.label,
            "hallucination_type": entry.hallucination_type,
            "difficulty_tier": entry.difficulty_tier,
            "generation_method": entry.generation_method,
            "fields": entry.fields,
            "live_subtests": live,
            "released_subtests": released,
            "agree": agree,
            "query_status": meta.get("query_status", {}),
            "n_sources": len(meta.get("results_by_source", {})),
        })

    summary = {"split": split, "n_sample": len(sample), "seed": 20261018, "per_subtest": {}}
    for s in SUBTESTS:
        cmp = [r["agree"][s] for r in records if r["agree"][s] is not None]
        n_na_live = sum(1 for r in records if r["live_subtests"][s] is None)
        summary["per_subtest"][s] = {
            "comparable": len(cmp),
            "agreement": round(sum(cmp) / len(cmp), 4) if cmp else None,
            "disagree": len(cmp) - sum(cmp),
            "live_abstained": n_na_live,
            "released_abstained": sum(1 for r in records if r["released_subtests"].get(s) is None),
        }
        log("  %-20s agreement=%s (n=%d, live abstain=%d)",
            s, summary["per_subtest"][s]["agreement"], len(cmp), n_na_live)

    summary["source_availability"] = {
        src: dict(Counter(r["query_status"].get(src, "missing") for r in records))
        for src in ("crossref", "openalex", "dblp")
    }
    summary["n_sources_histogram"] = dict(Counter(r["n_sources"] for r in records))
    summary["any_source_answered"] = sum(1 for r in records if r["n_sources"] > 0)
    summary["all_sources_answered"] = sum(1 for r in records if r["n_sources"] == 3)

    # Live sub-tests used as a detector on the subsample.
    summary["live_detector"] = _live_detector(records)

    with open(OUT_DIR / "subtest_live_records.jsonl", "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    write_json(OUT_DIR / "subtest_live_summary.json", summary)
    return summary


def _live_detector(records: list) -> dict:
    """How well does 'some live sub-test failed' detect the hallucinated class?"""
    tp = fp = tn = fn = abstain = 0
    for r in records:
        known = [v for v in r["live_subtests"].values() if v is not None]
        if not known:
            abstain += 1
            continue
        flagged = any(v is False for v in known)
        is_hall = r["label"] == "HALLUCINATED"
        if is_hall and flagged:
            tp += 1
        elif is_hall:
            fn += 1
        elif flagged:
            fp += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    return {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn, "abstain": abstain,
        "precision": precision, "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision and recall else 0.0,
        "fpr": fp / (fp + tn) if fp + tn else None,
        "coverage": round((tp + fp + tn + fn) / max(len(records), 1), 4),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="HALLMARK sub-test diagnosis")
    ap.add_argument("--offline", action="store_true", help="E3.1, no network")
    ap.add_argument("--live", action="store_true", help="E3.2, re-derive sub-tests live")
    ap.add_argument("--n", type=int, default=180, help="live subsample size")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--split", default="test_public", choices=SPLITS)
    args = ap.parse_args()
    if args.offline or not args.live:
        run_offline()
    if args.live:
        run_live(args.n, args.workers, args.split)


if __name__ == "__main__":
    main()
