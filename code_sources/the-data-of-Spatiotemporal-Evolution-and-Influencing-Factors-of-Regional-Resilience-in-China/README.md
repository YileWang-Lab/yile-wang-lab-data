# Spatiotemporal Evolution and Influencing Factors of Regional Resilience in China

**Data and code repository** for the study:

> **Spatiotemporal Evolution and Influencing Factors of Regional Resilience in China: Evidence from Provincial Panel Data Using Spearman-CRITIC and XGBoost-CatBoost-SHAP**
> Yuan Li, Yile Wang, Wenjing Li
> School of Economics, Beijing Technology and Business University, Beijing 102488, China
> Corresponding author: Wenjing Li (`lwjing99@yeah.net`)

This repository contains the full dataset, intermediate files, analysis scripts, and result files used in the paper. The manuscript itself is **not** included here.

---

## 1. Abstract

Regional resilience is closely related to sustainable development because it reflects the capacity of a region to maintain stable economic, social, ecological, and infrastructural functions under long-term transformation. Based on provincial panel data for China from **2007 to 2024** (31 provincial-level regions, 558 province-year observations), this study constructs a regional resilience evaluation system covering **economic resilience (ER)**, **social development resilience (SDR)**, **ecological and environmental resilience (EER)**, and **infrastructure resilience (IR)**.

* A **Spearman-CRITIC** model is used to compute the composite resilience index (robust to non-normal indicators and inter-indicator correlation).
* **Getis-Ord Gi\*** cold–hot spot analysis and **kernel density estimation (KDE)** examine spatial patterns and distributional dynamics.
* An **XGBoost-CatBoost hybrid model** with **SHAP** identifies the explanatory contribution of potential influencing factors.

**Main findings.** Provincial resilience generally improved over the study period, with persistent regional differences. Hot spots concentrate in the eastern coastal and some central-eastern provinces; cold spots appear intermittently in western and southwestern areas and contract over time. SHAP results indicate that **residents' income level (INC)**, **private economic vitality (PRI)**, and **urbanization rate (URB)** make the largest contributions to model prediction, with clear regional heterogeneity. Robustness checks (alternative weighting methods, alternative temporal splits, drop-one collinearity, leave-one-indicator-out) support the stability of the main patterns.

**Keywords:** Regional resilience; Spatiotemporal evolution; Spearman-CRITIC; Sustainable development; XGBoost-CatBoost-SHAP.

---

## 2. Data

| Item | Value |
|---|---|
| Spatial units | 31 provincial-level regions of mainland China |
| Period | 2007–2024 (annual) |
| Panel size | 558 province-year observations |
| Constitutive indicators | 16 (→ resilience index) |
| Explanatory variables | 10 (→ SHAP analysis, not part of the index) |
| Missing-value treatment | province-specific linear interpolation before standardization |

**Primary source.** `中国省级数据库6.0版.xlsx` — a compiled provincial statistical database (sheets: `原始数据` raw, `线性插值` linearly interpolated, `回归填补` regression-imputed). All indicator and explanatory-variable series are extracted from the `线性插值` sheet. This file is ~55 MB; GitHub may display a large-file notice.

The starting year 2007 is constrained by the fiscal-expenditure variables (EPES, INNO, EDU, SOC), which are not comparable before China's 2007 government revenue/expenditure reclassification, and by incomplete pre-2007 provincial coverage of IPR, PCURA, and REPC.

### 2.1 Resilience measurement system (16 constitutive indicators)

