"""E5 - Compare reproduced numbers against the reference results shipped upstream.

The upstream repository publishes the per-baseline metrics behind the paper in
``data/v1.2/baseline_results/``.  A reproduction claim is only meaningful if it
is checked against those files rather than against numbers remembered from the
paper text, so this script reads them and diffs them against our re-runs.

Three outcomes are distinguished, and the distinction is the point:

* ``reproduced``      - the same tool, same split, same scoring stance; any gap
                        is measurement noise from live APIs.
* ``adapted``         - a substituted model or service (our Stage 2 LLM, or a
                        baseline whose external source is unreachable); the
                        number is a new measurement, not a check.
* ``not attempted``   - the released row needs a service we do not have.

Usage::

    python -m hallmark_repro.exp5_compare
"""

from __future__ import annotations

import json
from pathlib import Path

from hallmark_repro.common import REPO_ROOT, RESULTS_DIR, load_metrics, log, setup_logging, write_json

logger = setup_logging("exp5_compare")

REF_DIR = REPO_ROOT / "data" / "v1.2" / "baseline_results"
OUT_DIR = RESULTS_DIR / "comparison"
OUT_DIR.mkdir(parents=True, exist_ok=True)

#: released file stem -> (our tag, stance, class)
#: ``class`` is one of reproduced / adapted / not_attempted.
PAIRS = [
    ("doi_only_dev_public", "doi_only", "conservative", "reproduced"),
    ("doi_only_test_public", "doi_only", "conservative", "reproduced"),
    ("bibtexupdater_dev_public", "bibtexupdater", "conservative", "reproduced"),
    ("bibtexupdater_test_public", "bibtexupdater", "conservative", "reproduced"),
    ("cascade_db_diagnosis_dev_public", "cascade_*", "conservative", "adapted"),
    ("cascade_db_diagnosis_test_public", "cascade_*", "conservative", "adapted"),
    ("cascade_db_diagnosis_aggressive_dev_public", "cascade_*", "aggressive", "adapted"),
    ("cascade_db_diagnosis_aggressive_test_public", "cascade_*", "aggressive", "adapted"),
]

METRICS = [
    "detection_rate", "false_positive_rate", "f1_hallucination",
    "tier_weighted_f1", "mcc", "auroc", "ece",
]


def _released(stem: str) -> dict | None:
    path = REF_DIR / f"{stem}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _ours(tag: str, split: str, stance: str) -> dict | None:
    if "*" in tag:
        # Cascade tags carry the substituted model slug; find whichever exists.
        for p in sorted((RESULTS_DIR / "metrics").glob(f"cascade_*__{split}*.json")):
            name = p.stem
            if stance == "aggressive" and "aggressive" not in name:
                continue
            if stance == "conservative" and "aggressive" in name:
                continue
            return json.loads(p.read_text(encoding="utf-8"))
        return None
    try:
        return load_metrics(tag, split, stance)
    except FileNotFoundError:
        return None


def main() -> None:
    rows = []
    for stem, tag, stance, klass in PAIRS:
        released = _released(stem)
        split = "dev_public" if "dev_public" in stem else "test_public"
        ours = _ours(tag, split, stance)
        row = {
            "released_file": stem,
            "our_tag": tag,
            "split": split,
            "stance": stance,
            "class": klass,
            "released_available": released is not None,
            "ours_available": ours is not None,
        }
        if released and ours:
            deltas = {}
            for m in METRICS:
                r, o = released.get(m), ours.get(m)
                if r is None or o is None:
                    deltas[m] = None
                else:
                    deltas[m] = {"released": round(float(r), 4), "ours": round(float(o), 4),
                                 "abs_diff": round(abs(float(o) - float(r)), 4),
                                 "rel_diff": round(abs(float(o) - float(r)) / float(r), 4)
                                 if float(r) else None}
            row["metrics"] = deltas
            row["released_run_timestamp"] = released.get("run_timestamp")
            row["released_split_sha256"] = released.get("split_sha256")
            row["our_split_sha256"] = (ours.get("_manifest") or {}).get("split_sha256")
            row["same_split_hash"] = (
                row["released_split_sha256"] is not None
                and row["released_split_sha256"] == row["our_split_sha256"]
            )
        rows.append(row)
        log("%-45s released=%s ours=%s", stem, row["released_available"], row["ours_available"])

    write_json(OUT_DIR / "reproduction_agreement.json", {"rows": rows})

    # flat table for the write-up
    lines = ["released_file\tclass\tmetric\treleased\tours\tabs_diff"]
    for row in rows:
        for m, d in (row.get("metrics") or {}).items():
            if d:
                lines.append(f"{row['released_file']}\t{row['class']}\t{m}\t"
                             f"{d['released']}\t{d['ours']}\t{d['abs_diff']}")
    (OUT_DIR / "reproduction_agreement.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log("E5 written to %s", OUT_DIR)


if __name__ == "__main__":
    main()
