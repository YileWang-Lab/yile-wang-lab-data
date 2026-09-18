import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.decomposition import PCA, FactorAnalysis
from sklearn.preprocessing import StandardScaler

# =========================================================
# 基本设置
# =========================================================
INPUT_PATH = r"RESILIENCE_PANEL_EN_INTERPOLATED.xlsx"   # 你的线性插值后Excel
INPUT_SHEET = 0                                         # 如果有sheet名，也可以改成 "Sheet1"
OUTPUT_PATH = r"REGIONAL_RESILIENCE_MULTI_METHOD_RESULTS.xlsx"

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


def normalize_score(score: pd.Series) -> pd.Series:
    """把综合得分统一归一化到[0,1]，便于方法间比较"""
    s = pd.to_numeric(score, errors="coerce").astype(float)
    mn = s.min(skipna=True)
    mx = s.max(skipna=True)

    if pd.isna(mn) or pd.isna(mx):
        return pd.Series(np.nan, index=s.index)

    if np.isclose(mx, mn):
        return pd.Series(1.0, index=s.index)

    return (s - mn) / (mx - mn)


# =========================================================
# 1. 熵权法
# =========================================================
def entropy_weight_method(z: pd.DataFrame):
    zf = z.copy().astype(float)
    zf = zf.fillna(zf.median())
    zf = zf + 1e-12

    p = zf.div(zf.sum(axis=0), axis=1)
    n = zf.shape[0]
    e = -(p * np.log(p)).sum(axis=0) / np.log(n)
    d = 1 - e
    w = d / d.sum()

    weight_df = pd.DataFrame({
        "INDICATOR": z.columns,
        "ENTROPY": e.values,
        "REDUNDANCY": d.values,
        "WEIGHT": w.values
    }).sort_values("WEIGHT", ascending=False).reset_index(drop=True)

    score = (zf * w).sum(axis=1)
    score = normalize_score(score)

    return weight_df, score


# =========================================================
# 2. 变异系数法
# =========================================================
def cv_weight_method(z: pd.DataFrame, eps: float = 1e-12):
    zf = z.copy().astype(float)
    zf = zf.fillna(zf.median())

    mean = zf.mean(axis=0)
    std = zf.std(axis=0, ddof=1)
    cv = std / (mean + eps)
    w = cv / cv.sum()

    weight_df = pd.DataFrame({
        "INDICATOR": z.columns,
        "MEAN": mean.values,
        "STD": std.values,
        "CV": cv.values,
        "WEIGHT": w.values
    }).sort_values("WEIGHT", ascending=False).reset_index(drop=True)

    score = (zf * w).sum(axis=1)
    score = normalize_score(score)

    return weight_df, score


# =========================================================
# 3. 最大离差法（DM）
# =========================================================
def deviation_maximization_method(z: pd.DataFrame):
    zf = z.copy().astype(float)
    zf = zf.fillna(zf.median())

    D_list = []
    for col in z.columns:
        x = zf[col].to_numpy(dtype=float)
        D = np.abs(x[:, None] - x[None, :]).sum()
        D_list.append(D)

    D_arr = np.array(D_list, dtype=float)
    w = D_arr / D_arr.sum()

    weight_df = pd.DataFrame({
        "INDICATOR": z.columns,
        "D": D_arr,
        "WEIGHT": w
    }).sort_values("WEIGHT", ascending=False).reset_index(drop=True)

    weight_series = pd.Series(w, index=z.columns)
    score = (zf * weight_series).sum(axis=1)
    score = normalize_score(score)

    return weight_df, score


# =========================================================
# 4. PCA
# =========================================================
def pca_method(z: pd.DataFrame):
    zf = z.copy().astype(float)
    zf = zf.fillna(zf.median())

    # PCA 一般基于标准化后的数据再做一次均值-方差标准化
    scaler = StandardScaler()
    X_std = scaler.fit_transform(zf)

    pca_full = PCA()
    pca_full.fit(X_std)

    eigvals = pca_full.explained_variance_
    n_components = int(np.sum(eigvals > 1))
    if n_components < 1:
        n_components = 1

    pca = PCA(n_components=n_components)
    comp_scores = pca.fit_transform(X_std)

    weights = pca.explained_variance_ratio_ / pca.explained_variance_ratio_.sum()
    composite_score = comp_scores @ weights
    composite_score = pd.Series(composite_score, index=z.index)
    composite_score = normalize_score(composite_score)

    loadings = pd.DataFrame(
        pca.components_.T,
        index=z.columns,
        columns=[f"PC{i+1}" for i in range(n_components)]
    )

    info_df = pd.DataFrame({
        "Component": [f"PC{i+1}" for i in range(n_components)],
        "Eigenvalue": pca.explained_variance_,
        "Explained_Variance_Ratio": pca.explained_variance_ratio_,
        "Cumulative_Explained_Ratio": np.cumsum(pca.explained_variance_ratio_)
    })

    return info_df, loadings, composite_score