| Dimension | Indicator | Code | Unit | Direction |
|---|---|---|---|---|
| Economic Resilience (ER) | Per Capita GDP | PCGDP | yuan/person | + |
| ER | Per Capita Retail Sales of Consumer Goods | PCRS | yuan/person | + |
| ER | Fiscal Self-sufficiency Ratio | FSR | % | + |
| ER | Share of Tertiary Industry in GDP | TIG | % | + |
| Social Development Resilience (SDR) | Registered Urban Unemployment Rate | RUUR | % | − |
| SDR | Hospital Beds per 10,000 People | HBTP | beds/10,000 persons | + |
| SDR | Internet Penetration Rate | IPR | % | + |
| SDR | Ratio of Urban to Rural Per Capita Disposable Income | URIR | ratio | − |
| Ecological & Environmental Resilience (EER) | Green Coverage Rate of Built-up Areas | GCR | % | + |
| EER | Wastewater Emission Intensity | WEI | 10,000 t / CNY 100 M | − |
| EER | Sulfur Dioxide Emission Intensity | SDEI | 10,000 t / CNY 100 M | − |
| EER | Environmental Protection Expenditure Share | EPES | % | + |
| Infrastructure Resilience (IR) | Urban Gas Penetration Rate | UGPR | % | + |
| IR | Urban Water Penetration Rate | UWPR | % | + |
| IR | Per Capita Urban Road Area | PCURA | m²/person | + |
| IR | Rural Electricity Consumption per Capita | REPC | kWh/person | + |

**Global Spearman-CRITIC weights** (from `SPEARMAN_CRITIC_RESULTS.xlsx`, sheet `WEIGHTS`):

| Indicator | Weight | Indicator | Weight | Indicator | Weight | Indicator | Weight |
|---|---|---|---|---|---|---|---|
| EPES | 0.1287 | RUUR | 0.0840 | GCR | 0.0492 | PCGDP | 0.0368 |
| FSR | 0.1020 | IPR | 0.0655 | UGPR | 0.0381 | WEI | 0.0348 |
| PCURA | 0.0981 | URIR | 0.0630 | UWPR | 0.0378 | SDEI | 0.0345 |
| HBTP | 0.0841 | TIG | 0.0614 | PCRS | 0.0505 | REPC | 0.0314 |

Subsystem (ER/SDR/EER/IR) scores are obtained by aggregating the global weights of the indicators within each subsystem (`SPEARMAN_CRITIC_CRITERION_RESULTS.xlsx`).

### 2.2 Explanatory variables (10; predictive correlates, not index components)

| Code | Meaning | Construction |
|---|---|---|
| URB | Urbanization rate | urban population / year-end resident population × 100 |
| GOV | Government intervention intensity | local general budgetary expenditure / GRP × 100 |
| INNO | Science & technology input intensity | local S&T expenditure / local general budgetary expenditure × 100 |
| EDU | Education input intensity | local education expenditure / local general budgetary expenditure × 100 |
| OPENPC | Per capita openness | total imports & exports (by operating-unit location) / resident population × 10,000 |
| FIN | Financial development level | financial-sector value added / GRP × 100 |
| DIG | Digital development level | ICT-sector urban employment / total urban employment × 100 |
| PRI | Private economic vitality | number of private enterprises / resident population × 10,000 |
| INC | Residents' income level | per capita disposable income of all residents |
| SOC | Social security support intensity | local social-security & employment expenditure / local general budgetary expenditure × 100 |

Identifiers `ADMINCODE`, `REGION`, `ZONE`, `YEAR` are used only to organize the panel and split it chronologically — they are **not** model features.

---

## 3. Methods

| Stage | Method | Notes |
|---|---|---|
| Index construction | **Spearman-CRITIC** | Rank-based CRITIC weighting; combines indicator dispersion (SD) and information conflict (1 − Spearman ρ). Directional standardization first. |
| Alternative weights (robustness) | EWM, CV, DM, PCA, Factor analysis | `综合测度.py` → `REGIONAL_RESILIENCE_MULTI_METHOD_RESULTS.xlsx` |
| Spatial pattern | **Getis-Ord Gi\*** cold/hot spots | Baseline: binary fixed-distance band (ArcGIS default threshold). Sensitivity: 4-nearest-neighbor, Queen contiguity. |
| Distribution dynamics | **Kernel density estimation** (Gaussian kernel) | `KDE.m` (MATLAB), national + eastern / central / western samples |
| Factor identification | **XGBoost-CatBoost hybrid** + **SHAP** | Prediction-level weighted fusion of independently trained XGBoost and CatBoost; SHAP (TreeExplainer-style) for contribution ranking and direction |
| Benchmarks | OLS, Ridge, Random Forest, SVR, XGBoost, GBDT, ELM, CatBoost, AdaBoost | `参数搜索2.py`, `简化模型的.py` |

