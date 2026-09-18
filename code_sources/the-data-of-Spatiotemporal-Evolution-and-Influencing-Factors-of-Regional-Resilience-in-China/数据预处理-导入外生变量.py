from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

# =========================================================
# 1. 文件设置
# =========================================================
DB_PATH = r"中国省级数据库6.0版.xlsx"
DB_SHEET = "线性插值"

SCORE_PATH = r"SPEARMAN_CRITIC_RESULTS.xlsx"
SCORE_SHEET = "SCORES"

OUTPUT_PATH = r"PANEL_ANALYSIS_DATA.xlsx"


# =========================================================
# 2. 工具函数
# =========================================================
def clean_colname(name: str) -> str:
    return str(name).strip().replace("\u3000", " ")


def safe_to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False),
        errors="coerce"
    )


def find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    cols = [clean_colname(c) for c in df.columns]
    col_map = {clean_colname(c): c for c in df.columns}

    for cand in candidates:
        cand_clean = clean_colname(cand)
        if cand_clean in col_map:
            return col_map[cand_clean]

    for cand in candidates:
        cand_clean = clean_colname(cand)
        for col in cols:
            if cand_clean in col or col in cand_clean:
                return col_map[col]

    return None


def fill_missing_by_region_year(
    df: pd.DataFrame,
    group_col: str,
    time_col: str,
    value_cols: List[str]
) -> pd.DataFrame:
    df = df.sort_values([group_col, time_col]).copy()

    for col in value_cols:
        df[col] = df.groupby(group_col)[col].transform(
            lambda x: x.interpolate(method="linear", limit_direction="both")
        )
        df[col] = df.groupby(time_col)[col].transform(
            lambda x: x.fillna(x.median())
        )
        df[col] = df[col].fillna(df[col].median())

    return df


def read_excel_file(path: str, sheet_name=0) -> pd.DataFrame:
    path_obj = Path(path)
    if not path_obj.exists():
        raise FileNotFoundError(f"找不到文件: {path}")

    df = pd.read_excel(path_obj, sheet_name=sheet_name)
    df.columns = [clean_colname(c) for c in df.columns]
    return df


