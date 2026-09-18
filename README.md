# Yile-Wang Lab Data Hub

面向经济学、金融工程与机器学习研究的双语数据与代码仓库。这里保存的是**可以被课题组成员继续复用、检查和追溯**的研究资料：标准化数据、原始来源线索、字段字典、清洗脚本、代码快照和质量审计记录。

> **Repository status**: Public · main · Last verified: 2026-09-18 (UTC)

本仓库不是把不同项目的文件简单堆在一起，也不是把所有文件强行拼成一张“大面板”。不同数据集的统计口径、频率、实体编码和授权条件并不相同，因此每个数据集都保留自己的来源、时间覆盖和处理记录。使用者应先查目录和审计文件，再决定如何合并或建模。

## 这份仓库现在包含什么

当前整理快照的规模如下。数量由仓库内的机器可读清单生成，后续更新时会随文件变化而变化。

| 内容 | 数量/状态 | 说明 |
|---|---:|---|
| 英文标准数据文件 | 244 | 变量名采用稳定的 ASCII 风格，适合 Python、R、Stata 和 SQL |
| 中文数据文件 | 244 | 保留原始中文字段或中文标准字段，便于核对来源和教学使用 |
| 处理后数据总行数 | 172,420 | 以 metadata/quality_report.json 的最近一次质量报告为准 |
| 字段字典记录 | 5,963 | 英文变量名、中文字段名、含义、单位和来源字段的对应关系 |
| 可复用数据集登记 | 243 | 每个条目包含文件路径、来源、时间信号和覆盖状态 |
| 代码文件 | 435 | Python、R、Stata、MATLAB 等研究代码和实验脚本 |
| 自动更新数据源 | 1 | 世界银行官方 API：GDP（现价美元） |

## 目录结构

~~~text
.
├── data_processed/
│   ├── english/          # 英文标准字段数据
│   └── chinese/          # 中文字段数据
├── data_raw/             # 可公开保留的原始或 API 导出数据
├── code_sources/         # 从个人仓库整理的可复用代码快照
├── metadata/             # 清单、字段字典、覆盖范围、质量和来源审计
├── scripts/              # 下载、更新、清洗和审计脚本
├── docs/                 # 来源核查、研究主题和使用说明
└── examples/             # 可继续补充的读取、合并和回归示例
~~~

source_snapshots/ 只在本地作为溯源材料保留，没有整体公开上传。它包含重复的原始工作簿、较大的中间文件以及需要逐项确认再分发权限的内容。公开仓库优先提供经过整理的结果、字段映射和可重跑的代码，避免把不必要的副本和未经核验的受限文件直接发布出去。

## 从哪里开始使用

如果你第一次进入这个仓库，建议按下面的顺序查找数据：

1. 打开 [metadata/usable_dataset_index_bilingual.csv](metadata/usable_dataset_index_bilingual.csv)，按主题、文件路径和可用状态筛选数据集。
2. 用 [metadata/field_dictionary_complete_bilingual.csv](metadata/field_dictionary_complete_bilingual.csv) 查每个变量的英文名、中文名、定义、单位和来源。
3. 用 [metadata/data_coverage_audit_bilingual.csv](metadata/data_coverage_audit_bilingual.csv) 确认文件中真实出现的起止年份；不要只根据文件名判断年份。
4. 阅读 [docs/SOURCE_AUDIT.md](docs/SOURCE_AUDIT.md)，确认数据能否公开再分发、来源是否需要进一步核对，以及哪些数据可以自动更新。
5. 再进入 data_processed/english/ 或 data_processed/chinese/ 读取文件；同一数据集的双语文件使用相同的主体名称和不同的语言后缀。

## 双语字段规则

处理后的数据尽量同时满足“机器能稳定读取”和“研究者能看懂核对”两个要求。英文标准字段遵循小写、下划线分隔、避免空格和标点的规则；中文文件保留原始中文列名或对应的中文标准名。字段字典是两套字段之间的桥梁，而不是另起一套无法追溯的变量命名。

常用审计字段如下：

| English field | 中文字段 | 用途 |
|---|---|---|
| entity_id | 个体编号 | 省份、城市、公司、国家或金融资产的稳定编码 |
| entity_name | 个体名称 | 便于阅读和人工核对的名称 |
| date | 观测日期 | 统一采用 ISO 日期格式 YYYY-MM-DD |
| year | 年份 | 年度观测或从日期提取的年度索引 |
| frequency | 频率 | daily、monthly、quarterly、annual 等 |
| variable | 指标英文名 | 可用于程序和模型公式的变量代码 |
| variable_cn | 指标中文名 | 变量的中文解释 |
| value | 数值 | 原始值或明确记录变换后的值 |
| unit | 单位 | 元、%、指数、吨、美元等 |
| source | 数据来源 | 机构、数据库或上游仓库名称 |
| source_url | 来源链接 | 原始下载地址或 API 查询地址 |
| release_date | 发布日期 | 数据对外发布的日期（若来源提供） |
| vintage_date | 数据版本日 | 宏观数据实时研究中用于避免前视偏差 |
| transform | 变换方式 | level、log、diff、return、winsorized 等 |
| quality_flag | 质量标记 | 缺失、异常值、修订或人工复核状态 |