**Chronological split (no random shuffling):** train 2007–2019, validation 2020–2021, test 2022–2024. Alternative splits: (a) pre-pandemic tuning with 2020–2024 test; (b) 2023–2024 recovery-period test.

**Best hybrid hyperparameters** (grid search): `alpha=0.342`; CatBoost `depth=6, iterations=500, l2_leaf_reg=5, learning_rate=0.05`; XGBoost `colsample_bytree=0.8, learning_rate=0.05, max_depth=5, n_estimators=500, subsample=1.0`. Full grid in `MODEL_COMPARE_RESULTS.xlsx` / paper Table A.1.

---

## 4. Repository structure

Scripts read and write **relative to the repository root**, so run them from the repo root directory.

### 4.1 Scripts (`.py`, plus `KDE.m`)

| Order | Script | Purpose | Key output |
|---|---|---|---|
| 1 | `数据预处理-整理测度指标.py` | Extract the 16 constitutive indicators from the provincial database | `resilience_output/RESILIENCE_PANEL_EN.csv`, `INDICATOR_SYSTEM_EN.csv` |
| 1b | `数据预处理-整理测度指标2.py` | Build the two urban–rural indicators (URIR, REPC) | `two_indicators_output/URBAN_RURAL_INDICATORS.xlsx` |
| 2 | `数据预处理-线性插值.py` | Province-wise linear interpolation of the indicator panel | `RESILIENCE_PANEL_EN_INTERPOLATED.xlsx` |
| 2b | `数据预处理-线性插值2.py` | Interpolate URIR / REPC | `URIR_REPC_INTERPOLATED.xlsx` |
| 3 | `描述性分析-正态检验.py` | Descriptive stats + KS normality test of indicators (Table 2) | `DESCRIPTIVE_STATISTICS_KS.xlsx` |
| 4 | `Spearman-CRITIC.py` | **Composite resilience index** (weights, standardized data, scores) | `SPEARMAN_CRITIC_RESULTS.xlsx` |
| 5 | `计算准则指标.py` | Subsystem ER / SDR / EER / IR scores | `SPEARMAN_CRITIC_CRITERION_RESULTS.xlsx` |
| 6 | `综合测度.py` | Alternative composite scores (EWM, CV, DM, PCA, Factor) | `REGIONAL_RESILIENCE_MULTI_METHOD_RESULTS.xlsx` |
| 7 | `数据预处理-导入外生变量.py` | Merge resilience score with the 10 explanatory variables | `PANEL_ANALYSIS_DATA.xlsx` |
| 8 | `描述性统计.py` | Descriptive statistics of the analysis panel (Table 3) | `DESCRIPTIVE_STATISTICS_RESULTS.xlsx` |
| 9 | `Pearson相关性分析.py` | Descriptive stats + Pearson correlation heatmap (Figure 4) | `DESCRIPTIVE_AND_PEARSON_RESULTS/` |
| 10 | `相关性2.py` | Explanatory variables vs. four subsystems (Table A.3) | `CORRELATION_RESULTS/TABLE_A3_SUBSYSTEM_CORRELATION.xlsx` |
| 11 | `稳健性-冷热点.py` | Getis-Ord Gi\* + spatial-weight sensitivity (Table 4, Figure 5) | `spatial_weight_sensitivity_output/` |
| 12 | `KDE.m` | Kernel density surfaces (Figure 6) — **MATLAB** | figures |
| 13 | `参数搜索.py` / `参数搜索2.py` | Model comparison, hyperparameter grid search, temporal robustness (Tables 5, 6, A.1) | in-script Excel output |
| 14 | `简化模型的.py` | OLS / Ridge parsimonious benchmarks | `simple_model_output/SIMPLE_MODEL_RESULTS.xlsx` |
| 15 | `SHAP.py` | National XGBoost-CatBoost + SHAP core figure (Figure 7, national) | `ML_SHAP_NATIONAL/` |
| 16 | `异质性分析.py` | By-zone SHAP: eastern / central / western (Figure 7, regional) | `ML_SHAP_BY_ZONE/` |
| 17 | `单因素.py` | SHAP dependence plots for the top-6 variables (Figure 11) | `SHAP_TOP6_DEPENDENCE_NATIONAL.*` |
| 18 | `稳健性-SHAP.py` / `稳健性2-SHAP.py` | SHAP under alternative resilience measures & subsystems (Figures 9, 10) | `ML_SHAP_MULTI_TARGET/` |
| 19 | `稳健性-SHAP补.py` | Drop-one collinearity check: remove PRI / remove INC (Figure 8) | `ML_SHAP_DROP_ONE/` |
| 20 | `稳健性3.py` | Leave-one-indicator-out for URIR / REPC (Table A.4) | `LEAVE_ONE_INDICATOR_OUT_RESULTS/` |

