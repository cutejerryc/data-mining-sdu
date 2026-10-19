"""E7 - Figures for the final paper.

Every figure reads the metric and prediction files written by the earlier
experiments; nothing is hard-coded, so a re-run of the experiments regenerates
the figures consistently.  Figures are written as PNG (for Word) and SVG (for
scaling) into ``figures/``.

Usage::

    python -m hallmark_repro.exp7_figures
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from hallmark_repro.common import FIG_DIR, METRIC_DIR, RESULTS_DIR, load_split, log, setup_logging

logger = setup_logging("exp7_figures")

plt.rcParams.update({
    "figure.dpi": 130,
    "savefig.dpi": 200,
    "font.size": 9,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.autolayout": True,
})

#: Chinese labels need a CJK font; fall back to English when absent.
CJK_CANDIDATES = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC"]
for _f in CJK_CANDIDATES:
    if any(_f.lower() in f.name.lower() for f in matplotlib.font_manager.fontManager.ttflist):
        plt.rcParams["font.sans-serif"] = [_f]
        break
plt.rcParams["axes.unicode_minus"] = False


def _load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _metric(tag: str, split: str) -> dict | None:
    return _load(METRIC_DIR / f"{tag}__{split}.json")


def _save(fig, name: str) -> None:
    for ext in ("png", "svg"):
        fig.savefig(FIG_DIR / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)
    log("wrote %s.png / .svg", name)


# ---------------------------------------------------------------------------

def fig_baseline_comparison() -> None:
    """Grouped bars: detection rate, FPR and F1 for every baseline we ran."""
    rows = []
    for tag, split, label in [
        ("always_valid", "test_public", "All-VALID (reference)"),
        ("always_hallucinated", "test_public", "All-HALLUCINATED (reference)"),
        ("random", "test_public", "Random (p=0.5)"),
        ("doi_presence_heuristic", "test_public", "DOI-presence heuristic"),
        ("doi_only_no_prescreening", "test_public", "DOI-only (no pre-screen)"),
        ("doi_only", "test_public", "DOI-only"),
        ("hallucitechecker", "test_public_300", "HalluCiteChecker (n=300)"),
        ("checkifexist", "test_public_300", "CheckIfExist (n=300)"),
        ("ensemble", "test_public_300", "Ensemble (n=300)"),
        ("bibtexupdater", "test_public", "bibtex-check Stage 1"),
        ("llm_zeroshot_deepseek-v41-flash", "test_public_200", "LLM zero-shot (n=200)"),
    ]:
        m = _metric(tag, split)
        if not m:
            continue
        rows.append((label, m))
    if not rows:
        log("fig_baseline_comparison: no metrics available yet")
        return

    labels = [r[0] for r in rows]
    dr = [r[1]["detection_rate"] for r in rows]
    fpr = [r[1]["false_positive_rate"] if r[1]["false_positive_rate"] is not None else 0.0
           for r in rows]
    f1 = [r[1]["f1_hallucination"] for r in rows]

    y = np.arange(len(rows))
    h = 0.26
    fig, ax = plt.subplots(figsize=(9.2, 0.44 * len(rows) + 2.0))
    ax.barh(y + h, dr, h, label="检出率 Detection Rate", color="#2f6fb0")
    ax.barh(y, f1, h, label="幻觉类 F1", color="#4f9d69")
    ax.barh(y - h, fpr, h, label="假阳性率 FPR", color="#c0563c")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.18)
    ax.set_xlabel("指标值")
    ax.set_title("HALLMARK test_public 上各基线的检出率、F1 与假阳性率\n"
                 "（标注 n 的条目为冻结子样本，其余为完整划分）", fontsize=10)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=3, frameon=False)
    for i, (d, f, p) in enumerate(zip(dr, f1, fpr)):
        ax.text(d + 0.01, i + h, f"{d:.2f}", va="center", fontsize=7.5)
        ax.text(f + 0.01, i, f"{f:.2f}", va="center", fontsize=7.5)
        ax.text(p + 0.01, i - h, f"{p:.2f}", va="center", fontsize=7.5)
    _save(fig, "fig1_baseline_comparison")


def fig_tier_decomposition() -> None:
    """Detection rate by difficulty tier, for the baselines that have tiers."""
    tags = [
        ("doi_only", "test_public", "DOI-only"),
        ("bibtexupdater", "test_public", "bibtex-check"),
        ("checkifexist", "test_public_300", "CheckIfExist"),
        ("llm_zeroshot_deepseek-v41-flash", "test_public_200", "LLM zero-shot"),
    ]
    data = []
    for tag, split, label in tags:
        m = _metric(tag, split)
        if not m or not m.get("per_tier_metrics"):
            continue
        tiers = m["per_tier_metrics"]
        data.append((label, [tiers.get(str(t), {}).get("detection_rate", 0.0) for t in (1, 2, 3)]))
    if not data:
        log("fig_tier_decomposition: no per-tier metrics yet")
        return

    x = np.arange(3)
    w = 0.8 / len(data)
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    colors = ["#2f6fb0", "#4f9d69", "#c0563c", "#8a6fb0", "#d9a441"]
    for i, (label, vals) in enumerate(data):
        ax.bar(x + i * w - 0.4 + w / 2, vals, w, label=label, color=colors[i % len(colors)])
        for xi, v in zip(x + i * w - 0.4 + w / 2, vals):
            ax.text(xi, v + 0.02, f"{v:.2f}", ha="center", fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels(["Tier 1 易", "Tier 2 中", "Tier 3 难"])
    ax.set_ylabel("检出率")
    ax.set_ylim(0, 1.08)
    ax.set_title("按难度层的检出率：所有方法在 Tier 3 上都接近失效", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    _save(fig, "fig2_tier_decomposition")


def fig_type_heatmap() -> None:
    """Heatmap of detection rate by hallucination type."""
    m = _metric("bibtexupdater", "test_public") or _metric("doi_only", "test_public")
    if not m or not m.get("per_type_metrics"):
        log("fig_type_heatmap: no per-type metrics yet")
        return
    per_type = m["per_type_metrics"]
    items = sorted(
        ((t, v.get("detection_rate", 0.0), v.get("num_hallucinated", 0))
         for t, v in per_type.items()),
        key=lambda kv: kv[1],
    )
    names = [f"{t} (n={n})" for t, _, n in items]
    vals = np.array([[v] for _, v, _ in items])

    fig, ax = plt.subplots(figsize=(5.2, 0.34 * len(items) + 1.8))
    im = ax.imshow(vals, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xticks([0])
    ax.set_xticklabels([m["tool_name"]])
    for i, v in enumerate(vals[:, 0]):
        ax.text(0, i, f"{v:.2f}", ha="center", va="center", fontsize=8,
                color="black" if 0.25 < v < 0.85 else "white")
    ax.set_title("按错误类型的检出率（越低越难）", fontsize=10)
    ax.grid(False)
    fig.colorbar(im, ax=ax, fraction=0.05, pad=0.08, label="检出率")
    _save(fig, "fig3_type_heatmap")


def fig_subtest_matrix() -> None:
    """Failure rate of each released sub-test, per hallucination type."""
    p = RESULTS_DIR / "subtests" / "subtest_offline.json"
    data = _load(p)
    if not data:
        log("fig_subtest_matrix: run exp3 --offline first")
        return
    matrix = data["type_subtest_matrix"]["test_public"]
    types = [t for t in matrix if t != "__VALID__"]
    types.sort(key=lambda t: -matrix[t]["n"])
    subtests = ["doi_resolves", "title_exists", "authors_match",
                "venue_correct", "fields_complete", "cross_db_agreement"]

    vals = np.array([[matrix[t]["fail_rate"][s] for s in subtests] for t in types])
    fig, ax = plt.subplots(figsize=(6.6, 0.36 * len(types) + 2.0))
    im = ax.imshow(vals, cmap="Blues", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(subtests)))
    ax.set_xticklabels([s.replace("_", "\n") for s in subtests], fontsize=8)
    ax.set_yticks(range(len(types)))
    ax.set_yticklabels([f"{t} (n={matrix[t]['n']})" for t in types], fontsize=8)
    for i in range(len(types)):
        for j in range(len(subtests)):
            v = vals[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7,
                    color="white" if v > 0.55 else "black")
    ax.set_title("标注层面：各错误类型下六个子测试的失败率", fontsize=10)
    ax.grid(False)
    fig.colorbar(im, ax=ax, fraction=0.04, pad=0.03, label="失败率")
    _save(fig, "fig4_subtest_failure_matrix")


def fig_cost_effect() -> None:
    """Detection rate against mean API calls per entry."""
    points = []
    for tag, split, label in [
        ("doi_presence_heuristic", "test_public", "DOI-presence"),
        ("doi_only", "test_public", "DOI-only"),
        ("checkifexist", "test_public_300", "CheckIfExist"),
        ("hallucitechecker", "test_public_300", "HalluCiteChecker"),
        ("bibtexupdater", "test_public", "bibtex-check"),
        ("llm_zeroshot_deepseek-v41-flash", "test_public_200", "LLM zero-shot"),
    ]:
        m = _metric(tag, split)
        if not m:
            continue
        calls = m.get("mean_api_calls")
        if calls is None:
            continue
        points.append((label, calls, m["detection_rate"], m["false_positive_rate"] or 0.0))
    if not points:
        log("fig_cost_effect: not enough metrics yet")
        return

    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    for label, calls, dr, fpr in points:
        ax.scatter(calls, dr, s=90, label=label, zorder=3)
        ax.annotate(f"FPR={fpr:.2f}", (calls, dr), textcoords="offset points",
                    xytext=(6, -10), fontsize=7, color="#555555")
    ax.set_xlabel("平均 API 调用次数 / 条目")
    ax.set_ylabel("检出率")
    ax.set_ylim(0, 1.02)
    ax.set_title("成本与效果：更多检索调用并未带来成比例的检出率", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    _save(fig, "fig5_cost_effect")


def fig_eval_mode_gap() -> None:
    """Conservative vs aggressive scoring for the released Stage 1."""
    tags = [("bibtexupdater", "test_public", "bibtex-check")] + [
        (p.stem.split("__")[0], "test_public", p.stem.split("__")[0])
        for p in sorted(METRIC_DIR.glob("cascade_*__test_public*.json"))
    ]
    rows = []
    for tag, split, label in tags:
        cons = _metric(tag, split)
        agg = _load(METRIC_DIR / f"{tag}__{split}__aggressive.json")
        if cons and agg:
            rows.append((label, cons, agg))
    if not rows:
        log("fig_eval_mode_gap: need conservative and aggressive metrics")
        return

    metrics = ["detection_rate", "false_positive_rate", "f1_hallucination", "tier_weighted_f1"]
    names = ["检出率", "假阳性率", "幻觉类 F1", "Tier 加权 F1"]
    x = np.arange(len(metrics))
    fig, axes = plt.subplots(1, len(rows), figsize=(4.6 * len(rows), 3.6), squeeze=False)
    for ax, (label, cons, agg) in zip(axes[0], rows):
        c = [cons.get(m) or 0.0 for m in metrics]
        a = [agg.get(m) or 0.0 for m in metrics]
        w = 0.38
        ax.bar(x - w / 2, c, w, label="保守 conservative", color="#2f6fb0")
        ax.bar(x + w / 2, a, w, label="激进 aggressive", color="#c0563c")
        for xi, (cv, av) in enumerate(zip(c, a)):
            ax.text(xi - w / 2, cv + 0.015, f"{cv:.2f}", ha="center", fontsize=7)
            ax.text(xi + w / 2, av + 0.015, f"{av:.2f}", ha="center", fontsize=7)
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontsize=8)
        ax.set_ylim(0, 1.28)
        ax.set_title(label, fontsize=9)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2, frameon=False,
                  fontsize=7.5)
    fig.suptitle("拒答计分方式的影响：激进模式用假阳性率换取召回", fontsize=10)
    _save(fig, "fig6_eval_mode_gap")


def fig_live_subtest_agreement() -> None:
    """Live re-derivation vs released annotation, per sub-test."""
    p = RESULTS_DIR / "subtests" / "subtest_live_summary.json"
    data = _load(p)
    if not data:
        log("fig_live_subtest_agreement: run exp3 --live first")
        return
    per = data["per_subtest"]
    names = list(per)
    agree = [per[n]["agreement"] if per[n]["agreement"] is not None else 0.0 for n in names]
    n_cmp = [per[n]["comparable"] for n in names]
    abst = [per[n]["live_abstained"] for n in names]

    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    bars = ax.bar(x, agree, 0.55, color="#4f9d69")
    for xi, (a, n, ab) in enumerate(zip(agree, n_cmp, abst)):
        ax.text(xi, a + 0.02, f"{a:.2f}\nn={n}, 弃权={ab}", ha="center", fontsize=7.5)
    ax.set_xticks(x)
    ax.set_xticklabels([n.replace("_", "\n") for n in names], fontsize=8)
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("与标注的一致率")
    ax.set_title(f"在 {data['n_sample']} 条分层子样本上重新推导子测试：与标注的一致率", fontsize=10)
    _save(fig, "fig7_live_subtest_agreement")


def main() -> None:
    fig_baseline_comparison()
    fig_tier_decomposition()
    fig_type_heatmap()
    fig_subtest_matrix()
    fig_cost_effect()
    fig_eval_mode_gap()
    fig_live_subtest_agreement()
    log("figures written to %s", FIG_DIR)


if __name__ == "__main__":
    main()
