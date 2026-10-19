# 引用真实性核验的可复现性研究 — 复现实验说明

本目录是课程 Project「文献真实性校验与证据对齐」的完整交付包，包含复现实验的全部代码、数据、逐样本预测、评价脚本、运行日志、图表与文档。

**复现对象**：HALLMARK（arXiv:2607.18360），仓库 <https://github.com/rpatrik96/hallmark>，提交 `80ce8ded446ad6d1792c62bf7c18d015eade3779`（2026-10-16），数据版本 v1.2.4（构建日期 2026-10-15）。

**复现日期**：2026-10-18。

---

## 一、目录结构

```
project/
├── code/hallmark_repro/          复现实验代码（可独立运行）
│   ├── common.py                 公共工具：路径、划分加载、评分、manifest
│   ├── parallel_runner.py        容错并发执行器（断点续跑、逐条错误隔离）
│   ├── llm_client.py             LLM 网关适配层（OpenAI 兼容端点）
│   ├── exp0_audit.py             数据集审计
│   ├── exp1_baselines.py         确定性基线
│   ├── exp2_cascade.py           数据库优先级联（Stage 1 / Stage 2）
│   ├── exp3_subtests.py          子测试诊断（标注层面 / 实测层面）
│   ├── exp4_llm.py               LLM 基线（零样本 / 工具增强）
│   ├── exp5_compare.py           与仓库发布参考值的一致性比对
│   ├── exp6_cases.py             代表性案例抽取
│   ├── exp7_figures.py           图表生成
│   ├── run_experiments.py        实验调度（按优先级串行）
│   └── md2docx.py                Markdown → Word 转换
├── repos/hallmark/               上游仓库副本（含数据与评测代码）
├── venv_btu/                     bibtex-updater 的隔离环境（依赖冲突，见下）
├── results/
│   ├── audit/                    数据集审计（dataset_audit.json + TSV）
│   ├── predictions/              逐条目预测（JSONL，每基线每划分一份）
│   ├── metrics/                  评分结果（JSON，含 _manifest 溯源块）
│   ├── subtests/                 子测试诊断（标注层面 + 实测层面）
│   ├── comparison/               与发布参考值的一致性比对
│   ├── samples/                  冻结子样本定义（ID 与组成分布）
│   ├── cases/                    案例分析（JSON + Markdown）
│   └── checkpoints/              断点续跑记录（执行器中间状态）
├── figures/                      论文图表（PNG + SVG）
├── logs/                         运行日志（每实验一份 + driver.log）
└── docs/                         调研报告与课程论文（Markdown + Word）
```

---

## 二、环境准备

### 2.1 基础环境

- Windows 11，Python 3.11.5
- 无 GPU 需求（HALLMARK 为纯 Python 实现）；本机 GPU 为 MX570 2 GB，未使用
- 主要依赖：`bibtexparser>=2.0.0b`、`requests`、`httpx`、`rapidfuzz`、`matplotlib`、`numpy`、`python-docx`

```bash
# 克隆上游仓库并锁定提交
git clone https://github.com/rpatrik96/hallmark
cd hallmark
git checkout 80ce8ded446ad6d1792c62bf7c18d015eade3779
pip install -e .

# 项目依赖
pip install matplotlib numpy python-docx openai
```

### 2.2 bibtex-check 的隔离环境（必须）

`bibtex-updater` 依赖 `bibtexparser` 1.x，而 HALLMARK 要求 2.x，二者无法共存。因此该工具安装在独立虚拟环境中：

```bash
python -m venv venv_btu
venv_btu/Scripts/pip install bibtex-updater "bibtexparser<2"
```

`exp2_cascade.py` 会通过 `HALLMARK_BIBTEX_CHECK_BIN` 环境变量指向该可执行文件，无需修改 PATH。

### 2.3 LLM 凭据（仅 LLM 基线需要）

```bash
export OPENCODE_API_KEY=<your-key>
export OPENCODE_BASE_URL=https://opencode.ai/zen/go/v1   # 可选，此为默认值
export OPENCODE_MODEL=deepseek-v4.1-flash                # 可选，此为默认值
```