# =========================================================
# 3. 提取外生变量
# =========================================================
def build_exogenous_panel(db: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    region_col = find_col(db, ["地区"])
    year_col = find_col(db, ["年份"])
    zone_col = find_col(db, ["所属地域"])
    admin_col = find_col(db, ["行政区划代码"])

    if region_col is None or year_col is None:
        raise ValueError("数据库中至少需要包含‘地区’和‘年份’两列。")

    # 原始字段
    pop_col = find_col(db, ["年末常住人口(万人)"])
    urban_pop_col = find_col(db, ["城镇人口(万人)"])
    gdp_col = find_col(db, ["地区生产总值(亿元)"])
    fiscal_exp_col = find_col(db, ["地方财政一般预算支出(亿元)"])
    sci_exp_col = find_col(db, ["地方财政科学技术支出(亿元)"])
    edu_exp_col = find_col(db, ["地方财政教育支出(亿元)"])
    soc_exp_col = find_col(db, ["地方财政社会保障和就业支出(亿元)"])
    trade_col = find_col(db, ["经营单位所在地进出口总额(千美元)", "境内目的地和货源地进出口总额(千美元)"])
    fin_value_col = find_col(db, ["金融业增加值(亿元)"])
    it_emp_col = find_col(db, ["信息传输、软件和信息技术服务业城镇单位就业人员(万人)", "信息传输、计算机服务和软件业城镇单位就业人员(万人)"])
    total_emp_col = find_col(db, ["城镇单位就业人员(万人)"])
    private_firms_col = find_col(db, ["私营企业户数(万户)"])
    income_col = find_col(db, ["全体居民人均可支配收入(元)"])

    raw = pd.DataFrame()
    if admin_col is not None:
        raw["ADMINCODE"] = db[admin_col]
    raw["REGION"] = db[region_col]
    if zone_col is not None:
        raw["ZONE"] = db[zone_col]
    raw["YEAR"] = safe_to_numeric(db[year_col]).astype("Int64")

    POP = safe_to_numeric(db[pop_col]) if pop_col is not None else pd.Series(np.nan, index=db.index)
    URBANPOP = safe_to_numeric(db[urban_pop_col]) if urban_pop_col is not None else pd.Series(np.nan, index=db.index)
    GDP = safe_to_numeric(db[gdp_col]) if gdp_col is not None else pd.Series(np.nan, index=db.index)
    FISCAL_EXP = safe_to_numeric(db[fiscal_exp_col]) if fiscal_exp_col is not None else pd.Series(np.nan, index=db.index)
    SCI_EXP = safe_to_numeric(db[sci_exp_col]) if sci_exp_col is not None else pd.Series(np.nan, index=db.index)
    EDU_EXP = safe_to_numeric(db[edu_exp_col]) if edu_exp_col is not None else pd.Series(np.nan, index=db.index)
    SOC_EXP = safe_to_numeric(db[soc_exp_col]) if soc_exp_col is not None else pd.Series(np.nan, index=db.index)
    TRADE = safe_to_numeric(db[trade_col]) if trade_col is not None else pd.Series(np.nan, index=db.index)
    FIN_VALUE = safe_to_numeric(db[fin_value_col]) if fin_value_col is not None else pd.Series(np.nan, index=db.index)
    IT_EMP = safe_to_numeric(db[it_emp_col]) if it_emp_col is not None else pd.Series(np.nan, index=db.index)
    TOTAL_EMP = safe_to_numeric(db[total_emp_col]) if total_emp_col is not None else pd.Series(np.nan, index=db.index)
    PRIVATE_FIRMS = safe_to_numeric(db[private_firms_col]) if private_firms_col is not None else pd.Series(np.nan, index=db.index)
    INCOME = safe_to_numeric(db[income_col]) if income_col is not None else pd.Series(np.nan, index=db.index)

    # 构造外生变量
    raw["URB"] = URBANPOP / POP * 100
    raw["GOV"] = FISCAL_EXP / GDP * 100
    raw["INNO"] = SCI_EXP / FISCAL_EXP * 100
    raw["EDU"] = EDU_EXP / FISCAL_EXP * 100
    raw["OPENPC"] = TRADE / POP * 10000
    raw["FIN"] = FIN_VALUE / GDP * 100
    raw["DIG"] = IT_EMP / TOTAL_EMP * 100
    raw["PRI"] = PRIVATE_FIRMS / POP * 10000
    raw["INC"] = INCOME
    raw["SOC"] = SOC_EXP / FISCAL_EXP * 100

    exog_cols = ["URB", "GOV", "INNO", "EDU", "OPENPC", "FIN", "DIG", "PRI", "INC", "SOC"]
    raw = fill_missing_by_region_year(raw, "REGION", "YEAR", exog_cols)

    var_dict = pd.DataFrame([
        ["RESILIENCE", "省域韧性得分", "前序 Spearman-CRITIC 结果"],
        ["URB", "城镇化率", "城镇人口 / 年末常住人口 × 100"],
        ["GOV", "政府干预强度", "地方财政一般预算支出 / 地区生产总值 × 100"],
        ["INNO", "科技投入强度", "地方财政科学技术支出 / 地方财政一般预算支出 × 100"],
        ["EDU", "教育投入强度", "地方财政教育支出 / 地方财政一般预算支出 × 100"],
        ["OPENPC", "人均对外开放水平", "经营单位所在地进出口总额 / 年末常住人口 × 10000"],
        ["FIN", "金融发展水平", "金融业增加值 / 地区生产总值 × 100"],
        ["DIG", "数字化发展水平", "信息传输、软件和信息技术服务业城镇单位就业人员 / 城镇单位就业人员 × 100"],
        ["PRI", "私营经济活力", "私营企业户数 / 年末常住人口 × 10000"],
        ["INC", "居民收入水平", "直接使用全体居民人均可支配收入"],
        ["SOC", "社会保障支持强度", "地方财政社会保障和就业支出 / 地方财政一般预算支出 × 100"],
    ], columns=["CODE", "NAME_CN", "FORMULA"])

    return raw, var_dict


# =========================================================
# 4. 读取韧性得分
# =========================================================
def read_resilience_score(score_df: pd.DataFrame) -> pd.DataFrame:
    score_df.columns = [clean_colname(c) for c in score_df.columns]

    region_col = find_col(score_df, ["REGION", "地区"])
    year_col = find_col(score_df, ["YEAR", "年份"])
    score_col = find_col(score_df, ["RESILIENCE_SCORE", "RESILIENCE", "韧性得分"])

    if region_col is None or year_col is None or score_col is None:
        raise ValueError("韧性得分表中需要包含 REGION/YEAR/RESILIENCE_SCORE 三类字段。")

    out = pd.DataFrame()
    if "ADMINCODE" in score_df.columns:
        out["ADMINCODE"] = score_df["ADMINCODE"]
    if "ZONE" in score_df.columns:
        out["ZONE"] = score_df["ZONE"]

    out["REGION"] = score_df[region_col]
    out["YEAR"] = safe_to_numeric(score_df[year_col]).astype("Int64")
    out["RESILIENCE"] = safe_to_numeric(score_df[score_col])

    return out


# =========================================================
# 5. 主程序
# =========================================================
def main():
    db = read_excel_file(DB_PATH, DB_SHEET)
    score_raw = read_excel_file(SCORE_PATH, SCORE_SHEET)

    exog_df, var_dict = build_exogenous_panel(db)
    score_df = read_resilience_score(score_raw)

    panel = pd.merge(
        score_df,
        exog_df,
        on=["REGION", "YEAR"],
        how="left",
        suffixes=("", "_EXOG")
    )

    for col in ["ADMINCODE_EXOG", "ZONE_EXOG"]:
        if col in panel.columns:
            panel.drop(columns=[col], inplace=True)

    panel = panel.sort_values(["REGION", "YEAR"]).reset_index(drop=True)

    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        panel.to_excel(writer, sheet_name="PANEL_ANALYSIS", index=False)
        var_dict.to_excel(writer, sheet_name="EXOGENOUS_DICT", index=False)
        exog_df.to_excel(writer, sheet_name="RAW_EXOGENOUS", index=False)

    print("=" * 70)
    print("整体分析数据已生成")
    print(f"输出文件: {Path(OUTPUT_PATH).resolve()}")
    print("输出sheet：")
    print("1. PANEL_ANALYSIS")
    print("2. EXOGENOUS_DICT")
    print("3. RAW_EXOGENOUS")
    print("=" * 70)
    print(panel.columns.tolist())


if __name__ == "__main__":
    main()