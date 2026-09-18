# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
from pathlib import Path
from scipy import stats

# =========================================================
# 基本设置
# =========================================================
DATA_PATH = r"PANEL_ANALYSIS_DATA - 副本.xlsx"
SHEET_NAME = 0

OUTPUT_PATH = r"DESCRIPTIVE_STATISTICS_RESULTS.xlsx"

ID_COLS = ["ADMINCODE", "REGION", "ZONE", "YEAR"]

TARGET_COL = "Spearman-CRITIC"

FEATURE_COLS = [
    "URB", "GOV", "INNO", "EDU", "OPENPC",
    "FIN", "DIG", "PRI", "INC", "SOC"
]

ANALYSIS_COLS = [TARGET_COL] + FEATURE_COLS


# =========================================================
# 自动读取 Excel
# =========================================================
def read_excel_auto(path, sheet_name=0, required_cols=None):
    xls = pd.ExcelFile(path)

    try:
        df0 = pd.read_excel(path, sheet_name=sheet_name)
        if required_cols is None or all(c in df0.columns for c in required_cols):
            print(f"[INFO] Using sheet: {sheet_name}")
            return df0
    except Exception:
        pass

    for sh in xls.sheet_names:
        tmp = pd.read_excel(path, sheet_name=sh, nrows=5)
        if required_cols is None or all(c in tmp.columns for c in required_cols):
            print(f"[INFO] Auto-detected sheet: {sh}")
            return pd.read_excel(path, sheet_name=sh)

    raise ValueError(f"未找到包含所需变量的sheet：{required_cols}")


# =========================================================
# 描述性统计 + KS检验
# =========================================================
def descriptive_analysis(df, cols):
    records = []

    for col in cols:
        x = pd.to_numeric(df[col], errors="coerce").dropna()

        if len(x) < 3:
            records.append({
                "Variable": col,
                "N": len(x),
                "Min": np.nan,
                "Max": np.nan,
                "Mean": np.nan,
                "Std": np.nan,
                "Median": np.nan,
                "Skewness": np.nan,
                "Kurtosis": np.nan,
                "KS Statistic": np.nan,
                "KS P-value": np.nan
            })
            continue

        mean_val = x.mean()
        std_val = x.std(ddof=1)

        if np.isclose(std_val, 0):
            ks_stat = np.nan
            ks_p = np.nan
        else:
            z = (x - mean_val) / std_val
            ks_stat, ks_p = stats.kstest(z, "norm")

        records.append({
            "Variable": col,
            "N": len(x),
            "Min": x.min(),
            "Max": x.max(),
            "Mean": mean_val,
            "Std": std_val,
            "Median": x.median(),
            "Skewness": stats.skew(x),
            "Kurtosis": stats.kurtosis(x),
            "KS Statistic": ks_stat,
            "KS P-value": ks_p
        })

    result = pd.DataFrame(records)
    return result


# =========================================================
# 主程序
# =========================================================
def main():
    input_file = Path(DATA_PATH)
    if not input_file.exists():
        raise FileNotFoundError(f"找不到文件：{DATA_PATH}")

    df = read_excel_auto(
        DATA_PATH,
        sheet_name=SHEET_NAME,
        required_cols=ANALYSIS_COLS
    )

    missing_cols = [c for c in ANALYSIS_COLS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"数据缺少以下变量：{missing_cols}")

    keep_cols = [c for c in ID_COLS if c in df.columns] + ANALYSIS_COLS
    df = df[keep_cols].copy()

    for col in ANALYSIS_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    missing_summary = df[ANALYSIS_COLS].isna().sum().reset_index()
    missing_summary.columns = ["Variable", "Missing_Count"]
    missing_summary["Missing_Ratio"] = missing_summary["Missing_Count"] / len(df)

    desc_df = descriptive_analysis(df, ANALYSIS_COLS)

    round_cols = [
        "Min", "Max", "Mean", "Std", "Median",
        "Skewness", "Kurtosis", "KS Statistic", "KS P-value"
    ]
    desc_df[round_cols] = desc_df[round_cols].round(6)
    missing_summary["Missing_Ratio"] = missing_summary["Missing_Ratio"].round(6)

    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="RAW_SELECTED_DATA", index=False)
        desc_df.to_excel(writer, sheet_name="DESCRIPTIVE_STATS", index=False)
        missing_summary.to_excel(writer, sheet_name="MISSING_SUMMARY", index=False)

    print("=" * 70)
    print("描述性统计计算完成")
    print(f"输入文件：{Path(DATA_PATH).resolve()}")
    print(f"输出文件：{Path(OUTPUT_PATH).resolve()}")
    print("分析变量：")
    print(ANALYSIS_COLS)
    print("=" * 70)
    print(desc_df)


if __name__ == "__main__":
    main()