未设置凭据时，`exp1`/`exp2`/`exp3`/`exp5`/`exp6`/`exp7` 仍可完整运行；`exp4` 与 `exp2 --cascade` 会拒绝启动并给出提示。

---

## 三、运行方式

```bash
cd code

# 一键运行全部实验（按优先级串行，网络受限时耗时较长）
python -m hallmark_repro.run_experiments --only exp1 exp2 exp3 exp4 exp5 exp6

# 生成图表
python -m hallmark_repro.exp7_figures

# 单独运行某一实验
python -m hallmark_repro.exp0_audit                      # 数据集审计（离线）
python -m hallmark_repro.exp1_baselines doi_only         # 单个基线
python -m hallmark_repro.exp2_cascade --stage1-only --split test_public
python -m hallmark_repro.exp3_subtests --offline         # 标注层面（离线）
python -m hallmark_repro.exp3_subtests --live --n 180    # 实测层面（需网络）
python -m hallmark_repro.exp4_llm --mode zeroshot --n 200 --model deepseek-v4.1-flash
python -m hallmark_repro.exp5_compare                    # 与发布值比对
python -m hallmark_repro.exp6_cases --limit 16           # 案例抽取
```

**断点续跑**：所有联网实验的逐条目结果实时写入 `results/checkpoints/`。中断后重新执行同一命令会自动跳过已完成的条目。

**文档排版约定**（`md2docx.py` 实现）：

- **字体全部为黑色**：代码片段与链接靠字体（Consolas / Times New Roman）区分，不使用颜色，保证灰度打印正常。
- **表格为三线表**：仅保留顶线（1.5 pt）、表头下线（0.75 pt）与底线（1.5 pt），无竖线。
- **引用为上标方括号编号**：正文中写 `^[3]^`，渲染为上标；多条合并写 `^[3,7,11]^`，脚本自动按升序排列。
- **参考文献按 GB/T 7714 顺序编码制**：`renumber_citations.py` 扫描正文中每条文献的**首次出现位置**确定编号，据此重排文献表并改写正文标记；文献条目以 `[n]` 开头并悬挂缩进。未被正文引用的条目会被报告出来。

**文档转换**：

```bash
python -m hallmark_repro.md2docx ../docs/01_调研报告.md ../docs/01_调研报告.docx
python -m hallmark_repro.md2docx ../docs/02_课程论文.md ../docs/02_课程论文.docx
```

---

## 四、结果溯源

每个 `results/metrics/*.json` 文件都带有一个 `_manifest` 块，记录：

| 字段 | 含义 |
|---|---|
| `tag` / `split` / `eval_mode` | 基线名、划分、计分立场 |
| `n_entries` / `n_predictions` / `n_answered` / `n_uncertain` / `n_unevaluated` | 覆盖率相关计数 |
| `label_counts` | 预测标签分布 |
| `split_sha256` | 所评划分文件的 SHA-256（数据版本可核验） |
| `timestamp` | 运行时间（UTC） |
| `api_calls` / `wall_clock_seconds` | 成本与耗时 |
| `environment` | Python 版本、平台、HALLMARK 版本与上游提交号 |
| `command` | 产生该结果的完整命令行 |

`_extra` 块记录基线特有的信息，例如 `bibtexupdater` 的 `source_condition` 与 `lookup_quality`（各来源失败计数、查询不完整条目比例）。

---

## 五、关键设置与偏离说明

**本节列出的偏离限定了结论的适用范围，请在引用本包结果时一并引用。**

### 5.1 来源可用性（影响最大）

实测于 2026-10-18，**且在单次会话内观察到状态变化**：

