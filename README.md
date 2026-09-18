# Yile-Wang Lab 数据获取与研究复用仓库

更新日期：2026-09-18

本仓库面向 Yile-Wang Lab 的经济学、金融工程和机器学习研究。数据同时提供英文标准字段、中文原始字段和字段字典，适合 Stata、R、Python 回归与机器学习使用。

来源核查记录见 `metadata/source_verification_bilingual.csv`、`metadata/data_coverage_audit_bilingual.csv` 和 `docs/SOURCE_AUDIT.md`。仓库只报告源文件中实际观测到的年份，不用插值或前向填充伪造最新年份。

## 目标
统一整理金融工程、经济学实证、机器学习和时间序列研究所需的数据、代码、元数据与更新脚本。所有数据集应同时提供英文变量名、中文变量名和字段字典。

## 目录
- `metadata/`：仓库清单、数据集登记表、双语字段字典
- `source_snapshots/`：待归档的源仓库快照（仅在下载成功后填充）
- `data_raw/`：原始数据（需逐项核验许可证）
- `data_processed/`：统一格式数据，优先 Parquet/CSV
- `scripts/`：下载、清洗、合并、质量检查和更新脚本
- `examples/`：可直接运行的读取和回归示例
- `docs/`：数据使用说明与研究主题索引

## 双语字段规范
建议所有处理后数据采用长表或规范宽表，并保留以下审计字段：

| English field | 中文字段 | 含义 |
|---|---|---|
| entity_id | 个体编号 | 省份、城市、公司或金融资产的稳定编码 |
| entity_name | 个体名称 | 个体中文名称 |
| date | 观测日期 | 统一为 ISO 格式 YYYY-MM-DD |
| frequency | 频率 | daily / monthly / quarterly / annual；日频/月频/季频/年频 |
| variable | 指标英文名 | 标准化指标代码 |
| variable_cn | 指标中文名 | 指标中文名称 |
| value | 数值 | 原始或转换后的观测值 |
| unit | 单位 | 元、%、指数、吨等 |
| source | 数据来源 | 机构或数据库名称 |
| source_url | 来源链接 | 原始下载或查询地址 |
| release_date | 发布日期 | 数据对外发布日 |
| vintage_date | 数据版本日 | 防止宏观数据前视偏差 |
| transform | 变换方式 | level/log/diff/return/winsorized 等 |
| quality_flag | 质量标记 | 缺失、异常、修订等状态 |

## 当前优先整理主题
1. 中国省级和地级市经济、能源、产业结构、全要素生产率与控制变量面板；
2. 金融市场、金融随机过程和时间序列预测数据；
3. 农业、大宗商品、能源与风险管理数据；
4. 数字经济、绿色生产率、区域韧性、信用风险和光伏专题数据；
5. 面向 FE-SCI、DML、深度学习和黎曼计量的可复现实验数据。

## 公开发布规则
商业数据库原始数据、受许可限制的数据和未确认再分发权限的网页文本不直接公开；仓库只保留下载脚本、字段字典、处理流程、合法样例和来源链接。每个数据集必须记录许可证、抓取时间、版本号和校验哈希。

## 更新规则
数据按来源实际发布频率更新。每次运行会记录核查时间、源链接、实际最新年份和文件级覆盖范围；不会覆盖历史处理文件，也不会用插值或前向填充补齐年份。API 密钥只放在 GitHub Secrets，不写入代码。

## 最新年份与自动更新

已加入 World Bank GDP（现价美元）官方 API。脚本每次按当前年份请求数据，并同步更新 `data_raw/`、英文处理文件、中文处理文件和来源核查报告；当前 API 返回的最新有效年份为 2025。GitHub Actions 工作流按月运行，也可手动运行：`python scripts/update_sources.py`。

课题组历史面板数据的年份取决于原始统计来源；`metadata/data_coverage_audit_bilingual.csv` 给出每个文件实际检测到的起止年份。对于尚无公开更新接口的数据，仓库保留原始来源路径和核查状态，不擅自延长年份。