# =========================================================
# 5. 因子分析法（因子分）
# 说明：
# 这里用 sklearn 的 FactorAnalysis 实现因子得分，
# 因子个数按 Kaiser 准则（特征值 > 1）确定，
# 综合因子分按各因子得分方差占比加权。
# =========================================================
def factor_score_method(z: pd.DataFrame):
    zf = z.copy().astype(float)
    zf = zf.fillna(zf.median())

    scaler = StandardScaler()
    X_std = scaler.fit_transform(zf)

    # 用相关矩阵特征值判断因子数
    corr = np.corrcoef(X_std, rowvar=False)
    eigvals = np.linalg.eigvalsh(corr)[::-1]
    n_factors = int(np.sum(eigvals > 1))
    if n_factors < 1:
        n_factors = 1
    if n_factors > X_std.shape[1]:
        n_factors = X_std.shape[1]

    fa = FactorAnalysis(n_components=n_factors, random_state=42)
    factor_scores = fa.fit_transform(X_std)

    # 因子载荷矩阵
    loadings = pd.DataFrame(
        fa.components_.T,
        index=z.columns,
        columns=[f"F{i+1}" for i in range(n_factors)]
    )

    # 用因子得分方差作为权重近似
    factor_var = np.var(factor_scores, axis=0, ddof=1)
    factor_weights = factor_var / factor_var.sum()

    composite_score = factor_scores @ factor_weights
    composite_score = pd.Series(composite_score, index=z.index)
    composite_score = normalize_score(composite_score)

    info_df = pd.DataFrame({
        "Factor": [f"F{i+1}" for i in range(n_factors)],
        "Factor_Score_Variance": factor_var,
        "Weight": factor_weights,
        "Cumulative_Weight": np.cumsum(factor_weights)
    })

    return info_df, loadings, composite_score


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
        print("警告：数据中仍存在缺失值，建议先完成插值后再计算。")
        print(missing_summary[missing_summary > 0])

    # 标准化
    z = standardize_data(df, indicator_cols, POLARITY)

    # 若标准化后仍有缺失，用该指标中位数补齐
    z = z.apply(lambda col: col.fillna(col.median()), axis=0)

    # =====================================================
    # 各方法计算
    # =====================================================
    entropy_weight_df, entropy_score = entropy_weight_method(z)
    cv_weight_df, cv_score = cv_weight_method(z)
    dm_weight_df, dm_score = deviation_maximization_method(z)
    pca_info_df, pca_loadings_df, pca_score = pca_method(z)
    factor_info_df, factor_loadings_df, factor_score = factor_score_method(z)

    # 汇总得分
    score_df = df[id_cols + indicator_cols].copy()
    score_df["SCORE_ENTROPY"] = entropy_score
    score_df["SCORE_CV"] = cv_score
    score_df["SCORE_DM"] = dm_score
    score_df["SCORE_PCA"] = pca_score
    score_df["SCORE_FACTOR"] = factor_score

    # 保留小数位
    z = z.round(6)
    entropy_weight_df = entropy_weight_df.round(6)
    cv_weight_df = cv_weight_df.round(6)
    dm_weight_df = dm_weight_df.round(6)
    pca_info_df = pca_info_df.round(6)
    pca_loadings_df = pca_loadings_df.round(6)
    factor_info_df = factor_info_df.round(6)
    factor_loadings_df = factor_loadings_df.round(6)

    score_cols = ["SCORE_ENTROPY", "SCORE_CV", "SCORE_DM", "SCORE_PCA", "SCORE_FACTOR"]
    score_df[score_cols] = score_df[score_cols].round(6)

    # 输出Excel
    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="RAW_DATA", index=False)
        z.to_excel(writer, sheet_name="STANDARDIZED", index=False)

        entropy_weight_df.to_excel(writer, sheet_name="ENTROPY_WEIGHTS", index=False)
        cv_weight_df.to_excel(writer, sheet_name="CV_WEIGHTS", index=False)
        dm_weight_df.to_excel(writer, sheet_name="DM_WEIGHTS", index=False)

        pca_info_df.to_excel(writer, sheet_name="PCA_INFO", index=False)
        pca_loadings_df.to_excel(writer, sheet_name="PCA_LOADINGS", index=True)

        factor_info_df.to_excel(writer, sheet_name="FACTOR_INFO", index=False)
        factor_loadings_df.to_excel(writer, sheet_name="FACTOR_LOADINGS", index=True)

        score_df.to_excel(writer, sheet_name="SCORES_ALL", index=False)

    print("=" * 70)
    print("区域韧性五种方法计算完成")
    print(f"输入文件: {Path(INPUT_PATH).resolve()}")
    print(f"输出文件: {Path(OUTPUT_PATH).resolve()}")
    print(f"使用指标数: {len(indicator_cols)}")
    print("结果文件包含以下sheet：")
    print("1. RAW_DATA")
    print("2. STANDARDIZED")
    print("3. ENTROPY_WEIGHTS")
    print("4. CV_WEIGHTS")
    print("5. DM_WEIGHTS")
    print("6. PCA_INFO")
    print("7. PCA_LOADINGS")
    print("8. FACTOR_INFO")
    print("9. FACTOR_LOADINGS")
    print("10. SCORES_ALL")
    print("=" * 70)
    print("\n熵权法权重预览：")
    print(entropy_weight_df.head())
    print("\n变异系数法权重预览：")
    print(cv_weight_df.head())
    print("\n最大离差法权重预览：")
    print(dm_weight_df.head())


if __name__ == "__main__":
    main()