`ML_SHAP_OUTPUT_CORE/` holds an earlier single-run variant of the national SHAP output.

### 4.2 Data & intermediate files

| File | Content |
|---|---|
| `中国省级数据库6.0版.xlsx` | Raw provincial database (primary source, ~55 MB) |
| `RESILIENCE_PANEL_EN.xlsx` | 16 constitutive indicators, English codes, before interpolation |
| `RESILIENCE_PANEL_EN_INTERPOLATED.xlsx` | Same, after province-wise linear interpolation (index input) |
| `URIR_REPC_INTERPOLATED.xlsx` | Interpolated urban–rural indicators |
| `PANEL_ANALYSIS_DATA.xlsx` | Analysis panel: `RESILIENCE` + 10 explanatory variables (+ `EXOGENOUS_DICT`) |
| `data for res.xlsx` | Resilience-index workbook (raw data, standardized, weights, Spearman corr, scores) |
| `DATA _PANEL_ANALYSIS.xlsx` | Panel with subsystem scores ER/SDR/EER/IR + explanatory variables |
| `全国-中部-东部_数据汇总.xlsx` | Wide resilience matrix (province × year) by group, input to `KDE.m` |
| `2007-20024各省份指标变化表.xlsx` | Province-level indicator change table |
| `粘贴的文本 (1)(94).txt` | Long-format `REGION / YEAR / RESILIENCE` dump (intermediate for the KDE workbook) |
| `PANEL_ANALYSIS_DATA - 副本*.xlsx` | Working copies retained for provenance |

### 4.3 Result folders

`SPEARMAN_CRITIC_RESULTS.xlsx`, `SPEARMAN_CRITIC_CRITERION_RESULTS.xlsx`, `REGIONAL_RESILIENCE_MULTI_METHOD_RESULTS.xlsx`, `DESCRIPTIVE_STATISTICS_KS.xlsx`, `DESCRIPTIVE_STATISTICS_RESULTS.xlsx`, `MODEL_COMPARE_RESULTS.xlsx`, `SHAP_TOP6_DEPENDENCE_NATIONAL.{xlsx,png,pdf}`, and the directories `CORRELATION_RESULTS/`, `DESCRIPTIVE_AND_PEARSON_RESULTS/`, `LEAVE_ONE_INDICATOR_OUT_RESULTS/`, `ML_SHAP_BY_ZONE/`, `ML_SHAP_DROP_ONE/`, `ML_SHAP_MULTI_TARGET/`, `ML_SHAP_NATIONAL/`, `ML_SHAP_OUTPUT_CORE/`, `resilience_output/`, `simple_model_output/`, `spatial_weight_sensitivity_output/`, `two_indicators_output/`. Figures `全国.png`, `东部.png`, `中部.png`, `西部.png` are regional resilience trend charts. `catboost_info/` is CatBoost training telemetry (regenerated on every run).

