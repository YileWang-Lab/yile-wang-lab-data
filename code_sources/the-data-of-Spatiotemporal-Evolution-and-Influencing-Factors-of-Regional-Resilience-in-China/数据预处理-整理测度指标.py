from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

# =========================================================
# Basic settings
# =========================================================
INPUT_PATH = r"中国省级数据库6.0版.xlsx"
INPUT_SHEET = "线性插值"
OUTPUT_DIR = Path("resilience_output")

# =========================================================
# Utilities
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


def read_data(path: str, sheet_name: str) -> pd.DataFrame:
    path_obj = Path(path)
    if not path_obj.exists():
        raise FileNotFoundError(f"File not found: {path}")

    suffix = path_obj.suffix.lower()

    if suffix in [".xlsx", ".xls"]:
        df = pd.read_excel(path_obj, sheet_name=sheet_name)
    elif suffix == ".csv":
        df = pd.read_csv(path_obj, encoding="utf-8-sig")
    else:
        raise ValueError("Only Excel or CSV files are supported.")

    df.columns = [clean_colname(c) for c in df.columns]
    return df


# =========================================================
# Indicator table
# =========================================================
def get_indicator_table() -> pd.DataFrame:
    data = [
        ["Economic Resilience", "Per Capita GDP", "PCGDP", "yuan/person", "+"],
        ["Economic Resilience", "Per Capita Retail Sales of Consumer Goods", "PCRS", "yuan/person", "+"],
        ["Economic Resilience", "Fiscal Self-sufficiency Ratio", "FSR", "%", "+"],
        ["Economic Resilience", "Share of Tertiary Industry in GDP", "TIG", "%", "+"],

        ["Social Resilience", "Registered Urban Unemployment Rate", "RUUR", "%", "-"],
        ["Social Resilience", "Hospital Beds per 10,000 People", "HBTP", "beds/10,000 persons", "+"],
        ["Social Resilience", "Internet Penetration Rate", "IPR", "%", "+"],
        ["Social Resilience", "Higher Education Students per 100,000 People", "HESP", "persons/100,000 persons", "+"],

        ["Ecological Resilience", "Green Coverage Rate of Built-up Areas", "GCR", "%", "+"],
        ["Ecological Resilience", "Wastewater Emission Intensity", "WEI", "10,000 tons/CNY 100 million", "-"],
        ["Ecological Resilience", "Sulfur Dioxide Emission Intensity", "SDEI", "10,000 tons/CNY 100 million", "-"],
        ["Ecological Resilience", "Environmental Protection Expenditure Share", "EPES", "%", "+"],

        ["Infrastructure Resilience", "Urban Gas Penetration Rate", "UGPR", "%", "+"],
        ["Infrastructure Resilience", "Urban Water Penetration Rate", "UWPR", "%", "+"],
        ["Infrastructure Resilience", "Per Capita Urban Road Area", "PCURA", "m²/person", "+"],
        ["Infrastructure Resilience", "Public Transit Vehicles per 10,000 People", "PTVP", "vehicles/10,000 persons", "+"],
    ]
    return pd.DataFrame(
        data,
        columns=["CRITERION", "INDICATOR", "CODE", "UNIT", "POLARITY"]
    )