| 来源 | 状态 | 证据 |
|---|---|---|
| CrossRef | 可达但检索质量弱 | HTTP 200；但按完整标题检索返回无关结果（如对 SoftMatch 的标题返回 "Trade-off between Quality and Cost"） |
| OpenAlex | **会话内从正常转为配额耗尽** | 实验早期 HTTP 200（E3.2 子测试 160/180 成功）；后期 HTTP 429，报文："Insufficient budget. This request has no API key, so it counts against the free daily budget shared by everyone on your network's IP address, and that budget is used up ($0.0009 remaining; resets at midnight UTC)" |
| DataCite | 正常 | HTTP 200 |
| arXiv | 正常 | 配速 20 次/分钟 |
| Semantic Scholar | 限流 | 无密钥时 HTTP 429；上游默认配速 10 次/分钟 |
| **DBLP** | **被反爬拦截** | 所有 API 请求返回 HTTP 202 并附带 Anubis 挑战页（"Making sure you're not a bot!"），返回 HTML 而非 JSON；实测 180/180 失败 |
| **OpenReview** | **被拒绝** | `api.openreview.net` / `api2.openreview.net` 均返回 HTTP 403 |
| doi.org | 重定向正常 | 出版社侧约 42% 返回 202/403/400 等非 200 状态 |

**OpenAlex 的配额是"同一出口 IP 全体共享"的资源**，一次下午的评测即可耗尽，随后所有依赖它的方法在同一会话内不可用。这直接影响两个实验：

- `checkifexist` 的回退来源（Semantic Scholar、OpenAlex）在运行时均返回 429，其 `api_sources_queried` 只剩 CrossRef 一项，300 条子样本输出全部为 HALLUCINATED。**该结果不是方法性能，而是来源退化下的失效**，因此未列入方法比较表。
- `hallucitechecker` 的名义配置是三来源，实测中仅 7/299 条真正查到 Semantic Scholar（172 条为 CrossRef + arXiv，120 条仅 CrossRef）。

由于 DBLP 与 OpenReview 不可用，`bibtex-check` 的来源不完整比例持续高于其 10% 门禁，工具会以退出码 5 结束并拒绝评分。本项目通过 `HALLMARK_ALLOW_SOURCE_OUTAGE=1` 覆盖该门禁以得到可评分结果，**因此所有 Stage 1 数字都标注为「来源不完整条件下测得」**，与作者在健康网络下得到的数值不可直接比较。逐条目的 `coverage_incomplete` 标志与各来源失败计数已保存于指标文件中。

### 5.2 LLM 模型替换

上游 LLM 基线针对 GPT-5.1 / Claude Sonnet 4.6 / OpenRouter 系列发布，这些端点在复现环境不可达。本项目改用 OpenAI 兼容网关与 `deepseek-v4.1-flash`。**所有 LLM 数字都是替代模型下的适配实验，不是对已发布数值的复现。**

模型配置中有一项必须记录：该模型为重推理模型，在默认 1024 token 预算下会把全部预算消耗在隐藏推理字段上，可见输出为空且 `finish_reason=length`（实测 8 次调用仅 1 次可用）。本项目将 `max_completion_tokens` 提高到 8192（实测 6/6 成功）。未报告该设置时，同一模型的评测结果无法复现。

### 5.3 级联的复现方式

论文主推架构 `cascade_db_diagnosis` 的端到端重跑在本环境需约四小时，且绝大部分时间花在确定性的第一阶段。由于第一阶段给定其磁盘缓存后是可重复的，本项目采取**从已保存的第一阶段输出重建级联**（`exp2b_cascade_from_stage1.py`）：

1. 读取第一阶段的逐条目预测与状态；
2. 按上游 `ROUTE_TO_STAGE2` 状态集合（**直接导入上游模块**，而非复制词表）划分为 627 条由第一阶段解决、204 条延迟到第二阶段（131 条 `api_error` + 73 条 `unconfirmed`）；
3. 只对这 204 条运行第二阶段模型（零样本判定提示，204 条约 18 分钟）；
4. 按上游规则合并，并在两种计分立场下评分。

**路由规则与合并逻辑取自上游；第二阶段模型是替换的**，且未使用工具增强——第二阶段的工具正是本环境中退化的那些来源，给模型返回 429 的工具测的是故障而非方法。因此级联数字是**适配结果**，与发布值并列报告而不作为其复现。

### 5.4 子样本使用

Semantic Scholar 的 10 次/分钟配速使多来源基线的全量运行需要约三小时。按课程要求（允许缩小复现范围但须说明），本项目对多来源基线使用**冻结的分层子样本**：

