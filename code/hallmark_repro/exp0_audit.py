"""E0 - Dataset audit of the HALLMARK release used in this reproduction.

The paper's headline claims are made about a specific frozen revision
(v1.2.4, built 2026-10-15).  Before scoring anything we audit the released
files themselves, because the upstream README warns that statistics differ
between locations in the repository and that an earlier HF mirror was
withdrawn.

Outputs ``results/audit/dataset_audit.json`` plus several CSV tables under
``results/audit/``.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from hallmark_repro.common import (
    DATA_VERSION,
    REFERENCE_YEAR,
    REPO_ROOT,
    RESULTS_DIR,
    SPLITS,
    data_file,
    environment_record,
    load_split,
    log,
    sha256_file,
    write_json,
)

AUDIT_DIR = RESULTS_DIR / "audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

SUBTESTS = [
    "doi_resolves",
    "title_exists",
    "authors_match",
    "venue_correct",
    "fields_complete",
    "cross_db_agreement",
]

#: Fields that would leak the answer if handed to a verifier as input.
LEAK_RISK_FIELDS = [
    "label",
    "hallucination_type",
    "difficulty_tier",
    "explanation",
    "generation_method",
    "source",
    "source_conference",
    "subtests",
    "raw_bibtex",
]


def _field_completeness(entries) -> dict[str, dict[str, float]]:
    """Fraction of entries carrying each BibTeX field, per label group."""
    groups: dict[str, Counter] = defaultdict(Counter)
    totals: Counter = Counter()
    for e in entries:
        grp = "HALLUCINATED" if e.label == "HALLUCINATED" else "VALID"
        totals[grp] += 1
        totals["ALL"] += 1
        for f in e.fields:
            groups[grp][f] += 1
            groups["ALL"][f] += 1
    out = {}
    for grp, counter in groups.items():
        out[grp] = {f: round(c / totals[grp], 4) for f, c in sorted(counter.items())}
    return out


def _subtest_stats(entries) -> dict:
    stats: dict[str, dict[str, int]] = {s: Counter() for s in SUBTESTS}
    present = 0
    for e in entries:
        st = getattr(e, "subtests", None) or {}
        if st:
            present += 1
        for s in SUBTESTS:
            v = st.get(s, "MISSING")
            stats[s][str(v)] += 1
    return {
        "entries_with_subtests": present,
        "coverage": round(present / max(len(entries), 1), 4),
        "values": {s: dict(c) for s, c in stats.items()},
    }


def _subtest_by_type(entries) -> dict:
    """Which sub-test is 'supposed' to fail for each hallucination type."""
    table: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(Counter))
    for e in entries:
        if e.label != "HALLUCINATED":
            continue
        st = getattr(e, "subtests", None) or {}
        for s in SUBTESTS:
            table[e.hallucination_type][s][str(st.get(s, "MISSING"))] += 1
    return {t: {s: dict(c) for s, c in v.items()} for t, v in table.items()}


def audit_split(split: str) -> dict:
    entries = load_split(split)
    path = data_file(split)

    tiers = Counter(e.difficulty_tier for e in entries if e.label == "HALLUCINATED")
    types = Counter(e.hallucination_type for e in entries if e.label == "HALLUCINATED")
    gens = Counter(e.generation_method for e in entries)
    gens_hall = Counter(e.generation_method for e in entries if e.label == "HALLUCINATED")
    gens_val = Counter(e.generation_method for e in entries if e.label != "HALLUCINATED")
    sources = Counter(e.source for e in entries)
    dates = Counter(str(e.publication_date)[:7] for e in entries)

    record = {
        "split": split,
        "file": str(path.relative_to(REPO_ROOT)),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "n_entries": len(entries),
        "n_valid": sum(1 for e in entries if e.label != "HALLUCINATED"),
        "n_hallucinated": sum(1 for e in entries if e.label == "HALLUCINATED"),
        "label_values": dict(Counter(e.label for e in entries)),
        "tier_distribution": {str(k): v for k, v in sorted(tiers.items())},
        "type_distribution": dict(sorted(types.items())),
        "generation_method_distribution": dict(sorted(gens.items())),
        "generation_method_hallucinated": dict(sorted(gens_hall.items())),
        "generation_method_valid": dict(sorted(gens_val.items())),
        "source_distribution": {
            str(k): v for k, v in sorted(sources.items(), key=lambda kv: str(kv[0]))
        },
        "publication_date_months": dict(sorted(dates.items())),
        "bibtex_types": dict(sorted(Counter(e.bibtex_type for e in entries).items())),
        "field_completeness": _field_completeness(entries),
        "subtests": _subtest_stats(entries),
        "subtests_by_type": _subtest_by_type(entries),
        "has_raw_bibtex": sum(1 for e in entries if e.raw_bibtex),
    }
    # Sanity: every hallucinated entry must carry a type and a tier.
    record["integrity"] = {
        "hallucinated_missing_type": sum(
            1 for e in entries if e.label == "HALLUCINATED" and not e.hallucination_type
        ),
        "hallucinated_missing_tier": sum(
            1 for e in entries if e.label == "HALLUCINATED" and not e.difficulty_tier
        ),
        "valid_with_type": sum(
            1 for e in entries if e.label != "HALLUCINATED" and e.hallucination_type
        ),
        "empty_title": sum(1 for e in entries if not e.fields.get("title")),
        "empty_author": sum(1 for e in entries if not e.fields.get("author")),
        "has_doi": sum(1 for e in entries if e.fields.get("doi")),
        "future_dated": sum(
            1 for e in entries
            if (e.fields.get("year") or "0").isdigit() and int(e.fields.get("year") or 0) > REFERENCE_YEAR
        ),
    }
    return record


def cross_split_leakage(records: dict[str, dict]) -> dict:
    """Overlap of bibtex_key and of title between splits.

    Identical titles appearing in two splits would make a title-based oracle
    look better than it is; the upstream repo ships such oracles for diagnosis,
    so we quantify the overlap rather than assume it away.
    """
    titles: dict[str, dict[str, str]] = {}
    keys: dict[str, set[str]] = {}
    for split in records:
        entries = load_split(split)
        titles[split] = {}
        for e in entries:
            t = (e.fields.get("title") or "").strip().lower()
            titles[split][e.bibtex_key] = t
        keys[split] = set(e.bibtex_key for e in entries)

    out: dict[str, dict] = {}
    names = sorted(records)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            shared_keys = keys[a] & keys[b]
            ta = Counter(t for t in titles[a].values() if t)
            tb = Counter(t for t in titles[b].values() if t)
            shared_titles = set(ta) & set(tb)
            out[f"{a}|{b}"] = {
                "shared_bibtex_keys": len(shared_keys),
                "examples_keys": sorted(shared_keys)[:5],
                "shared_normalized_titles": len(shared_titles),
                "examples_titles": sorted(shared_titles)[:5],
            }
    return out


def main() -> None:
    log("E0 dataset audit, version=%s", DATA_VERSION)
    records = {}
    for split in SPLITS:
        rec = audit_split(split)
        records[split] = rec
        log(
            "  %-12s n=%4d valid=%4d hall=%4d tiers=%s",
            split,
            rec["n_entries"],
            rec["n_valid"],
            rec["n_hallucinated"],
            rec["tier_distribution"],
        )

    payload = {
        "environment": environment_record(),
        "data_version": DATA_VERSION,
        "reference_year": REFERENCE_YEAR,
        "splits": records,
        "cross_split_overlap": cross_split_leakage(records),
        "leak_risk_fields_present_in_benchmark_file": LEAK_RISK_FIELDS,
    }
    write_json(AUDIT_DIR / "dataset_audit.json", payload)

    # ---- flat tables for the write-up -------------------------------------
    lines = ["split\tn_entries\tn_valid\tn_hallucinated\thallucination_rate"]
    for split, rec in records.items():
        lines.append(
            f"{split}\t{rec['n_entries']}\t{rec['n_valid']}\t{rec['n_hallucinated']}\t"
            f"{rec['n_hallucinated'] / rec['n_entries']:.4f}"
        )
    (AUDIT_DIR / "split_summary.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    types = sorted({t for rec in records.values() for t in rec["type_distribution"]})
    lines = ["hallucination_type\t" + "\t".join(SPLITS)]
    for t in types:
        lines.append(t + "\t" + "\t".join(str(records[s]["type_distribution"].get(t, 0)) for s in SPLITS))
    (AUDIT_DIR / "type_distribution.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    lines = ["generation_method\t" + "\t".join(SPLITS)]
    for g in sorted({g for rec in records.values() for g in rec["generation_method_distribution"]}):
        lines.append(
            g + "\t" + "\t".join(
                str(records[s]["generation_method_distribution"].get(g, 0)) for s in SPLITS
            )
        )
    (AUDIT_DIR / "generation_method_distribution.tsv").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    log("E0 written to %s", AUDIT_DIR)


if __name__ == "__main__":
    main()
