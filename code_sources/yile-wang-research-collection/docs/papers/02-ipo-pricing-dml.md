# 投资者情绪与 IPO 定价效率

## 论文信息

| 项目 | 内容 |
| --- | --- |
| 英文题目 | *Research on the Impact of Investor Sentiment on IPO Pricing Efficiency Based on Double Machine Learning* |
| 作者 | Jintai Ye、Yunshi Chen、Yile Wang |
| 类型 | 工作论文 |
| 样本 | 2019—2023 年中国 A 股 IPO |
| 页数 | 10 页 |

[下载 Word 原文](../assets/papers/ipo-pricing-dml.docx)

## 研究背景

注册制改革加深后，新股定价更加依赖市场化询价，但投资者情绪、散户交易和首日价格限制仍可能使发行价格偏离基本面。传统线性回归难以同时处理高维控制变量、非线性关系和潜在的模型设定偏误，因此论文引入因果机器学习框架。

## 变量与识别思路

- **被解释变量**：IPO 抑价率，即首日收盘价相对于发行价的超额收益，并对极端值进行处理；
- **核心解释变量**：投资者情绪综合指数，结合新闻情绪、换手率、融资余额等信息，并使用 PCA 提取共同成分；
- **控制变量**：企业规模、资产负债率、净资产收益率、成长性、每股收益、发行市盈率和发行规模等；
- **识别方法**：双重机器学习通过交叉拟合估计干扰函数，再对残差化后的处理变量和结果变量进行正交估计；广义随机森林用于刻画个体处理效应差异。

## 研究假设

1. 投资者情绪显著提高 IPO 抑价率；
2. 发行规模通过稀释情绪交易的价格冲击，负向调节情绪效应；
3. 首日涨跌幅限制延迟价格发现，从而放大情绪对抑价率的影响。

## 核心发现

- 投资者情绪对 IPO 抑价具有显著正向影响，多种敏感性和稳健性检验支持这一结果。
- 小规模发行更容易受到情绪驱动的错误定价影响；大规模发行的机构参与度和流动性更高，定价相对稳定。
- 发行市盈率表现为倒 U 型异质性：中等估值区间内的情绪影响最强。
- 低盈利或亏损企业对情绪更加敏感，盈利能力增强会降低情绪的边际影响。

## 章节索引

1. Introduction
2. Literature Review
3. Theoretical Analysis and Research Hypotheses
4. Research Design
5. Empirical Analysis and Heterogeneity
6. Conclusions and Implications

> **原文说明**：Word 原文包含 DML 与 GRF 的完整公式、变量表、模型结果图以及稳健性检验，请下载原文件查看。