- 抽样规则：按（标签，幻觉类型）比例分层；同层内按 `bibtex_key` 排序后以固定种子 `20261018` 打乱抽取
- 样本定义与组成分布：`results/samples/sample_<split>_<n>_20261018.json`
- 规模：多来源确定性基线 300 条；LLM 基线 200 条
- 规则在任何模型输出产生之前冻结，样本 ID 可审计

单来源基线（`doi_only` 系列、`doi_presence_heuristic`、常量参照、随机参照）与 Stage 1 在**完整划分**上运行。

### 5.5 评价协议

- 评测脚本：上游 `hallmark.evaluation.metrics.evaluate`，未作修改
- 评测基准年份：固定为 2026（`REFERENCE_YEAR`），保证未来日期判定的可重复性
- 计分立场：默认 `conservative`（UNCERTAIN 排除在混淆矩阵之外，同时报告覆盖率）；Stage 1 同时报告 `aggressive`（UNCERTAIN 按 HALLUCINATED@0.55 处理）
- 信息泄漏防护：只向基线传递 `BlindEntry`（剥离 `label`、`hallucination_type`、`difficulty_tier`、`explanation`、`subtests`、`url` 等字段）；不使用数据文件中的历史预测
- 随机种子：随机基线 42；子样本 20261018；bootstrap 置信区间 20261018

### 5.6 执行器的错误处理

上游 `parallel_run_baseline` 会让单条目的异常传播出线程池并中止整轮。在复现环境的网络条件下（doi.org 连接被间歇性重置）这会导致整轮丢失，因此本项目实现了 `parallel_runner.py`：对每条目做错误隔离，重试耗尽后记为拒答（`UNCERTAIN`，`evaluated=False`）并继续。**拒答条目在指标文件中单独计数**（`num_uncertain`、`num_error_fallbacks`），不参与分类指标，覆盖率同时报告。

---

## 六、结果文件索引

| 文件 | 内容 |
|---|---|
| `results/audit/dataset_audit.json` | 三个划分的标签、类型、难度、生成方式分布；子测试覆盖；跨划分重叠；完整性检查 |
| `results/metrics/*.json` | 每个基线在每个划分上的完整指标（含 per-tier、per-type、per-generation-method 分解） |
| `results/subtests/subtest_offline.json` | 六个子测试作为检测器的精确率/召回率/F1/覆盖率（标注层面） |
| `results/subtests/subtest_live_summary.json` | 实时推导子测试与标注的一致率、来源可用性、实时检测器指标 |
| `results/subtests/subtest_live_records.jsonl` | 180 条子样本的逐条对比记录 |
| `results/comparison/reproduction_agreement.json` | 与仓库 `data/v1.2/baseline_results/` 的逐指标比对 |
| `results/cascade/cascade_recon_summary__test_public.json` | 重建级联的保守/激进两立场汇总 |
| `results/cases/cases.json` / `cases.md` | 代表性案例（含各基线判定与理由） |
| `figures/*.png` / `*.svg` | 论文图表 |

---

## 七、已知局限

1. **实测层面的子测试使用自行实现的元数据获取逻辑**（CrossRef + OpenAlex 直连），而非 `bibtex-check` 的内部路径。因此一致率度量的是「用本项目的获取逻辑重新推导子测试」与标注的一致程度，其中同时包含标注的不稳定性与本项目实现差异。
2. **DBLP 不可用使 `venue_correct` 与 `cross_db_agreement` 的低一致率无法完全归因**——无法在「来源不可用」与「判定逻辑脆弱」之间分离。已在论文中明确标注。
3. **LLM 结果来自单一替代模型与单一网关**，不能推广到已发布模型的性能。
4. **Stage 1 数字在来源不完整条件下测得**，与健康网络下的数值不可直接比较。
5. **子样本指标与全量划分指标不可直接比较**；小样本的置信区间更宽。
6. 本项目**不声称实现了自动证据检索**，也不声称完成了论断与原文证据的语义对齐。调研报告覆盖了证据对齐路线，但实验部分明确限定在书目真实性核验。
