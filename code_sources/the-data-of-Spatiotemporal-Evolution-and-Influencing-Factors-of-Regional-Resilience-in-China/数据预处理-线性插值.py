import pandas as pd
from pathlib import Path

# =========================
# File settings
# =========================
INPUT_PATH = r"RESILIENCE_PANEL_EN.xlsx"
INPUT_SHEET = 0          # 如果有指定sheet名字，可以改成 "Sheet1"
OUTPUT_PATH = r"RESILIENCE_PANEL_EN_INTERPOLATED.xlsx"

# =========================
# Read Excel
# =========================
df = pd.read_excel(INPUT_PATH, sheet_name=INPUT_SHEET)

# =========================
# Define id columns and indicator columns
# =========================
id_cols = ["ADMINCODE", "REGION", "ZONE", "YEAR"]
id_cols = [col for col in id_cols if col in df.columns]

indicator_cols = [col for col in df.columns if col not in id_cols]

# 转为数值型
for col in indicator_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# =========================
# Sort by province and year
# =========================
df = df.sort_values(["REGION", "YEAR"]).copy()

# =========================
# Linear interpolation within each province
# =========================
for col in indicator_cols:
    df[col] = df.groupby("REGION")[col].transform(
        lambda x: x.interpolate(method="linear", limit_direction="both")
    )

# =========================
# Save result
# =========================
df.to_excel(OUTPUT_PATH, index=False)

print("线性插值完成。")
print(f"输出文件: {Path(OUTPUT_PATH).resolve()}")