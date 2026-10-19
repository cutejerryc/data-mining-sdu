# 文献真实性校验与证据对齐 — 复现代码与数据

山东大学 数据挖掘 2026 课程 Project
**陈红瑞　202635482　计算机技术**

本仓库是课程 Project「文献真实性校验与证据对齐」的完整交付材料：复现实验代码、逐样本预测、评分结果、图表、运行日志与两份报告。

---

## 复现对象

| 项目 | 内容 |
|---|---|
| 论文 | HALLMARK: Diagnosing Three Failure Modes in LLM Citation Verifiers |
| arXiv | [2607.18360](https://arxiv.org/abs/2607.18360) |
| 官方仓库 | [rpatrik96/hallmark](https://github.com/rpatrik96/hallmark) |
| 上游提交 | `80ce8ded446ad6d1792c62bf7c18d015eade3779`（2026-10-16） |
| 数据版本 | v1.2.4（构建日期 2026-10-15） |
| 复现日期 | 2026-10-18 |

选择该基准的原因：无 GPU 需求（本机仅 2 GB 显存），且仓库内发布了全部基线的逐样本参考结果，使「复现是否成功」可以被逐指标核对，而不是只能与论文正文数字做主观比较。

---

## 主要结果

### 1. 确定性基线达到逐项一致

`doi_only` 在 `dev_public` 上的**检出率、假阳性率、幻觉类 F1、Tier 加权 F1、MCC、AUROC、ECE 七项指标与仓库发布值绝对差全部为 0.0000**；`test_public` 上仅 AUROC 与 ECE 有 0.0009 与 0.0004 的差异，来自在线 DOI 解析的不确定性。

### 2. Stage 1 的差异是工作点偏移，不是判别力下降

| 指标 | 发布值 | 本次复现 | 绝对差 |
|---|---|---|---|
| 检出率 | 0.8359 | 0.9848 | +0.1489 |
| 假阳性率 | 0.0717 | 0.3090 | +0.2373 |
| 幻觉类 F1 | 0.8902 | 0.9087 | +0.0185 |
| **MCC** | **0.7420** | **0.7387** | **−0.0033** |
| AUROC | 0.9200 | 0.8009 | −0.1191 |

检出率与假阳性率都大幅高于发布值，但 MCC 几乎相同——**同一工具在来源退化下只是移向更激进的工作点，用误报换召回，判别力本身并未下降**。逐条目状态分布证实了原因：仅 20.1% 的条目被「肯定确认为真」，而上游注释记载健康运行约为 52%。

### 3. 子测试：标注层面强，实测层面弱

把发布数据中的子测试标注当检测器，「任一失败」在 `test_public` 上 F1 = 0.971；但在 180 条分层子样本上从原始来源重新推导同样六个子测试时，与标注的一致率从 0.2266（场所正确性）到 0.9667（字段完整性）不等，实时检测器的假阳性率高达 0.9848——退化为「几乎全部报警」。**信息量最高的 `cross_db_agreement` 恰好是实测最不可靠的。**

### 4. 难度层是「方法 × 错误类型」的联合属性

`hallucitechecker` 在「最难」的 Tier 3 上检出率 0.7091，在「最易」的 Tier 1 上仅 0.2222。因为难度层是相对**字段级核验**定义的，而它只查标题：对它而言「论文不存在」容易、「字段错误」困难。

### 5. 级联的贡献是覆盖率而非准确率

重建的级联把弃权条目从 204 条压到 13 条（覆盖率 0.7545 → 0.9844），而 MCC 从 0.7387 微降到 0.7265。它让系统能对 98% 的输入给出答复，但没有提升判别力。

---

## 目录结构

```
├── REPRODUCTION.md      完整复现说明：环境准备、运行方式、全部偏离、已知局限（请先读）
├── docs/                两份报告
│   ├── 01_调研报告.md / .docx        文献调研报告
│   └── 02_课程论文.md / .docx        最终课程论文
├── code/hallmark_repro/ 复现实验代码，可独立运行
│   ├── common.py                     公共工具：路径、评分、溯源 manifest
│   ├── parallel_runner.py            容错并发执行器（断点续跑、逐条错误隔离）
│   ├── llm_client.py                 LLM 网关适配层
│   ├── exp0_audit.py                 数据集审计
│   ├── exp1_baselines.py             确定性基线
│   ├── exp2_cascade.py               数据库优先级联（Stage 1 / Stage 2）
│   ├── exp2b_cascade_from_stage1.py  从已保存的 Stage 1 输出重建级联
│   ├── exp3_subtests.py              子测试诊断（标注层面 / 实测层面）
│   ├── exp4_llm.py                   LLM 基线
│   ├── exp5_compare.py               与仓库发布参考值的一致性比对
│   ├── exp6_cases.py                 代表性案例抽取
│   ├── exp7_figures.py               图表生成
│   ├── run_experiments.py            实验调度
│   ├── md2docx.py                    Markdown → Word 转换（三线表、上标引用、全黑字体）
│   ├── renumber_citations.py         参考文献按 GB/T 7714 引用顺序重编号
│   ├── render_docx.py                Word → PDF → PNG（排版验收）
│   └── package.py                    打包脚本
├── results/
│   ├── audit/           数据集审计（划分、标签、类型、难度、子测试覆盖、完整性检查）
│   ├── predictions/     逐条目预测（JSONL，每基线每划分一份）
│   ├── metrics/         评分结果（JSON，含 _manifest 溯源块）
│   ├── subtests/        子测试诊断（含 180 条逐条对比记录）
│   ├── comparison/      与仓库 data/v1.2/baseline_results/ 的逐指标比对
│   ├── cascade/         重建级联的汇总
│   ├── samples/         冻结子样本定义（ID 与组成分布）
│   └── cases/           16 个代表性案例
├── figures/             7 张图表（PNG + SVG）
└── logs/                运行日志
```

---

## 快速开始

```bash
# 1. 克隆上游仓库并锁定提交（无 GPU 需求）
git clone https://github.com/rpatrik96/hallmark
cd hallmark && git checkout 80ce8ded && pip install -e .

# 2. bibtex-check 需要独立环境（依赖 bibtexparser 1.x，与 HALLMARK 的 2.x 冲突）
python -m venv venv_btu
venv_btu/Scripts/pip install bibtex-updater "bibtexparser<2"

# 3. LLM 凭据（仅 LLM 基线需要）
export OPENCODE_API_KEY=<your-key>

# 4. 运行
cd code
python -m hallmark_repro.run_experiments --only exp1 exp2 exp3 exp4 exp5 exp6
python -m hallmark_repro.exp7_figures
```

未设置 LLM 凭据时，`exp1`/`exp2`/`exp3`/`exp5`/`exp6`/`exp7` 仍可完整运行。

---

## 溯源与可复现性

每个 `results/metrics/*.json` 都带 `_manifest` 块，记录：上游提交号、划分文件 SHA-256、运行时间戳、API 调用总数、逐条目耗时、Python 与平台版本、产生该结果的完整命令行。

**信息泄漏防护**：只向基线传递 `BlindEntry`（剥离 `label`、`hallucination_type`、`difficulty_tier`、`explanation`、`subtests`、`url`）；不使用数据文件中的历史预测；子样本规则在任何模型输出产生之前冻结。

**如实报告失败**：执行器对每条目做错误隔离，重试耗尽后记为拒答（`UNCERTAIN`，`evaluated=False`）并继续运行；拒答数在指标文件中单独计数，覆盖率同时报告。

---

## ⚠️ 来源可用性（影响结论解读，务必阅读）

复现环境的网络条件与论文作者存在实质差异，且**在单次会话内观察到状态变化**：

| 来源 | 状态 | 证据 |
|---|---|---|
| CrossRef | 可达但检索质量弱 | HTTP 200；但按完整标题检索返回无关结果 |
| OpenAlex | **会话内从正常转为配额耗尽** | 早期 200（子测试 160/180 成功）；后期 429，报文说明无密钥配额按**出口 IP 全体共享**、剩余 $0.0009、UTC 午夜重置 |
| DataCite | 正常 | HTTP 200 |
| arXiv | 正常 | 配速 20 次/分钟 |
| Semantic Scholar | 限流 | 无密钥时 HTTP 429；上游默认配速 10 次/分钟 |
| **DBLP** | **被反爬拦截** | 所有请求返回 HTTP 202 + Anubis 挑战页（HTML 而非 JSON）；实测 180/180 失败 |
| **OpenReview** | **被拒绝** | `api.openreview.net` / `api2.openreview.net` 均返回 HTTP 403 |

由此产生的三条重要边界：

1. **所有 Stage 1 与级联数字都是在「来源不完整」条件下测得的**，与作者在健康网络下得到的数值不可直接比较。`bibtex-check` 在来源查询不完整条目超过 10% 时会以退出码 5 结束并拒绝评分，本项目通过 `HALLMARK_ALLOW_SOURCE_OUTAGE=1` 覆盖该门禁以得到可评分结果。
2. **`checkifexist` 未能被有效测量**：其回退来源（Semantic Scholar、OpenAlex）运行时均返回 429，300 条子样本输出全部为 HALLUCINATED。这是来源退化下的失效，不是方法性能，故未列入方法比较表。
3. **LLM 数字来自替代模型**：上游 LLM 基线针对 GPT-5.1 / Claude Sonnet 4.6 / OpenRouter 发布，这些端点在本环境不可达；本项目改用 OpenAI 兼容网关与 `deepseek-v4.1-flash`。**所有 LLM 数字都是适配实验，不是对已发布数值的复现。**

此外，`deepseek-v4.1-flash` 是重推理模型，默认 1024 token 预算下会把预算全部消耗在隐藏推理字段上、可见输出为空；本项目将 `max_completion_tokens` 提高到 8192（实测 8 次调用仅 1 次可用 → 6/6 成功）。未报告该设置时同一模型的评测结果无法复现。

---

## 已知局限

1. 实测层面的子测试使用自行实现的元数据获取逻辑（CrossRef + OpenAlex 直连），而非 `bibtex-check` 的内部路径，因此一致率同时包含标注的不稳定性与实现差异。
2. DBLP 不可用使 `venue_correct` 与 `cross_db_agreement` 的低一致率无法在「来源不可用」与「判定逻辑脆弱」之间完全归因。
3. 多来源基线使用冻结的分层子样本（300 条 / 200 条），指标与全量划分不可直接比较；单来源基线与 Stage 1 在完整划分上运行。
4. 本项目**不声称实现了自动证据检索**，也不声称完成了论断与原文证据的语义对齐——实验部分明确限定在书目真实性核验。

---

## 许可与致谢

- 复现对象 HALLMARK 及其数据：MIT，© Patrik Reizinger 等
- 本项目代码与报告：课程作业成果
- 本仓库不包含任何 API 密钥；运行 LLM 基线需自备凭据
