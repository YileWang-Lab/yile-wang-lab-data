# 中国现代化进程的多维评估

![论文首页](../assets/covers/hybrid-pca-stacking.jpg)

## 论文信息

| 项目 | 内容 |
| --- | --- |
| 英文题目 | *A Hybrid PCA-Stacking Framework for Multidimensional Assessment of Development Trajectories: Evidence from China's Modernization Process* |
| 作者 | Hanrui Wang、Yile Wang |
| 来源 | *Frontiers in Economics and Management*, 1(1) |
| 年份 | 2020 |
| 页数 | 9 页 |

[打开或下载 PDF 原文](../assets/papers/hybrid-pca-stacking.pdf)

## 研究问题

单一 GDP 指标无法同时反映经济基础、创新教育、公共治理与可持续转型。论文试图回答：如何建立一个能够跨时期比较中国发展轨迹的多维指数？如何预测缺失或未来指标？如何根据数据而不是主观分期识别现代化阶段？

## 方法框架

1. 从经济、社会与治理领域选取 14 项指标并进行标准化；
2. 使用主成分分析提炼共同变化结构，降低指标冗余；
3. 以 NAR 神经网络预测二级指标，以线性回归、KNN 和随机森林构成 Stacking 回归器预测主要指标；
4. 使用熵权—变异系数组合方法合成中国发展指数（CDI）；
5. 结合 LightGBM、XGBoost 与 SVM 的 Stacking 分类模型识别发展阶段。

## 核心发现

- 两个主成分累计解释 94.39% 的系统方差。其中，创新—教育—治理组合是最主要的变化维度，经济基本面构成第二维度。
- NAR 网络在时间序列预测中取得较低误差；Stacking 模型相较单一预测器进一步降低均方误差。
- CDI 将长期发展划分为建国、改革与现代化三个阶段，并显示 2000 年后综合发展速度明显提高。
- 长期预测提示发展模式将逐渐转向环境脱钩与可持续转型，但这一结论依赖指标设定和情景假设。

## 章节索引

1. Introduction
2. Literature Review
3. Core Modernization Factor Extraction
4. China Development Index Construction
5. Development Phase Identification
6. Conclusion

> **原文说明**：PCA 载荷、预测模型设定、指数计算公式和全部结果图表请查看 PDF 原文。
