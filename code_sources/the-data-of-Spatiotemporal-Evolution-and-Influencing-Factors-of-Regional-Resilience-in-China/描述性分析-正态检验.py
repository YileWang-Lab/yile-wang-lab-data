import pandas as pd
import numpy as np
from pathlib import Path
from scipy.stats import kstest

# =========================
# 文件设置
# =========================
INPUT_PATH = r"RESILIENCE_PANEL_EN_INTERPOLATED.xlsx"
INPUT_SHEET = 0   # 如果有指定sheet名，可以改成 "Sheet1"
OUTPUT_PATH = r"DESCRIPTIVE_STATISTICS_KS.xlsx"

# =========================
# 读取数据
# =========================
df = pd.read_excel(INPUT_PATH, sheet_name=INPUT_SHEET)

# =========================
# ID列与指标列
# =========================
id_cols = ["ADMINCODE", "REGION", "ZONE", "YEAR"]
id_cols = [col for col in id_cols if col in df.columns]

indicator_cols = [
    "PCGDP", "PCRS", "FSR", "TIG",
    "RUUR", "HBTP", "IPR", "URIR",
    "GCR", "WEI", "SDEI", "EPES",
    "UGPR", "UWPR", "PCURA", "REPC"
]

# 只保留实际存在的列
indicator_cols = [col for col in indicator_cols if col in df.columns]

# 转成数值型
for col in indicator_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# =========================
# 描述性统计 + KS正态检验
# =========================
results = []

for col in indicator_cols:
    series = df[col].dropna()

    n = len(series)
    min_val = series.min() if n > 0 else np.nan
    max_val = series.max() if n > 0 else np.nan
    mean_val = series.mean() if n > 0 else np.nan
    var_val = series.var(ddof=1) if n > 1 else np.nan
    std_val = series.std(ddof=1) if n > 1 else np.nan

    # KS 正态检验
    if n > 2 and std_val is not None and not np.isnan(std_val) and std_val > 0:
        z = (series - mean_val) / std_val
        ks_stat, ks_p = kstest(z, 'norm')
        normality = "Normal" if ks_p > 0.05 else "Non-normal"
    else:
        ks_stat, ks_p, normality = np.nan, np.nan, "Not applicable"

    results.append({
        "Variable": col,
        "N": n,
        "Min": min_val,
        "Max": max_val,
        "Mean": mean_val,
        "Variance": var_val,
        "Std": std_val,
        "KS Statistic": ks_stat,
        "KS P-value": ks_p,
        "Normality": normality
    })

result_df = pd.DataFrame(results)

# =========================
# 保留小数位
# =========================
numeric_cols = ["Min", "Max", "Mean", "Variance", "Std", "KS Statistic", "KS P-value"]
result_df[numeric_cols] = result_df[numeric_cols].round(6)

# =========================
# 输出结果
# =========================
result_df.to_excel(OUTPUT_PATH, index=False)

print("描述性统计与KS正态检验完成。")
print(f"输出文件: {Path(OUTPUT_PATH).resolve()}")
print(result_df)