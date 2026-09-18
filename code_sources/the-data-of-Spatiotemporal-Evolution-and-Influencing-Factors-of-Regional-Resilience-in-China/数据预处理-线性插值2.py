import pandas as pd
from pathlib import Path


# =========================
# File settings
# =========================
INPUT_PATH = r"two_indicators_output/URBAN_RURAL_INDICATORS.xlsx"
OUTPUT_PATH = r"URIR_REPC_INTERPOLATED.xlsx"

# 需要插值的两个指标
INDICATOR_COLS = ["URIR", "REPC"]


# =========================
# Read data
# =========================
input_path = Path(INPUT_PATH)

if not input_path.exists():
    raise FileNotFoundError(
        f"未找到输入文件：{input_path.resolve()}"
    )

if input_path.suffix.lower() in [".xlsx", ".xls"]:
    df = pd.read_excel(input_path)

elif input_path.suffix.lower() == ".csv":
    df = pd.read_csv(
        input_path,
        encoding="utf-8-sig"
    )

else:
    raise ValueError("仅支持Excel或CSV文件。")


# =========================
# Check required columns
# =========================
required_cols = ["REGION", "YEAR", "URIR", "REPC"]

missing_cols = [
    col for col in required_cols
    if col not in df.columns
]

if missing_cols:
    raise ValueError(
        "缺少以下字段："
        + ", ".join(missing_cols)
    )


# =========================
# Convert data types
# =========================
df["YEAR"] = pd.to_numeric(
    df["YEAR"],
    errors="coerce"
).astype("Int64")

for col in INDICATOR_COLS:
    df[col] = pd.to_numeric(
        df[col],
        errors="coerce"
    )


# =========================
# Missing values before interpolation
# =========================
missing_before = df[INDICATOR_COLS].isna().sum()


# =========================
# Sort by province and year
# =========================
df = df.sort_values(
    ["REGION", "YEAR"]
).copy()


# =========================
# Linear interpolation by province
# =========================
for col in INDICATOR_COLS:
    df[col] = (
        df.groupby("REGION")[col]
        .transform(
            lambda x: x.interpolate(
                method="linear",
                limit_direction="both"
            )
        )
    )


# =========================
# Round results
# =========================
df["URIR"] = df["URIR"].round(6)
df["REPC"] = df["REPC"].round(6)


# =========================
# Missing values after interpolation
# =========================
missing_after = df[INDICATOR_COLS].isna().sum()


# =========================
# Save result
# =========================
df.to_excel(
    OUTPUT_PATH,
    index=False
)


# =========================
# Print information
# =========================
print("=" * 60)
print("URIR和REPC的分省线性插值已完成。")
print(f"输出文件：{Path(OUTPUT_PATH).resolve()}")

print("\n插值前缺失值：")
print(missing_before)

print("\n插值后缺失值：")
print(missing_after)

print("=" * 60)