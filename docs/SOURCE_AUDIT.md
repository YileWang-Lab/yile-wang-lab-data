# Source audit / 数据来源核查

更新日期：2026-09-18（UTC）

## 核查原则

- 公开 API 数据必须保留官方查询链接、下载时间、指标代码和实际返回的最新年份。
- GitHub 数据和代码必须保留原始仓库链接、上游仓库更新时间和源文件路径。
- `metadata/data_coverage_audit_bilingual.csv` 只记录文件中实际出现的年份；不插值、不前向填充、不把文件名中的年份当作观测。
- 未确认许可证的源仓库在核查表中标记为需复核，使用者应在论文或公开再分发前检查原始仓库许可证和数据提供方条款。

## 当前已核查来源

| English source | 中文来源 | Source URL | Status |
|---|---|---|---|
| World Bank GDP (current US$) | 世界银行国内生产总值（现价美元） | `https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.CD` | Official live API; latest returned year recorded in the report |
| KarlHeinrich-jpg repositories | KarlHeinrich-jpg 个人 GitHub 仓库 | `https://github.com/KarlHeinrich-jpg` | Snapshot checked; repository-level license review required |
| YileWang-Lab repositories | Yile-Wang-Lab 组织仓库 | `https://github.com/YileWang-Lab` | Snapshot checked; repository-level license review required |

逐项结果见 `metadata/source_verification_bilingual.csv`；每个标准化数据文件的实际年份覆盖见 `metadata/data_coverage_audit_bilingual.csv`。

## 自动更新范围

当前自动更新的是 World Bank 官方 API 数据，并同步生成：

- `data_raw/worldbank_NY.GDP.MKTP.CD.csv`
- `data_processed/english/worldbank_gdp_current_usd__worldbank_en.csv`
- `data_processed/chinese/worldbank_gdp_current_usd__worldbank_cn.csv`
- `metadata/source_verification_bilingual.csv`
- `metadata/data_coverage_audit_bilingual.csv`
- `metadata/source_manifest.json`
- `metadata/update_run.json`

其他课题组面板数据没有统一、稳定且明确授权的公开 API，因此只保留已核查的历史观测和源路径，避免用不可靠的抓取或推断制造“最新年份”。