# =========================================================
# Build extracted panel only
# =========================================================
def build_panel(df: pd.DataFrame) -> pd.DataFrame:
    region_col = find_col(df, ["地区"])
    year_col = find_col(df, ["年份"])
    zone_col = find_col(df, ["所属地域"])
    admin_col = find_col(df, ["行政区划代码"])

    if region_col is None or year_col is None:
        raise ValueError("Columns '地区' and '年份' are required.")

    raw = {}
    raw["PCGDP"] = find_col(df, ["人均地区生产总值(元/人)"])
    raw["RETAIL"] = find_col(df, ["社会消费品零售总额(亿元)"])
    raw["POP"] = find_col(df, ["年末常住人口(万人)"])
    raw["FINREV"] = find_col(df, ["地方财政一般预算收入(亿元)"])
    raw["FINEXP"] = find_col(df, ["地方财政一般预算支出(亿元)"])
    raw["TERTIARY"] = find_col(df, ["第三产业增加值(亿元)"])
    raw["GDP"] = find_col(df, ["地区生产总值(亿元)"])

    raw["RUUR"] = find_col(df, ["城镇登记失业率(%)"])
    raw["HBTP"] = find_col(df, ["每万人医疗机构床位数(张)", "每万人医院和卫生院床位数(张)"])
    raw["IPR"] = find_col(df, ["互联网普及率(%)"])
    raw["HESP"] = find_col(df, ["每十万人口高等学校平均在校生数(人)"])
    raw["HESTOTAL"] = find_col(df, ["普通高等学校在校学生数(万人)"])

    raw["GCR"] = find_col(df, ["建成区绿化覆盖率(%)"])
    raw["WASTE"] = find_col(df, ["废水排放总量(万吨)"])
    raw["SO2"] = find_col(df, ["二氧化硫排放量(万吨)"])
    raw["ENVEXP"] = find_col(df, ["地方财政环境保护支出(亿元)"])

    raw["UGPR"] = find_col(df, ["城市燃气普及率(%)"])
    raw["UWPR"] = find_col(df, ["城市用水普及率(%)"])
    raw["PCURA"] = find_col(df, ["人均城市道路面积(平方米)"])
    raw["PTVP"] = find_col(df, ["每万人拥有公共交通车辆(标台)"])

    panel = pd.DataFrame()
    if admin_col is not None:
        panel["ADMINCODE"] = df[admin_col]
    panel["REGION"] = df[region_col]
    if zone_col is not None:
        panel["ZONE"] = df[zone_col]
    panel["YEAR"] = safe_to_numeric(df[year_col]).astype("Int64")

    def get_series(key: str) -> pd.Series:
        col = raw[key]
        if col is None:
            return pd.Series(np.nan, index=df.index)
        return safe_to_numeric(df[col])

    GDP = get_series("GDP")
    POP = get_series("POP")
    RETAIL = get_series("RETAIL")
    FINREV = get_series("FINREV")
    FINEXP = get_series("FINEXP")
    TERTIARY = get_series("TERTIARY")
    HESTOTAL = get_series("HESTOTAL")
    WASTE = get_series("WASTE")
    SO2 = get_series("SO2")
    ENVEXP = get_series("ENVEXP")

    panel["PCGDP"] = get_series("PCGDP")
    panel["PCRS"] = RETAIL / POP * 10000
    panel["FSR"] = FINREV / FINEXP * 100
    panel["TIG"] = TERTIARY / GDP * 100

    panel["RUUR"] = get_series("RUUR")
    panel["HBTP"] = get_series("HBTP")
    panel["IPR"] = get_series("IPR")

    panel["HESP"] = get_series("HESP")
    missing_hesp = panel["HESP"].isna()
    panel.loc[missing_hesp, "HESP"] = HESTOTAL[missing_hesp] / POP[missing_hesp] * 100000

    panel["GCR"] = get_series("GCR")
    panel["WEI"] = WASTE / GDP
    panel["SDEI"] = SO2 / GDP
    panel["EPES"] = ENVEXP / FINEXP * 100

    panel["UGPR"] = get_series("UGPR")
    panel["UWPR"] = get_series("UWPR")
    panel["PCURA"] = get_series("PCURA")
    panel["PTVP"] = get_series("PTVP")

    return panel


# =========================================================
# Main
# =========================================================
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = read_data(INPUT_PATH, INPUT_SHEET)
    indicator_table = get_indicator_table()
    panel = build_panel(df)

    indicator_table.to_csv(
        OUTPUT_DIR / "INDICATOR_SYSTEM_EN.csv",
        index=False,
        encoding="utf-8-sig"
    )

    panel.to_csv(
        OUTPUT_DIR / "RESILIENCE_PANEL_EN.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print("=" * 70)
    print("Finished successfully.")
    print(f"Input file: {INPUT_PATH}")
    print(f"Input sheet: {INPUT_SHEET}")
    print(f"Output folder: {OUTPUT_DIR.resolve()}")
    print("Generated files:")
    print("1. INDICATOR_SYSTEM_EN.csv")
    print("2. RESILIENCE_PANEL_EN.csv")
    print("=" * 70)


if __name__ == "__main__":
    main()