并不是每个文件都包含全部审计字段。对原始来源无法提供的字段会保留空值或在字典中标注“不可得”，不会凭空补写。

## 如何读取和建模

### Python

~~~python
import pandas as pd

path = "data_processed/english/worldbank_gdp_current_usd__worldbank_en.csv"
df = pd.read_csv(path)
df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
df = df.dropna(subset=["country_code", "year", "value"])
~~~

### R

~~~r
library(readr)

df <- read_csv(
  "data_processed/english/worldbank_gdp_current_usd__worldbank_en.csv",
  show_col_types = FALSE
)
df$year <- as.integer(df$year)
~~~

### Stata

~~~stata
import delimited using "data_processed/english/worldbank_gdp_current_usd__worldbank_en.csv", clear
destring year, replace
xtset country_code year
~~~

读取后请先检查单位、频率、实体编码和缺失值，再进行 merge、滞后项、对数变换或缩尾处理。不同来源之间即使变量名称相似，也不能默认统计口径一致。

## 数据来源和核查规则

来源核查的完整说明见 [docs/SOURCE_AUDIT.md](docs/SOURCE_AUDIT.md)。机器可读的核查结果包括：

- [metadata/source_verification_bilingual.csv](metadata/source_verification_bilingual.csv)：来源、URL、核查时间、状态和授权复核提示；
- [metadata/data_coverage_audit_bilingual.csv](metadata/data_coverage_audit_bilingual.csv)：逐文件记录实际检测到的年份范围；
- [metadata/source_manifest.json](metadata/source_manifest.json)：自动更新范围和来源规则；
- [metadata/file_inventory_bilingual.csv](metadata/file_inventory_bilingual.csv)：文件级路径、类型、大小和溯源信息；
- [metadata/quality_report.json](metadata/quality_report.json)：处理后文件数量、行数和异常文件报告。

目前可以稳定自动更新的是世界银行官方 API 的 GDP（现价美元）指标。脚本每次运行时按当前年份请求 API，并记录服务器实际返回的最新有效年份；本次核查返回的最新有效年份为 **2025**。这表示源数据当前最新观测到 2025 年，并不意味着把 2026 年的值估算出来。

对于来自个人 GitHub 仓库的历史数据，仓库记录了上游路径、快照时间和文件级信息，但不把“上游仓库存在”误写成“数据可以无限制再分发”。在论文、课程材料或二次公开发布前，请按来源表逐项检查原始仓库许可证和数据提供方条款。

## “更新到最新年份”在这里是什么意思

本仓库遵守一个简单但重要的规则：**只更新来源实际发布的观测，不制造年份。**

- 有稳定公开 API 的数据：通过 scripts/update_sources.py 重新下载，并同步更新原始文件、英文文件、中文文件和审计元数据。
- 只有历史工作簿或静态快照的数据：保留源文件中真实出现的年份，并在覆盖审计中注明状态。
- 缺失年份：不使用前向填充、线性插值或文件名推断来伪造“最新值”。如果研究设计需要插值或外推，应该在论文代码中明确写出，并与原始数据分开保存。
- 数据修订：保留更新时间和来源链接，避免把修订后的结果与旧版本混在一起而无法追溯。

GitHub Actions 已配置为每月运行一次，也可以在仓库的 **Actions → Update public data → Run workflow** 手动触发。工作流成功后会更新 data_raw/、data_processed/ 和 metadata/，并自动提交变更。

本地运行方式：

~~~bash
python scripts/update_sources.py
~~~

脚本只需要公开 API；任何需要授权的密钥都不应写入代码或数据文件，应放入 GitHub Secrets。

## 研究复用建议

为了让不同课题组成员的结果可以互相复现，建议每个新项目至少保存以下信息：

1. 使用的数据文件相对路径和 Git commit；
2. 样本筛选条件、时间范围和实体编码规则；
3. 变量变换、缺失值处理、缩尾和滞后设定；
4. 数据来源 URL、下载日期和许可证状态；
5. 生成回归表或机器学习结果所使用的脚本和随机种子。

不要直接覆盖共享数据文件来适应单个论文的样本。更稳妥的做法是在 examples/ 或相应研究项目目录中写出可重跑的筛选脚本，并把中间结果标记为派生文件。

## 公开与授权边界

本仓库公开的是已经整理的可复用结果、处理脚本、字段字典和来源记录。商业数据库原始文件、明确禁止再分发的文件、含有个人敏感信息的文件以及许可证尚未确认的完整快照不应直接放入公开仓库。若新增数据无法确认公开权限，应先上传“获取脚本 + 字段说明 + 来源链接”，不要上传受限原文件。

## 贡献和问题反馈

如果发现变量含义、单位、实体编码、年份覆盖或来源链接有问题，请在 Issue 中说明：文件路径、变量名、问题描述、可核对的来源链接和建议修正方式。修正应同时更新数据文件、字段字典和审计记录，避免只改一个 CSV 而留下不一致的元数据。

最后更新：2026-09-18（UTC）
