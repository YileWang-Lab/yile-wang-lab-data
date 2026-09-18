import pandas as pd
import numpy as np
from pathlib import Path

# =========================================================
# 基本设置
# =========================================================
INPUT_PATH = r"RESILIENCE_PANEL_EN_INTERPOLATED.xlsx"   # 你的线性插值后Excel
INPUT_SHEET = 0                                         # 如果有sheet名，也可以改成 "Sheet1"
OUTPUT_PATH = r"SPEARMAN_CRITIC_RESULTS.xlsx"

# ID列
ID_COLS = ["ADMINCODE", "REGION", "ZONE", "YEAR"]

# 指标列
INDICATOR_COLS = [
    "PCGDP", "PCRS", "FSR", "TIG",
    "RUUR", "HBTP", "IPR", "URIR",
    "GCR", "WEI", "SDEI", "EPES",
    "UGPR", "UWPR", "PCURA", "REPC"
]

# 指标方向：+ 为正向，- 为负向
POLARITY = {
    "PCGDP": "+",
    "PCRS": "+",
    "FSR": "+",
    "TIG": "+",
    "RUUR": "-",
    "HBTP": "+",
    "IPR": "+",
    "URIR": "-",
    "GCR": "+",
    "WEI": "-",
    "SDEI": "-",
    "EPES": "+",
    "UGPR": "+",
    "UWPR": "+",
    "PCURA": "+",
    "REPC": "+"
}


# =========================================================
# 工具函数
# =========================================================
def minmax_positive(series: pd.Series) -> pd.Series:
    """正向指标标准化"""
    s = pd.to_numeric(series, errors="coerce").astype(float)
    mn = s.min(skipna=True)
    mx = s.max(skipna=True)

    if pd.isna(mn) or pd.isna(mx):
        return pd.Series(np.nan, index=s.index)

    if np.isclose(mx, mn):
        return pd.Series(1.0, index=s.index)

    return (s - mn) / (mx - mn)


def minmax_negative(series: pd.Series) -> pd.Series:
    """负向指标正向化后再标准化"""
    s = pd.to_numeric(series, errors="coerce").astype(float)
    mn = s.min(skipna=True)
    mx = s.max(skipna=True)

    if pd.isna(mn) or pd.isna(mx):
        return pd.Series(np.nan, index=s.index)

    if np.isclose(mx, mn):
        return pd.Series(1.0, index=s.index)

    return (mx - s) / (mx - mn)


def standardize_data(df: pd.DataFrame, indicator_cols: list, polarity: dict) -> pd.DataFrame:
    """按指标方向做正向化+极差标准化"""
    z = pd.DataFrame(index=df.index)

    for col in indicator_cols:
        if polarity[col] == "+":
            z[col] = minmax_positive(df[col])
        else:
            z[col] = minmax_negative(df[col])

    return z


def compute_spearman_critic_weights(z: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    基于标准化矩阵 z 计算 Spearman-CRITIC 权重
    C_j = s_j * sum(1 - r_jk)
    """
    # 标准差
    std = z.std(axis=0, ddof=1)

    # Spearman相关矩阵
    corr = z.corr(method="spearman")

    # 冲突性
    conflict = (1 - corr).sum(axis=1)

    # 信息量
    c_value = std * conflict

    # 权重
    weights = c_value / c_value.sum()

    weight_df = pd.DataFrame({
        "INDICATOR": z.columns,
        "STD": std.values,
        "CONFLICT": conflict.values,
        "C_VALUE": c_value.values,
        "WEIGHT": weights.values
    }).sort_values("WEIGHT", ascending=False).reset_index(drop=True)

    return weight_df, corr


def compute_scores(df: pd.DataFrame, z: pd.DataFrame, weight_df: pd.DataFrame) -> pd.DataFrame:
    """计算综合得分"""
    weights = weight_df.set_index("INDICATOR")["WEIGHT"]
    score = z.mul(weights, axis=1).sum(axis=1)

    result = df.copy()
    result["RESILIENCE_SCORE"] = score
    return result


# =========================================================
# 主程序
# =========================================================
def main():
    input_file = Path(INPUT_PATH)
    if not input_file.exists():
        raise FileNotFoundError(f"找不到输入文件: {INPUT_PATH}")

    # 读取Excel
    df = pd.read_excel(INPUT_PATH, sheet_name=INPUT_SHEET)

    # 保留实际存在的ID列和指标列
    id_cols = [col for col in ID_COLS if col in df.columns]
    indicator_cols = [col for col in INDICATOR_COLS if col in df.columns]

    if len(indicator_cols) == 0:
        raise ValueError("未识别到任何指标列，请检查文件列名是否正确。")

    # 转为数值型
    for col in indicator_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 检查缺失
    missing_summary = df[indicator_cols].isna().sum()
    if missing_summary.sum() > 0:
        print("警告：数据中仍存在缺失值，建议先完成插值后再计算权重。")
        print(missing_summary[missing_summary > 0])

    # 标准化
    z = standardize_data(df, indicator_cols, POLARITY)

    # 若标准化后仍有缺失，用该指标中位数补齐
    z = z.apply(lambda col: col.fillna(col.median()), axis=0)

    # 计算权重
    weight_df, corr_df = compute_spearman_critic_weights(z)

    # 计算得分
    score_df = compute_scores(df[id_cols + indicator_cols], z, weight_df)

    # 保留小数位
    numeric_weight_cols = ["STD", "CONFLICT", "C_VALUE", "WEIGHT"]
    weight_df[numeric_weight_cols] = weight_df[numeric_weight_cols].round(6)

    corr_df = corr_df.round(6)
    z = z.round(6)
    score_df["RESILIENCE_SCORE"] = score_df["RESILIENCE_SCORE"].round(6)

    # 输出Excel
    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="RAW_DATA", index=False)
        z.to_excel(writer, sheet_name="STANDARDIZED", index=False)
        weight_df.to_excel(writer, sheet_name="WEIGHTS", index=False)
        corr_df.to_excel(writer, sheet_name="SPEARMAN_CORR", index=True)
        score_df.to_excel(writer, sheet_name="SCORES", index=False)

    print("=" * 70)
    print("Spearman-CRITIC 计算完成")
    print(f"输入文件: {Path(INPUT_PATH).resolve()}")
    print(f"输出文件: {Path(OUTPUT_PATH).resolve()}")
    print(f"使用指标数: {len(indicator_cols)}")
    print("结果文件包含以下sheet：")
    print("1. RAW_DATA")
    print("2. STANDARDIZED")
    print("3. WEIGHTS")
    print("4. SPEARMAN_CORR")
    print("5. SCORES")
    print("=" * 70)
    print("\n权重结果预览：")
    print(weight_df)


if __name__ == "__main__":
    main()