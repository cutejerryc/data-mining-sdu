"""E6 - Select and describe the representative cases for the case analysis.

The assignment requires at least ten cases that between them cover the
different error sources a citation verifier runs into: parsing mistakes, entity
matching mistakes, missed evidence, ignored numbers or conditions, and wrong
support verdicts.  This script picks them mechanically from the prediction
files rather than by hand, so the selection rule is auditable and no case is
chosen because it flatters a baseline.

Selection rule
--------------
Every entry of ``test_public`` is placed in a cell of
``(outcome, hallucination_type, tier)`` for a *reference baseline*.  Outcomes are
TP / FP / TN / FN / ABSTAIN.  One case per non-empty cell is emitted, ordered by
how much explanatory value the cell has, and truncated to the requested count.
Each case carries every baseline's verdict and reason for that entry, so the
narrative in the paper can compare systems on the same citation.

Outputs
-------
``results/cases/cases.json``   machine-readable, with full field values
``results/cases/cases.md``     the same content laid out for reading
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from hallmark_repro.common import RESULTS_DIR, load_split, log, setup_logging, write_json

logger = setup_logging("exp6_cases")

OUT_DIR = RESULTS_DIR / "cases"
OUT_DIR.mkdir(parents=True, exist_ok=True)

#: Baselines quoted side by side for every case.
REFERENCE_BASELINES = [
    "doi_presence_heuristic",
    "doi_only",
    "hallucitechecker",
    # ``checkifexist`` is deliberately absent: in this environment its fallback
    # sources (Semantic Scholar, OpenAlex) both returned 429 and it degraded to
    # labelling every entry HALLUCINATED.  Including it would put a row of
    # identical verdicts in every case without carrying information about the
    # method.
    "bibtexupdater",
]

#: Cells ordered by how much they explain.  A cell is
#: ``(outcome, hallucination_type_or_ANY, tier_or_ANY)``.
PRIORITY_CELLS = [
    ("FN", "plausible_fabrication", 3),
    ("FP", "ANY", None),
    ("FN", "near_miss_title", 3),
    ("TP", "hybrid_fabrication", 2),
    ("FN", "hybrid_fabrication", 2),
    ("TP", "fabricated_doi", 1),
    ("FN", "fabricated_doi", 1),
    ("TP", "chimeric_title", 2),
    ("FN", "chimeric_title", 2),
    ("TP", "wrong_venue", 2),
    ("FN", "wrong_venue", 2),
    ("TP", "preprint_as_published", 2),
    ("FN", "preprint_as_published", 2),
    ("TP", "swapped_authors", 2),
    ("FN", "swapped_authors", 2),
    ("TP", "nonexistent_venue", 1),
    ("FN", "nonexistent_venue", 1),
    ("TP", "future_date", 1),
    ("TP", "placeholder_authors", 1),
    ("ABSTAIN", "ANY", None),
    ("TP", "merged_citation", 2),
    ("TP", "partial_author_list", 2),
    ("TP", "arxiv_version_mismatch", 3),
    ("TN", "ANY", None),
]


def load_all_predictions(split: str, sample_sizes: tuple[int, ...] = (300, 200)) -> dict[str, dict[str, dict]]:
    """tag -> bibtex_key -> prediction dict, for every baseline we have.

    A baseline may have been run on the full split or on a frozen subsample;
    both are accepted, and the subsample file is preferred when the full-split
    file is absent, because a case study needs the richer set of baselines more
    than it needs full-split coverage.
    """
    from hallmark_repro.common import PRED_DIR

    out: dict[str, dict[str, dict]] = {}
    for tag in REFERENCE_BASELINES:
        candidates = [PRED_DIR / f"{tag}__{split}.jsonl"]
        candidates += [PRED_DIR / f"{tag}__{split}_{n}.jsonl" for n in sample_sizes]
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            continue
        by_key: dict[str, dict] = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                by_key[rec["bibtex_key"]] = rec
        out[tag] = by_key
    return out


def outcome_for(entry, pred: dict | None) -> str:
    if pred is None:
        return "ABSTAIN"
    if not pred.get("evaluated", True):
        return "ABSTAIN"
    label = pred.get("label")
    if label == "UNCERTAIN":
        return "ABSTAIN"
    is_hall = entry.label == "HALLUCINATED"
    if is_hall:
        return "TP" if label == "HALLUCINATED" else "FN"
    return "FP" if label == "HALLUCINATED" else "TN"


def build_cells(entries, preds_by_tag: dict, reference: str) -> dict:
    ref = preds_by_tag.get(reference) or next(iter(preds_by_tag.values()), {})
    cells: dict[tuple, list] = defaultdict(list)
    for entry in entries:
        pred = ref.get(entry.bibtex_key)
        outcome = outcome_for(entry, pred)
        key = (outcome, entry.hallucination_type or "VALID", entry.difficulty_tier or 0)
        cells[key].append(entry)
    return cells


def select_cases(entries, preds_by_tag: dict, reference: str, limit: int) -> list:
    cells = build_cells(entries, preds_by_tag, reference)
    by_key = {e.bibtex_key: e for e in entries}
    chosen: list = []
    used: set[str] = set()

    def take(key):
        if key not in cells:
            return None
        for entry in sorted(cells[key], key=lambda e: e.bibtex_key):
            if entry.bibtex_key not in used:
                used.add(entry.bibtex_key)
                return entry
        return None

    for outcome, htype, tier in PRIORITY_CELLS:
        if len(chosen) >= limit:
            break
        if htype == "ANY":
            candidates = [k for k in cells
                          if k[0] == outcome and (tier is None or k[2] == tier)]
            candidates.sort(key=lambda k: -len(cells[k]))
            for k in candidates:
                e = take(k)
                if e:
                    chosen.append((k, e))
                    break
        else:
            e = take((outcome, htype, tier if tier is not None else 0))
            if e is None and tier is not None:
                # tier may differ from the taxonomy default; retry without it
                for k in [k for k in cells if k[0] == outcome and k[1] == htype]:
                    e = take(k)
                    if e:
                        break
            if e:
                chosen.append(((outcome, htype, tier), e))
    return chosen


def describe(case_key, entry, preds_by_tag: dict) -> dict:
    outcome, htype, tier = case_key
    per_baseline = {}
    for tag, by_key in preds_by_tag.items():
        p = by_key.get(entry.bibtex_key)
        if p is None:
            per_baseline[tag] = None
            continue
        per_baseline[tag] = {
            "label": p.get("label"),
            "confidence": p.get("confidence"),
            "reason": p.get("reason"),
            "api_calls": p.get("api_calls"),
            "evaluated": p.get("evaluated", True),
            "subtest_results": p.get("subtest_results"),
            "api_sources_queried": p.get("api_sources_queried"),
        }
    return {
        "case_id": f"{outcome}-{htype}-{entry.bibtex_key[:8]}",
        "outcome_vs_reference": outcome,
        "bibtex_key": entry.bibtex_key,
        "bibtex_type": entry.bibtex_type,
        "ground_truth_label": entry.label,
        "hallucination_type": entry.hallucination_type,
        "difficulty_tier": entry.difficulty_tier,
        "generation_method": entry.generation_method,
        "source": entry.source,
        "fields": entry.fields,
        "gold_subtests": getattr(entry, "subtests", None),
        "gold_explanation": getattr(entry, "explanation", None),
        "baselines": per_baseline,
    }


def render_markdown(cases: list[dict], reference: str) -> str:
    lines = [
        "# 代表性案例分析（自动抽取）",
        "",
        f"参考基线：`{reference}`。每个单元格（结果 × 错误类型 × 难度层）抽取一例；",
        "同一引文列出全部基线的判定与理由，便于横向比较。",
        "",
    ]
    for c in cases:
        lines.append(f"## {c['case_id']}")
        lines.append("")
        lines.append(
            f"- 真值：**{c['ground_truth_label']}**"
            + (f"（{c['hallucination_type']}，tier {c['difficulty_tier']}）"
               if c["hallucination_type"] else "")
        )
        lines.append(f"- 生成方式：{c['generation_method']}；来源：{c['source']}")
        lines.append(f"- 参考基线上的结果：{c['outcome_vs_reference']}")
        lines.append("")
        lines.append("**书目字段**")
        lines.append("")
        lines.append("| 字段 | 值 |")
        lines.append("|---|---|")
        for k, v in c["fields"].items():
            lines.append(f"| {k} | `{str(v)[:200]}` |")
        lines.append("")
        if c.get("gold_subtests"):
            lines.append("**标注的子测试结果**：" + json.dumps(
                c["gold_subtests"], ensure_ascii=False))
            lines.append("")
        if c.get("gold_explanation"):
            lines.append(f"**标注说明**：{str(c['gold_explanation'])[:600]}")
            lines.append("")
        lines.append("**各基线判定**")
        lines.append("")
        lines.append("| 基线 | 判定 | 置信度 | 理由 |")
        lines.append("|---|---|---|---|")
        for tag, p in c["baselines"].items():
            if p is None:
                lines.append(f"| {tag} | 未运行 | | |")
            else:
                reason = (p.get("reason") or "").replace("|", "\\|")[:220]
                lines.append(f"| {tag} | {p['label']} | {p.get('confidence')} | {reason} |")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract representative cases")
    ap.add_argument("--split", default="test_public")
    ap.add_argument("--reference", default="checkifexist")
    ap.add_argument("--limit", type=int, default=16)
    args = ap.parse_args()

    entries = load_split(args.split)
    preds_by_tag = load_all_predictions(args.split)
    log("loaded predictions for %s", list(preds_by_tag))

    reference = args.reference if args.reference in preds_by_tag else (
        next(iter(preds_by_tag), "doi_only"))
    chosen = select_cases(entries, preds_by_tag, reference, args.limit)
    log("selected %d cases", len(chosen))

    cases = [describe(k, e, preds_by_tag) for k, e in chosen]
    write_json(OUT_DIR / "cases.json", {"split": args.split, "reference": reference,
                                        "n_cases": len(cases), "cases": cases})
    (OUT_DIR / "cases.md").write_text(render_markdown(cases, reference), encoding="utf-8")
    for c in cases:
        log("  %-38s %s / %s", c["case_id"], c["ground_truth_label"],
            c["hallucination_type"] or "-")


if __name__ == "__main__":
    main()
