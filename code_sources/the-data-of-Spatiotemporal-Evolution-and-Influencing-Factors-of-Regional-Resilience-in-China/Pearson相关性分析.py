# -*- coding: utf-8 -*-

import pandas as pd
import numpy as np
from pathlib import Path
from scipy import stats

import matplotlib.pyplot as plt

# =========================================================
# 基本设置
# =========================================================
DATA_PATH = r"PANEL_ANALYSIS_DATA.xlsx"
SHEET_NAME = 0

OUTPUT_DIR = Path("DESCRIPTIVE_AND_PEARSON_RESULTS")
OUTPUT_DIR.mkdir(exist_ok=True)

OUTPUT_EXCEL = OUTPUT_DIR / "DESCRIPTIVE_AND_PEARSON_RESULTS.xlsx"
OUTPUT_FIG_PNG = OUTPUT_DIR / "PEARSON_CORRELATION_HEATMAP.png"
OUTPUT_FIG_PDF = OUTPUT_DIR / "PEARSON_CORRELATION_HEATMAP.pdf"

ID_COLS = ["ADMINCODE", "REGION", "ZONE", "YEAR"]

TARGET_COL = "RESILIENCE"

FEATURE_COLS = [
    "URB", "GOV", "INNO", "EDU", "OPENPC",
    "FIN", "DIG", "PRI", "INC", "SOC"
]

ANALYSIS_COLS = [TARGET_COL] + FEATURE_COLS


# =========================================================
# 绘图风格
# =========================================================
plt.rcParams.update({
    "font.family": "Times New Roman",
    "font.weight": "bold",
    "font.size": 16,
    "axes.labelweight": "bold",
    "axes.titleweight": "bold",
    "axes.labelsize": 18,
    "axes.titlesize": 20,
    "xtick.labelsize": 15,
    "ytick.labelsize": 15,
    "legend.fontsize": 14,
    "axes.linewidth": 1.6,
    "axes.edgecolor": "black",
    "axes.unicode_minus": True,
    "xtick.major.width": 1.6,
    "ytick.major.width": 1.6,
    "xtick.major.size": 6,
    "ytick.major.size": 6,
})
plt.rcParams["axes.formatter.use_mathtext"] = True


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

    return pd.DataFrame(records)


# =========================================================
# Pearson相关系数和P值
# =========================================================
def get_numeric_series(df, col):
    s = df.loc[:, col]

    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]

    return pd.to_numeric(s, errors="coerce")


def pearson_corr_pvalue(df, cols):
    corr_mat = pd.DataFrame(index=cols, columns=cols, dtype=float)
    p_mat = pd.DataFrame(index=cols, columns=cols, dtype=float)

    for i in cols:
        for j in cols:

            if i == j:
                corr_mat.loc[i, j] = 1.0
                p_mat.loc[i, j] = np.nan
                continue

            x = get_numeric_series(df, i)
            y = get_numeric_series(df, j)

            tmp = pd.concat([x, y], axis=1)
            tmp.columns = ["x", "y"]
            tmp = tmp.dropna()

            if len(tmp) < 3:
                corr_mat.loc[i, j] = np.nan
                p_mat.loc[i, j] = np.nan
                continue

            std_x = tmp["x"].std(ddof=1)
            std_y = tmp["y"].std(ddof=1)

            if pd.isna(std_x) or pd.isna(std_y) or np.isclose(std_x, 0) or np.isclose(std_y, 0):
                corr_mat.loc[i, j] = np.nan
                p_mat.loc[i, j] = np.nan
                continue

            r, p = stats.pearsonr(tmp["x"], tmp["y"])
            corr_mat.loc[i, j] = r
            p_mat.loc[i, j] = p

    return corr_mat, p_mat


def significance_star(p):
    if pd.isna(p):
        return ""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return ""


