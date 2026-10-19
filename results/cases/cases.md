# 代表性案例分析（自动抽取）

参考基线：`hallucitechecker`。每个单元格（结果 × 错误类型 × 难度层）抽取一例；
同一引文列出全部基线的判定与理由，便于横向比较。

## FP-VALID-a337fdfa

- 真值：**VALID**
- 生成方式：scraped；来源：None
- 参考基线上的结果：FP

**书目字段**

| 字段 | 值 |
|---|---|
| title | `Towards Rigorous Interpretations: a Formalisation of Feature Attribution` |
| author | `Darius Afchar and Vincent Guigue and Romain Hennequin` |
| year | `2021` |
| booktitle | `ICML` |

**标注的子测试结果**：{"doi_resolves": null, "title_exists": true, "authors_match": true, "fields_complete": true, "cross_db_agreement": true, "venue_correct": true}

**标注说明**：Valid entry scraped from DBLP and verified

**各基线判定**

| 基线 | 判定 | 置信度 | 理由 |
|---|---|---|---|
| doi_presence_heuristic | HALLUCINATED | 0.8 | No DOI field present (heuristic shortcut) |
| doi_only | VALID | 0.5 | No DOI field present |
| hallucitechecker | HALLUCINATED | 0.6 | No title match across ['crossref', 'arxiv'] (max similarity=0.661 < 0.90) |
| bibtexupdater | HALLUCINATED | 0.638138 | Status: title_mismatch; Mismatched: ['title', 'venue']; Unconfirmed (not compared): ['author']; Errors: ['DBLP: dblp dblp.org lookup did not complete: HTTP 202', 'OpenReview: openreview api2.openreview.net lookup did not |

## FN-near_miss_title-0cb3d100

- 真值：**HALLUCINATED**（near_miss_title，tier 3）
- 生成方式：perturbation；来源：None
- 参考基线上的结果：FN

**书目字段**

| 字段 | 值 |
|---|---|
| title | `Neutral Prompts, Non-Neutral People: Quantifying Gender and Skin-Tone Bias in Gemini Flash 2.5 Image and GPT Visual 1.5` |
| author | `Roberto Balestri` |
| year | `2026` |
| doi | `10.48550/arXiv.2602.12133v1` |

**标注的子测试结果**：{"doi_resolves": true, "title_exists": false, "authors_match": true, "venue_correct": true, "fields_complete": true, "cross_db_agreement": false}

**标注说明**：Title slightly modified: 'Neutral Prompts, Non-Neutral People: Quantifying Gender and Skin-Tone Bias in Gemini Flash 2.5 Image and GPT Visual 1.5' (original: 'Neutral Prompts, Non-Neutral People: Quantifying Gender and Skin-Tone Bias in Gemini Flash 2.5 Image and GPT Image 1.5')

**各基线判定**

| 基线 | 判定 | 置信度 | 理由 |
|---|---|---|---|
| doi_presence_heuristic | VALID | 0.6 | DOI field present (heuristic shortcut) |
| doi_only | HALLUCINATED | 0.75 | DOI returns HTTP 404 at doi.org |
| hallucitechecker | VALID | 0.85 | Title match in arxiv (similarity=0.963, threshold=0.90): 'Neutral Prompts, Non-Neutral People: Quantifying Gender and Skin-Tone Bias in Gemini Flash 2.5 Image and GPT Image 1.5' |
| bibtexupdater | HALLUCINATED | 0.612112 | Status: title_mismatch; Mismatched: ['title']; Errors: ['DBLP: dblp dblp.org lookup did not complete: HTTP 202', 'OpenReview: openreview api2.openreview.net lookup did not complete: challenge-gated; no credentials config |

## TP-hybrid_fabrication-a73d7564

- 真值：**HALLUCINATED**（hybrid_fabrication，tier 2）
- 生成方式：adversarial；来源：perturbation_scaleup
- 参考基线上的结果：TP

**书目字段**

| 字段 | 值 |
|---|---|
| title | `Forward Compatible Few-Shot Efficient training` |
| author | `David Okonkwo and Laura Fischer and Wei-Ting Hsu` |
| year | `2022` |
| doi | `10.1109/CVPR52688.2022.00884` |
| booktitle | `CVPR` |

**标注的子测试结果**：{"doi_resolves": true, "title_exists": false, "authors_match": false, "fields_complete": true, "cross_db_agreement": false, "venue_correct": true}

**标注说明**：Real DOI with fabricated authors and modified title

**各基线判定**

| 基线 | 判定 | 置信度 | 理由 |
|---|---|---|---|
| doi_presence_heuristic | VALID | 0.6 | DOI field present (heuristic shortcut) |
| doi_only | VALID | 0.5 | indeterminate \| DOI returned HTTP 202 (indeterminate) |
| hallucitechecker | HALLUCINATED | 0.6 | No title match across ['crossref', 'arxiv'] (max similarity=0.764 < 0.90) |
| bibtexupdater | HALLUCINATED | 0.5 | Status: author_mismatch; Mismatched: ['title', 'author']; Errors: ["DOI 10.1109/CVPR52688.2022.00884 resolves to the cited paper 'Forward Compatible Few-Shot Class-Incremental Learning', but the entry's authors do not ma |

## FN-hybrid_fabrication-e8e1379d

- 真值：**HALLUCINATED**（hybrid_fabrication，tier 2）
- 生成方式：llm_generated；来源：llm_generated
- 参考基线上的结果：FN

**书目字段**

| 字段 | 值 |
|---|---|
| title | `Masked Autoencoders Are Scalable Vision Learners` |
| author | `Kaiming He and Xinlei Chen and Saining Xie and Yanghao Li and Piotr Doll{\'a}r and Ross Girshick` |
| booktitle | `CVPR` |
| year | `2022` |
| doi | `10.1109/CVPR52688.2022.01552` |

**标注的子测试结果**：{"doi_resolves": true, "title_exists": false, "authors_match": false, "venue_correct": true, "fields_complete": true, "cross_db_agreement": false}

**标注说明**：MAE (CVPR 2022); cited DOI 10.1109/CVPR52688.2022.01552 is 'Motion-from-Blur: 3D Shape and Motion Estimation of Motion-blurred Objects in Videos' (MAE is .01553).

**各基线判定**

| 基线 | 判定 | 置信度 | 理由 |
|---|---|---|---|
| doi_presence_heuristic | VALID | 0.6 | DOI field present (heuristic shortcut) |
| doi_only | VALID | 0.5 | indeterminate \| DOI returned HTTP 202 (indeterminate) |
| hallucitechecker | VALID | 0.85 | Title match in crossref (similarity=1.000, threshold=0.90): 'Masked Autoencoders Are Scalable Vision Learners' |
| bibtexupdater | HALLUCINATED | 0.5 | Status: doi_mismatch; Errors: ["DOI 10.1109/CVPR52688.2022.01552 resolves to 'Motion-from-Blur: 3D Shape and Motion Estimation of Motion-blurred Objects in Videos', which does not match entry title 'Masked Autoencoders A |

## TP-fabricated_doi-cea852a4

- 真值：**HALLUCINATED**（fabricated_doi，tier 1）
- 生成方式：perturbation；来源：perturbation_scaleup
- 参考基线上的结果：TP

**书目字段**

| 字段 | 值 |
|---|---|
| title | `Spherical Message Passing for 3D Molecular Graphs` |
| author | `Yi Liu and Limei Wang and Meng Liu and Yuchao Lin and Xuan Zhang and Bora Oztekin and Shuiwang Ji` |
| year | `2022` |
| booktitle | `ICLR` |
| doi | `10.55910/mbwo.6329160` |

**标注的子测试结果**：{"doi_resolves": false, "title_exists": true, "authors_match": true, "fields_complete": true, "cross_db_agreement": false, "venue_correct": true}

**标注说明**：DOI fabricated: 10.55910/mbwo.6329160 does not resolve

**各基线判定**

| 基线 | 判定 | 置信度 | 理由 |
|---|---|---|---|
| doi_presence_heuristic | VALID | 0.6 | DOI field present (heuristic shortcut) |
| doi_only | HALLUCINATED | 0.85 | DOI returns HTTP 404 at doi.org \| [Pre-screening confirms] DOI 10.55910/mbwo.6329160 returns 404 at doi.org |
| hallucitechecker | HALLUCINATED | 0.6 | No title match across ['crossref', 'arxiv'] (max similarity=0.810 < 0.90) |
| bibtexupdater | HALLUCINATED | 0.85 | Status: doi_not_found; Errors: ['DOI does not resolve: 10.55910/mbwo.6329160'] \| [Pre-screening confirms] DOI 10.55910/mbwo.6329160 returns 404 at doi.org |

## FN-fabricated_doi-aa79e4b0

- 真值：**HALLUCINATED**（fabricated_doi，tier 1）
- 生成方式：perturbation；来源：perturbation_scaleup
- 参考基线上的结果：FN

**书目字段**

| 字段 | 值 |
|---|---|
| title | `Intelligent Online Selling Point Extraction for E-commerce Recommendation` |
| author | `Xiaojie Guo and Shugen Wang and Hanqing Zhao and Shiliang Diao and Jiajia Chen and Zhuoye Ding and Zhen He and Jianchao Lu and Yun Xiao and Bo Long and Han Yu and Lingfei Wu` |
| year | `2022` |
| doi | `10.88882/9q1cuf3v1s` |
| booktitle | `AAAI` |

**标注的子测试结果**：{"doi_resolves": false, "title_exists": true, "authors_match": true, "fields_complete": true, "cross_db_agreement": false, "venue_correct": true}

**标注说明**：DOI fabricated: 10.88882/9q1cuf3v1s does not resolve

**各基线判定**

| 基线 | 判定 | 置信度 | 理由 |
|---|---|---|---|
| doi_presence_heuristic | VALID | 0.6 | DOI field present (heuristic shortcut) |
| doi_only | HALLUCINATED | 0.85 | DOI returns HTTP 404 at doi.org \| [Pre-screening confirms] DOI 10.88882/9q1cuf3v1s returns 404 at doi.org |
| hallucitechecker | VALID | 0.85 | Title match in crossref (similarity=0.909, threshold=0.90): 'Intelligent online selling point extraction and generation for e‐commerce recommendation' |
| bibtexupdater | HALLUCINATED | 0.85 | Status: doi_not_found; Errors: ['DOI does not resolve: 10.88882/9q1cuf3v1s'] \| [Pre-screening confirms] DOI 10.88882/9q1cuf3v1s returns 404 at doi.org |

## TP-chimeric_title-abeeb4b8

- 真值：**HALLUCINATED**（chimeric_title，tier 2）
- 生成方式：perturbation；来源：perturbation_scaleup
- 参考基线上的结果：TP

**书目字段**

| 字段 | 值 |
|---|---|
| title | `Curriculum Learning for Complex Task Training` |
| author | `Anurag Ajay and Aviral Kumar and Pulkit Agrawal and Sergey Levine and Ofir Nachum` |
| year | `2021` |
| booktitle | `ICLR` |

**标注的子测试结果**：{"doi_resolves": null, "title_exists": false, "authors_match": true, "fields_complete": true, "cross_db_agreement": false, "venue_correct": true}

**标注说明**：Title 'Curriculum Learning for Complex Task Training' is fabricated; authors are real

**各基线判定**

| 基线 | 判定 | 置信度 | 理由 |
|---|---|---|---|
| doi_presence_heuristic | HALLUCINATED | 0.8 | No DOI field present (heuristic shortcut) |
| doi_only | VALID | 0.5 | No DOI field present |
| hallucitechecker | HALLUCINATED | 0.6 | No title match across ['crossref', 'arxiv'] (max similarity=0.600 < 0.90) |
| bibtexupdater | UNCERTAIN | 0.5 | Status: api_error; Abstention: the source lookup failed (API error), so this is not a verdict; Mismatched: ['title', 'author', 'year', 'venue']; Errors: ['DBLP: dblp dblp.org lookup did not complete: Retryable status', ' |

## TP-wrong_venue-b79b4a67

- 真值：**HALLUCINATED**（wrong_venue，tier 2）
- 生成方式：perturbation；来源：perturbation_scaleup
- 参考基线上的结果：TP

**书目字段**

| 字段 | 值 |
|---|---|
| title | `simpleKT: A Simple But Tough-to-Beat Baseline for Knowledge Tracing` |
| author | `Zitao Liu and Qiongqiong Liu and Jiahao Chen and Shuyan Huang and Weiqi Luo` |
| year | `2023` |
| booktitle | `EMNLP` |

**标注的子测试结果**：{"doi_resolves": null, "title_exists": true, "authors_match": true, "fields_complete": true, "cross_db_agreement": false, "venue_correct": false}

**标注说明**：Venue changed to 'EMNLP' (original was different)

**各基线判定**

| 基线 | 判定 | 置信度 | 理由 |
|---|---|---|---|
| doi_presence_heuristic | HALLUCINATED | 0.8 | No DOI field present (heuristic shortcut) |
| doi_only | VALID | 0.5 | No DOI field present |
| hallucitechecker | HALLUCINATED | 0.6 | No title match across ['crossref', 'arxiv'] (max similarity=0.672 < 0.90) |
| bibtexupdater | HALLUCINATED | 0.67589 | Status: given_name_substitution; Mismatched: ['author']; Unconfirmed (not compared): ['venue']; Errors: ['DBLP: dblp dblp.org lookup did not complete: HTTP 202', 'OpenReview: openreview api2.openreview.net lookup did not |

## FN-wrong_venue-7ee3e320

- 真值：**HALLUCINATED**（wrong_venue，tier 2）
- 生成方式：perturbation；来源：None
- 参考基线上的结果：FN

**书目字段**

| 字段 | 值 |
|---|---|
| title | `Tiny Recursive Reasoning with Mamba-2 Attention Hybrid` |
| author | `Wenlong Wang and Fergal Reid` |
| year | `2026` |
| doi | `10.48550/arXiv.2602.12078v1` |
| booktitle | `NeurIPS` |

**标注的子测试结果**：{"doi_resolves": true, "title_exists": true, "authors_match": true, "venue_correct": false, "fields_complete": true, "cross_db_agreement": false}

**标注说明**：Venue changed to 'NeurIPS' (original was different)

**各基线判定**

| 基线 | 判定 | 置信度 | 理由 |
|---|---|---|---|
| doi_presence_heuristic | VALID | 0.6 | DOI field present (heuristic shortcut) |
| doi_only | HALLUCINATED | 0.75 | DOI returns HTTP 404 at doi.org |
| hallucitechecker | VALID | 0.85 | Title match in arxiv (similarity=1.000, threshold=0.90): 'Tiny Recursive Reasoning with Mamba-2 Attention Hybrid' |
| bibtexupdater | UNCERTAIN | 0.5 | Status: unconfirmed; Abstention: a record was found but a claimed field could not be confirmed against any source, so this is not a verdict; Unconfirmed (not compared): ['venue']; Errors: ['DBLP: dblp dblp.org lookup did |

## TP-preprint_as_published-a641868c

- 真值：**HALLUCINATED**（preprint_as_published，tier 2）
- 生成方式：perturbation；来源：perturbation_scaleup
- 参考基线上的结果：TP

**书目字段**

| 字段 | 值 |
|---|---|
| title | `Spherical Message Passing for 3D Molecular Graphs` |
| author | `Yi Liu and Limei Wang and Meng Liu and Yuchao Lin and Xuan Zhang and Bora Oztekin and Shuiwang Ji` |
| year | `2022` |
| booktitle | `ACL` |

**标注的子测试结果**：{"doi_resolves": null, "title_exists": true, "authors_match": true, "fields_complete": true, "cross_db_agreement": false, "venue_correct": false}

**标注说明**：Preprint falsely cited as published at 'ACL'

**各基线判定**

| 基线 | 判定 | 置信度 | 理由 |
|---|---|---|---|
| doi_presence_heuristic | HALLUCINATED | 0.8 | No DOI field present (heuristic shortcut) |
| doi_only | VALID | 0.5 | No DOI field present |
| hallucitechecker | HALLUCINATED | 0.6 | No title match across ['crossref', 'arxiv'] (max similarity=0.810 < 0.90) |
| bibtexupdater | HALLUCINATED | 0.638138 | Status: title_mismatch; Mismatched: ['title', 'author', 'venue']; Errors: ['DBLP: dblp dblp.org lookup did not complete: HTTP 202', 'OpenReview: openreview api2.openreview.net lookup did not complete: challenge-gated; no |

## FN-preprint_as_published-b90a5e9e

- 真值：**HALLUCINATED**（preprint_as_published，tier 2）
- 生成方式：perturbation；来源：perturbation_scaleup
- 参考基线上的结果：FN

**书目字段**

| 字段 | 值 |
|---|---|
| title | `Learning to Search Feasible and Infeasible Regions of Routing Problems with Flexible Neural k-Opt` |
| author | `Yining Ma and Zhiguang Cao and Yeow Meng Chee` |
| year | `2023` |
| booktitle | `WWW` |

**标注的子测试结果**：{"doi_resolves": null, "title_exists": true, "authors_match": true, "fields_complete": true, "cross_db_agreement": false, "venue_correct": false}

**标注说明**：Preprint falsely cited as published at 'WWW'

**各基线判定**

| 基线 | 判定 | 置信度 | 理由 |
|---|---|---|---|
| doi_presence_heuristic | HALLUCINATED | 0.8 | No DOI field present (heuristic shortcut) |
| doi_only | VALID | 0.5 | No DOI field present |
| hallucitechecker | VALID | 0.85 | Title match in crossref (similarity=1.000, threshold=0.90): 'Learning to Search Feasible and Infeasible Regions of Routing Problems with Flexible Neural k-Opt' |
| bibtexupdater | HALLUCINATED | 0.6105104 | Status: venue_mismatch; Mismatched: ['venue']; Errors: ['DBLP: dblp dblp.org lookup did not complete: HTTP 202', 'OpenReview: openreview api2.openreview.net lookup did not complete: challenge-gated; no credentials config |

## TP-swapped_authors-ac682a14

- 真值：**HALLUCINATED**（swapped_authors，tier 2）
- 生成方式：perturbation；来源：perturbation_scaleup
- 参考基线上的结果：TP

**书目字段**

| 字段 | 值 |
|---|---|
| title | `Representation Balancing Offline Model-based Reinforcement Learning` |
| author | `Ye Yuan and Yuda Song and Zhengyi Luo and Wen Sun and Kris M. Kitani` |
| year | `2021` |
| booktitle | `ICLR` |

**标注的子测试结果**：{"doi_resolves": null, "title_exists": true, "authors_match": false, "fields_complete": true, "cross_db_agreement": false, "venue_correct": true}

**标注说明**：Authors swapped from '00072022transform2act:'

**各基线判定**

| 基线 | 判定 | 置信度 | 理由 |
|---|---|---|---|
| doi_presence_heuristic | HALLUCINATED | 0.8 | No DOI field present (heuristic shortcut) |
| doi_only | VALID | 0.5 | No DOI field present |
| hallucitechecker | HALLUCINATED | 0.6 | No title match across ['crossref', 'arxiv'] (max similarity=0.784 < 0.90) |
| bibtexupdater | HALLUCINATED | 0.639425 | Status: title_mismatch; Mismatched: ['title', 'author', 'year', 'venue']; Errors: ['DBLP: dblp dblp.org lookup did not complete: HTTP 202', 'OpenReview: openreview api2.openreview.net lookup did not complete: challenge-g |

## FN-swapped_authors-a4820127

- 真值：**HALLUCINATED**（swapped_authors，tier 2）
- 生成方式：real_world；来源：gptzero_neurips2025
- 参考基线上的结果：FN

**书目字段**

| 字段 | 值 |
|---|---|
| author | `Junyeong Lee and Yiseong Kim and Seungju Park and Hyunjik Lee` |
| title | `Softmatch: Addressing the quantity-quality trade-off in semi-supervised learning` |
| year | `2023` |

**标注的子测试结果**：{"doi_resolves": null, "title_exists": true, "authors_match": false, "venue_correct": true, "fields_complete": true, "cross_db_agreement": false}

**标注说明**：Real-world hallucination from NeurIPS 2025 accepted paper 'Robust Label Proportions Learning'. Found by GPTZero analysis (scan type: Scan  AI*). Comment: Title matches this paper. No match in NeurIPS volume 36.. URL: https://gptzero.me/news/neurips/

**各基线判定**

| 基线 | 判定 | 置信度 | 理由 |
|---|---|---|---|
| doi_presence_heuristic | HALLUCINATED | 0.8 | No DOI field present (heuristic shortcut) |
| doi_only | VALID | 0.5 | No DOI field present |
| hallucitechecker | VALID | 0.85 | Title match in arxiv (similarity=1.000, threshold=0.90): 'SoftMatch: Addressing the Quantity-Quality Trade-off in Semi-supervised Learning' |
| bibtexupdater | HALLUCINATED | 0.638138 | Status: title_mismatch; Mismatched: ['title', 'author', 'year']; Errors: ['DBLP: dblp dblp.org lookup did not complete: HTTP 202', 'OpenReview: openreview api2.openreview.net lookup did not complete: challenge-gated; no  |

## TP-nonexistent_venue-b8df2054

- 真值：**HALLUCINATED**（nonexistent_venue，tier 1）
- 生成方式：perturbation；来源：perturbation_scaleup
- 参考基线上的结果：TP

**书目字段**

| 字段 | 值 |
|---|---|
| title | `Are Neural Rankers still Outperformed by Gradient Boosted Decision Trees?` |
| author | `Zhen Qin and Le Yan and Honglei Zhuang and Yi Tay and Rama Kumar Pasumarthi and Xuanhui Wang and Michael Bendersky and Marc Najork` |
| year | `2021` |
| booktitle | `International Journal of Context Learning` |

**标注的子测试结果**：{"doi_resolves": null, "title_exists": true, "authors_match": true, "fields_complete": true, "cross_db_agreement": false, "venue_correct": false}

**标注说明**：Venue fabricated: 'International Journal of Context Learning' does not exist

**各基线判定**

| 基线 | 判定 | 置信度 | 理由 |
|---|---|---|---|
| doi_presence_heuristic | HALLUCINATED | 0.8 | No DOI field present (heuristic shortcut) |
| doi_only | VALID | 0.5 | No DOI field present |
| hallucitechecker | HALLUCINATED | 0.6 | No title match across ['crossref', 'arxiv'] (max similarity=0.661 < 0.90) |
| bibtexupdater | UNCERTAIN | 0.5 | Status: api_error; Abstention: the source lookup failed (API error), so this is not a verdict; Mismatched: ['title', 'author']; Unconfirmed (not compared): ['venue']; Errors: ['DBLP: dblp dblp.org lookup did not complete |

## FN-nonexistent_venue-72f55675

- 真值：**HALLUCINATED**（nonexistent_venue，tier 1）
- 生成方式：perturbation；来源：None
- 参考基线上的结果：FN

**书目字段**

| 字段 | 值 |
|---|---|
| title | `Pedagogically-Inspired Data Synthesis for Language Model Knowledge Distillation` |
| author | `Bowei He and Yankai Chen and Xiaokun Zhang and Linghe Kong and Philip S. Yu and Xue Liu and Chen Ma` |
| year | `2026` |
| doi | `10.48550/arXiv.2602.12172v1` |
| journal | `Symposium on Regularization Techniques` |

**标注的子测试结果**：{"doi_resolves": true, "title_exists": true, "authors_match": true, "venue_correct": false, "fields_complete": true, "cross_db_agreement": false}

**标注说明**：Venue fabricated: 'Symposium on Regularization Techniques' does not exist

**各基线判定**

| 基线 | 判定 | 置信度 | 理由 |
|---|---|---|---|
| doi_presence_heuristic | VALID | 0.6 | DOI field present (heuristic shortcut) |
| doi_only | HALLUCINATED | 0.75 | DOI returns HTTP 404 at doi.org |
| hallucitechecker | VALID | 0.85 | Title match in arxiv (similarity=1.000, threshold=0.90): 'Pedagogically-Inspired Data Synthesis for Language Model Knowledge Distillation' |
| bibtexupdater | UNCERTAIN | 0.5 | Status: unconfirmed; Abstention: a record was found but a claimed field could not be confirmed against any source, so this is not a verdict; Unconfirmed (not compared): ['venue']; Errors: ['DBLP: dblp dblp.org lookup did |

## TP-future_date-cc62d714

- 真值：**HALLUCINATED**（future_date，tier 1）
- 生成方式：perturbation；来源：perturbation_scaleup
- 参考基线上的结果：TP

**书目字段**

| 字段 | 值 |
|---|---|
| title | `SCoRe: Pre-Training for Context Representation in Conversational Semantic Parsing` |
| author | `Tao Yu and Rui Zhang and Alex Polozov and Christopher Meek and Ahmed Hassan Awadallah` |
| year | `2034` |
| booktitle | `ICLR` |

**标注的子测试结果**：{"doi_resolves": null, "title_exists": true, "authors_match": true, "fields_complete": true, "cross_db_agreement": false, "venue_correct": true}

**标注说明**：Publication year 2034 is in the future

**各基线判定**

| 基线 | 判定 | 置信度 | 理由 |
|---|---|---|---|
| doi_presence_heuristic | HALLUCINATED | 0.8 | No DOI field present (heuristic shortcut) |
| doi_only | HALLUCINATED | 0.95 | No DOI field present \| [Pre-screening override] Publication year 2034 is in the future |
| hallucitechecker | HALLUCINATED | 0.6 | No title match across ['crossref', 'arxiv'] (max similarity=0.555 < 0.90) |
| bibtexupdater | HALLUCINATED | 0.95 | Status: future_date; Errors: ['Year validation failed: 2034'] \| [Pre-screening confirms] Publication year 2034 is in the future |
