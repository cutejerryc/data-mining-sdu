"""Renumber the survey's citations into GB/T 7714 citation order.

Chinese academic convention (顺序编码制) numbers references by first appearance
in the text.  The survey was drafted with named markers — ``[HALLMARK]``,
``[CiteAudit]`` — which read well while writing but are not how a submitted
paper cites.  This script:

1. finds every marker and its first appearance, giving the citation order;
2. reorders and renumbers the reference list to match;
3. rewrites each marker as a superscript bracketed number (``^[1]^``), merging
   adjacent markers into one group (``^[7,13]^``);
4. keeps the entries that are never cited, renumbered after the cited ones, so
   nothing silently disappears from the bibliography.

Usage::

    python -m hallmark_repro.renumber_citations docs/01_调研报告.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

#: Marker -> a distinctive substring of its bibliography entry.  Matching on a
#: substring rather than on position means a reordered reference list still
#: resolves correctly.
MARKER_TO_ENTRY = {
    "HALLMARK": "HALLMARK: Diagnosing Three Failure Modes",
    "CiteAudit": "CiteAudit: You Cited It",
    "CiteTracer": "Source or It Didn't Happen",
    "GhostCite": "GhostCite: A Large-Scale Analysis",
    "PhantomRef": "Phantom References: Hallucinated Citations",
    "HalluCiteChecker": "HalluCiteChecker: A Lightweight Toolkit",
    "CitationIntegrity": "Assessing citation integrity in biomedical",
    "SemanticCite": "SemanticCite: Citation Verification",
    "SciCiteVal": "SciCiteVal: A Multi-Domain Dataset",
    "RefVerifier": "RefVerifier: Semi-Automated Reference Claim",
    "CiteCheck": "CiteCheck: Towards Accurate Citation Faithfulness",
    "SciFact": "Fact or Fiction: Verifying Scientific Claims",
    "MultiVerS": "MultiVerS: Improving scientific claim verification",
    "SciFactOpen": "SciFact-Open: Towards open-domain",
    "MiniCheck": "MiniCheck: Efficient Fact-Checking",
    "RefChecker": "RefChecker: Reference-based Fine-grained",
    "ALCE": "Enabling Large Language Models to Generate Text",
    "AttributionBench": "AttributionBench: How Hard",
    "Survey2023": "Scientific Fact-Checking: A Survey of Resources",
    "ToolBounds2026": "Detecting Hallucinated and Suspicious Citations",
}

ENTRY_RE = re.compile(r"^(\d+)\.\s+(.*)$")
MARKER_RE = re.compile(r"\[([A-Za-z][A-Za-z0-9]*)\]")


def main() -> None:
    ap = argparse.ArgumentParser(description="Renumber citations in citation order")
    ap.add_argument("path")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    path = Path(args.path)
    text = path.read_text(encoding="utf-8")

    ref_head = "## 参考文献"
    if ref_head not in text:
        raise SystemExit(f"{path}: no '{ref_head}' section")
    body, tail = text.split(ref_head, 1)

    # Split the tail into the bibliography and anything after it.
    m = re.search(r"\n## ", tail)
    refs_block, after = (tail[:m.start()], tail[m.start():]) if m else (tail, "")

    entries: list[tuple[int, str]] = []
    for line in refs_block.splitlines():
        em = ENTRY_RE.match(line.strip())
        if em:
            entries.append((int(em.group(1)), em.group(2).strip()))
    if not entries:
        raise SystemExit(f"{path}: no numbered reference entries found")

    # 1. Citation order = first appearance of each marker in the body.
    seen: list[str] = []
    for mk in MARKER_RE.findall(body):
        if mk in MARKER_TO_ENTRY and mk not in seen:
            seen.append(mk)

    # 2. Resolve markers to entries and build the new numbering.
    old_to_new: dict[int, int] = {}
    new_entries: list[str] = []
    for mk in seen:
        needle = MARKER_TO_ENTRY[mk]
        hit = next((n for n, t in entries if needle in t), None)
        if hit is None:
            print(f"  WARNING: no bibliography entry matches marker [{mk}]", file=sys.stderr)
            continue
        if hit in old_to_new:
            continue
        old_to_new[hit] = len(new_entries) + 1
        new_entries.append(dict(entries)[hit])
    # 3. Uncited entries keep their relative order, numbered after the cited ones.
    uncited = [(n, t) for n, t in entries if n not in old_to_new]
    for n, t in uncited:
        old_to_new[n] = len(new_entries) + 1
        new_entries.append(t)

    print(f"cited markers: {len(seen)}; references: {len(entries)} "
          f"({len(entries) - len(uncited)} cited, {len(uncited)} uncited)")
    for mk in seen:
        needle = MARKER_TO_ENTRY[mk]
        hit = next((n for n, t in entries if needle in t), None)
        print(f"  [{mk:18s}] -> [{old_to_new.get(hit, '?')}]")

    # 4. Rewrite the body: merge adjacent markers, then emit superscripts.
    def repl(match: re.Match) -> str:
        nums = []
        for mk in MARKER_RE.findall(match.group(0)):
            needle = MARKER_TO_ENTRY.get(mk)
            hit = next((n for n, t in entries if needle and needle in t), None)
            if hit is not None:
                nums.append(str(old_to_new[hit]))
        # Ascending order: a citation group reads as a set, and GB/T 7714
        # examples print them in numeric order.
        nums = sorted(set(nums), key=int)
        return f"^[{','.join(nums)}]^" if nums else match.group(0)

    # Match runs of consecutive markers so [A][B] becomes one superscript group.
    body = re.sub(r"(?:\[[A-Za-z][A-Za-z0-9]*\])+", repl, body)

    left = MARKER_RE.findall(body)
    if left:
        print(f"  remaining unconverted markers: {sorted(set(left))}", file=sys.stderr)

    # 5. Rebuild the bibliography with bracket prefixes.
    lines = [f"[{i}] {t}" for i, t in enumerate(new_entries, start=1)]
    out = body.rstrip() + "\n\n" + ref_head + "\n\n" + "\n\n".join(lines) + "\n" + after

    if args.dry_run:
        print("(dry run, nothing written)")
        return
    path.write_text(out, encoding="utf-8")
    print(f"written: {path}")


if __name__ == "__main__":
    main()
