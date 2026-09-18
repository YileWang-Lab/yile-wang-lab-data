import pandas as pd
import numpy as np
from pathlib import Path

# =========================================================
# 基本设置
# =========================================================
INPUT_PATH = r"RESILIENCE_PANEL_EN_INTERPOLATED.xlsx"   # 你的线性插值后Excel
INPUT_SHEET = 0                                         # 如果有sheet名，也可以改成 "Sheet1"
OUTPUT_PATH = r"SPEARMAN_CRITIC_CRITERION_RESULTS.xlsx"

# 是否在每个准则层内部重新归一化权重
# False：直接使用16个指标的全局Spearman-CRITIC权重（推荐）
# True：在ER/SDR/EER/IR内部把对应权重重新归一化后再加权
NORMALIZE_WITHIN_CRITERION = False

# ID列
ID_COLS = ["ADMINCODE", "REGION", "ZONE", "YEAR"]

# 指标列
INDICATOR_COLS = [
    "PCGDP", "PCRS", "FSR", "TIG",
    "RUUR", "HBTP", "IPR", "HESP",
    "GCR", "WEI", "SDEI", "EPES",
    "UGPR", "UWPR", "PCURA", "PTVP"
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
    "HESP": "+",
    "GCR": "+",
    "WEI": "-",
    "SDEI": "-",
    "EPES": "+",
    "UGPR": "+",
    "UWPR": "+",
    "PCURA": "+",
    "PTVP": "+"
}

# 四个准则层
CRITERION_GROUPS = {
    "ER": ["PCGDP", "PCRS", "FSR", "TIG"],
    "SDR": ["RUUR", "HBTP", "IPR", "HESP"],
    "EER": ["GCR", "WEI", "SDEI", "EPES"],
    "IR": ["UGPR", "UWPR", "PCURA", "PTVP"]
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


def compute_overall_score(z: pd.DataFrame, weight_df: pd.DataFrame) -> pd.Series:
    """计算总体韧性得分"""
    weights = weight_df.set_index("INDICATOR")["WEIGHT"]
    score = z.mul(weights, axis=1).sum(axis=1)
    return score


def compute_criterion_scores(
    z: pd.DataFrame,
    weight_df: pd.DataFrame,
    criterion_groups: dict,
    normalize_within_criterion: bool = False
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    用16个指标的全局Spearman-CRITIC权重，分别计算ER/SDR/EER/IR
    """
    global_weights = weight_df.set_index("INDICATOR")["WEIGHT"]
    result = pd.DataFrame(index=z.index)
    criterion_weight_records = []

    for criterion, indicators in criterion_groups.items():
        existing_indicators = [c for c in indicators if c in z.columns]
        if len(existing_indicators) == 0:
            continue

        w = global_weights.loc[existing_indicators].copy()

        if normalize_within_criterion:
            w = w / w.sum()

        result[criterion] = z[existing_indicators].mul(w, axis=1).sum(axis=1)

        tmp = pd.DataFrame({
            "CRITERION": criterion,
            "INDICATOR": existing_indicators,
            "GLOBAL_WEIGHT": global_weights.loc[existing_indicators].values,
            "USED_WEIGHT": w.values
        })
        criterion_weight_records.append(tmp)

    criterion_weight_df = pd.concat(criterion_weight_records, axis=0, ignore_index=True)
    return result, criterion_weight_df


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

    # 计算16个指标的全局Spearman-CRITIC权重
    weight_df, corr_df = compute_spearman_critic_weights(z)

    # 计算总体韧性得分
    overall_score = compute_overall_score(z, weight_df)

    # 计算四个准则层得分
    criterion_scores_df, criterion_weight_df = compute_criterion_scores(
        z=z,
        weight_df=weight_df,
        criterion_groups=CRITERION_GROUPS,
        normalize_within_criterion=NORMALIZE_WITHIN_CRITERION
    )

    # 汇总结果
    result_df = df[id_cols + indicator_cols].copy()
    result_df["RESILIENCE_SCORE"] = overall_score

    for col in ["ER", "SDR", "EER", "IR"]:
        if col in criterion_scores_df.columns:
            result_df[col] = criterion_scores_df[col]

    # 保留小数位
    numeric_weight_cols = ["STD", "CONFLICT", "C_VALUE", "WEIGHT"]
    weight_df[numeric_weight_cols] = weight_df[numeric_weight_cols].round(6)

    criterion_weight_df[["GLOBAL_WEIGHT", "USED_WEIGHT"]] = criterion_weight_df[
        ["GLOBAL_WEIGHT", "USED_WEIGHT"]
    ].round(6)

    corr_df = corr_df.round(6)
    z = z.round(6)

    score_cols = [c for c in ["RESILIENCE_SCORE", "ER", "SDR", "EER", "IR"] if c in result_df.columns]
    result_df[score_cols] = result_df[score_cols].round(6)

    # 输出Excel
    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="RAW_DATA", index=False)
        z.to_excel(writer, sheet_name="STANDARDIZED", index=False)
        weight_df.to_excel(writer, sheet_name="GLOBAL_WEIGHTS", index=False)
        corr_df.to_excel(writer, sheet_name="SPEARMAN_CORR", index=True)
        criterion_weight_df.to_excel(writer, sheet_name="CRITERION_WEIGHTS", index=False)
        result_df.to_excel(writer, sheet_name="CRITERION_SCORES", index=False)

    print("=" * 70)
    print("Spearman-CRITIC 全局权重与四个准则层得分计算完成")
    print(f"输入文件: {Path(INPUT_PATH).resolve()}")
    print(f"输出文件: {Path(OUTPUT_PATH).resolve()}")
    print(f"使用指标数: {len(indicator_cols)}")
    print(f"是否在准则层内归一化权重: {NORMALIZE_WITHIN_CRITERION}")
    print("结果文件包含以下sheet：")
    print("1. RAW_DATA")
    print("2. STANDARDIZED")
    print("3. GLOBAL_WEIGHTS")
    print("4. SPEARMAN_CORR")
    print("5. CRITERION_WEIGHTS")
    print("6. CRITERION_SCORES")
    print("=" * 70)
    print("\n16个指标全局权重预览：")
    print(weight_df.head())
    print("\n准则层权重使用情况预览：")
    print(criterion_weight_df.head(16))


if __name__ == "__main__":
    main()