---

## 5. Reproduction

### Environment

* **Python** ≥ 3.10
* `pip install pandas numpy scipy scikit-learn xgboost catboost shap matplotlib openpyxl`
* Spatial analysis (`稳健性-冷热点.py`): `pip install geopandas libpysal esda` (this script also downloads a province boundary file the first time it runs)
* **MATLAB** with the Statistics and Machine Learning Toolbox for `KDE.m` (uses `ksdensity`)

See `requirements.txt`.

### Steps

1. Clone the repository and work from its root directory.
2. Run the scripts in the order given in §4.1. Stages 1–7 rebuild the resilience index; stages 8–20 reproduce the tables and figures.
3. `KDE.m` contains a hard-coded `cd(...)` path — edit it to your local repository path before running.

---

## 6. Key results (summary)

* **Index.** Mean resilience 0.492 (SD 0.097, median 0.501); slightly left-skewed, relatively flat.
* **Spatial pattern.** Stable eastern-coastal hot spots; intermittent southwestern/western cold spots that contract after 2016. Gi\* z-score rank correlation across alternative spatial weights: 0.89 (4-NN), 0.86 (Queen).
* **Distribution.** National KDE shifts right (overall improvement); persistent east–west gaps; some multi-peak structure in the east.
* **Prediction.** XGBoost-CatBoost hybrid test R² = 0.765 (MAE 0.021, RMSE 0.026, MAPE 3.88%), best among all benchmarks; OLS/Ridge test R² ≈ 0.00–0.02. Under alternative temporal splits, test R² = 0.765–0.816.
* **SHAP.** National: INC, PRI, URB rank highest. Eastern: PRI, INC, DIG. Western: INC, URB (then PRI, SOC, FIN). Central: PRI, INC (then FIN, URB). Core rankings stable across EWM/CV/DM/PCA measures; OPENPC dominates only the economic subsystem.
* **Robustness.** Drop-one (remove PRI or INC) keeps the other dominant and URB/INNO stable; leave-one-indicator-out for URIR/REPC keeps Spearman correlation with the full index ≥ 0.995.

---

## 7. Notes and caveats

* **Indicator revision.** Some earlier files (`RESILIENCE_PANEL_EN.xlsx`, `data for res.xlsx`, `DATA _PANEL_ANALYSIS.xlsx`, `SPEARMAN_CRITIC_CRITERION_RESULTS.xlsx`) still carry two superseded SDR/IR indicators — **HESP** (higher-education students per 100k) and **PTVP** (public-transit vehicles per 10k). The **published** measurement system replaces these with **URIR** and **REPC**; the corresponding current files are `RESILIENCE_PANEL_EN_INTERPOLATED.xlsx`, `SPEARMAN_CRITIC_RESULTS.xlsx`, and `PANEL_ANALYSIS_DATA.xlsx`.
* SHAP values and machine-learning results are **predictive associations**, not causal effects. Province identifiers are excluded from all models.
* FSR, TIG, PCRS, PCURA are bounded proxies (fiscal autonomy, structural upgrading, internal demand, urban road-service capacity) and do not capture fiscal transfers/reserves, full industrial diversification, multimodal transport, or rural roads.
* The manuscript file is intentionally not included in this repository.

---

## 8. Citation

If you use this dataset or code, please cite the paper above. A machine-readable citation entry is in `CITATION.cff`.

## 9. Contact

Yile Wang — `lasulse20@gmail.com` · Corresponding author Wenjing Li — `lwjing99@yeah.net`