# =========================================================
# Pearson相关性热力图
# =========================================================
def plot_pearson_heatmap(corr_mat, p_mat, output_png, output_pdf):
    cols = corr_mat.columns.tolist()
    data = corr_mat.values.astype(float)

    fig, ax = plt.subplots(figsize=(10, 8.5), dpi=400)

    im = ax.imshow(
        data,
        cmap="RdBu_r",
        vmin=-1,
        vmax=1,
        aspect="auto"
    )

    ax.set_xticks(np.arange(len(cols)))
    ax.set_yticks(np.arange(len(cols)))
    ax.set_xticklabels(cols, rotation=45, ha="right", fontweight="bold", fontsize=15)
    ax.set_yticklabels(cols, fontweight="bold", fontsize=15)

    ax.set_title(
        "Pearson Correlation Matrix",
        fontsize=22,
        fontweight="bold",
        pad=20
    )

    for i in range(len(cols)):
        for j in range(len(cols)):
            r = corr_mat.iloc[i, j]
            p = p_mat.iloc[i, j]

            if pd.isna(r):
                text = "NA"
            elif i == j:
                text = "1.00"
            else:
                star = significance_star(p)
                text = f"{r:.2f}{star}"

            color = "white" if abs(r) >= 0.55 else "black"

            ax.text(
                j, i, text,
                ha="center",
                va="center",
                fontsize=12.5,
                fontweight="bold",
                color=color
            )

    ax.set_xticks(np.arange(-0.5, len(cols), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(cols), 1), minor=True)
    ax.grid(which="minor", color="white", linestyle="-", linewidth=1.3)
    ax.tick_params(which="minor", bottom=False, left=False)

    for spine in ax.spines.values():
        spine.set_linewidth(1.8)
        spine.set_color("black")

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cbar.set_label(
        "Pearson Correlation Coefficient",
        fontweight="bold",
        fontsize=16
    )
    cbar.ax.tick_params(labelsize=14, width=1.5, length=5)
    cbar.outline.set_linewidth(1.4)

    fig.text(
        0.5, 0.018,
        "Notes: * p < 0.05, ** p < 0.01, *** p < 0.001.",
        ha="center",
        va="center",
        fontsize=14,
        fontweight="bold"
    )

    plt.tight_layout(rect=[0, 0.045, 1, 1])
    plt.savefig(output_png, dpi=300, bbox_inches="tight")
    plt.savefig(output_pdf, dpi=300, bbox_inches="tight")
    plt.close()


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
    corr_df, pvalue_df = pearson_corr_pvalue(df, ANALYSIS_COLS)

    round_cols = [
        "Min", "Max", "Mean", "Std", "Median",
        "Skewness", "Kurtosis", "KS Statistic", "KS P-value"
    ]
    desc_df[round_cols] = desc_df[round_cols].round(6)
    missing_summary["Missing_Ratio"] = missing_summary["Missing_Ratio"].round(6)

    corr_out = corr_df.round(6)
    pvalue_out = pvalue_df.round(6)

    plot_pearson_heatmap(
        corr_mat=corr_df,
        p_mat=pvalue_df,
        output_png=OUTPUT_FIG_PNG,
        output_pdf=OUTPUT_FIG_PDF
    )

    with pd.ExcelWriter(OUTPUT_EXCEL, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="RAW_SELECTED_DATA", index=False)
        desc_df.to_excel(writer, sheet_name="DESCRIPTIVE_STATS", index=False)
        missing_summary.to_excel(writer, sheet_name="MISSING_SUMMARY", index=False)
        corr_out.to_excel(writer, sheet_name="PEARSON_CORR", index=True)
        pvalue_out.to_excel(writer, sheet_name="PEARSON_PVALUE", index=True)

    print("=" * 70)
    print("描述性统计与Pearson相关性分析完成")
    print(f"输入文件：{Path(DATA_PATH).resolve()}")
    print(f"输出Excel：{Path(OUTPUT_EXCEL).resolve()}")
    print(f"相关性热力图PNG：{Path(OUTPUT_FIG_PNG).resolve()}")
    print(f"相关性热力图PDF：{Path(OUTPUT_FIG_PDF).resolve()}")
    print("=" * 70)
    print("\n描述性统计预览：")
    print(desc_df)
    print("\nPearson相关系数预览：")
    print(corr_out)


if __name__ == "__main__":
    main()