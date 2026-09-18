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

START_YEAR = 2007
END_YEAR = 2024

OUTPUT_DIR = Path("two_indicators_output")
OUTPUT_FILE = OUTPUT_DIR / "URBAN_RURAL_INDICATORS.xlsx"


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


def find_col(
    df: pd.DataFrame,
    candidates: List[str]
) -> Optional[str]:

    col_map = {
        clean_colname(col): col
        for col in df.columns
    }

    # Exact matching
    for candidate in candidates:
        candidate_clean = clean_colname(candidate)

        if candidate_clean in col_map:
            return col_map[candidate_clean]

    # Fuzzy matching
    for candidate in candidates:
        candidate_clean = clean_colname(candidate)

        for cleaned_col, original_col in col_map.items():
            if (
                candidate_clean in cleaned_col
                or cleaned_col in candidate_clean
            ):
                return original_col

    return None


def read_data(
    path: str,
    sheet_name: str
) -> pd.DataFrame:

    path_obj = Path(path)

    if not path_obj.exists():
        raise FileNotFoundError(
            f"File not found: {path_obj.resolve()}"
        )

    suffix = path_obj.suffix.lower()

    if suffix in [".xlsx", ".xls"]:
        df = pd.read_excel(
            path_obj,
            sheet_name=sheet_name
        )

    elif suffix == ".csv":
        df = pd.read_csv(
            path_obj,
            encoding="utf-8-sig"
        )

    else:
        raise ValueError(
            "Only Excel and CSV files are supported."
        )

    df.columns = [
        clean_colname(col)
        for col in df.columns
    ]

    return df


# =========================================================
# Build URIR and REPC
# =========================================================
def build_indicators(df: pd.DataFrame) -> pd.DataFrame:

    # Identification columns
    admin_col = find_col(
        df,
        ["行政区划代码"]
    )

    region_col = find_col(
        df,
        ["地区"]
    )

    zone_col = find_col(
        df,
        ["所属地域"]
    )

    year_col = find_col(
        df,
        ["年份"]
    )

    # Income columns
    urban_income_col = find_col(
        df,
        [
            "城镇居民人均可支配收入(元)",
            "城镇居民人均可支配收入"
        ]
    )

    rural_income_col = find_col(
        df,
        [
            "农村居民人均可支配收入(元)",
            "农村居民人均可支配收入"
        ]
    )

    # Rural electricity and population columns
    rural_electricity_col = find_col(
        df,
        [
            "农村用电量(亿千瓦小时)",
            "农村用电量"
        ]
    )

    rural_population_col = find_col(
        df,
        [
            "乡村人口(万人)",
            "年末乡村人口(万人)",
            "乡村人口"
        ]
    )

    # Check required columns
    required_columns = {
        "地区": region_col,
        "年份": year_col,
        "城镇居民人均可支配收入": urban_income_col,
        "农村居民人均可支配收入": rural_income_col,
        "农村用电量": rural_electricity_col,
        "乡村人口": rural_population_col,
    }

    missing_columns = [
        name
        for name, col in required_columns.items()
        if col is None
    ]

    if missing_columns:
        raise ValueError(
            "The following required columns were not found:\n"
            + "\n".join(missing_columns)
        )

    # Read numeric variables
    year = safe_to_numeric(
        df[year_col]
    )

    urban_income = safe_to_numeric(
        df[urban_income_col]
    )

    rural_income = safe_to_numeric(
        df[rural_income_col]
    )

    rural_electricity = safe_to_numeric(
        df[rural_electricity_col]
    )

    rural_population = safe_to_numeric(
        df[rural_population_col]
    )

    # -----------------------------------------------------
    # Indicator 1: Urban-rural income ratio
    #
    # URIR = Urban per capita disposable income
    #        / Rural per capita disposable income
    #
    # Unit: ratio
    # Direction: negative
    # -----------------------------------------------------
    valid_rural_income = rural_income.replace(
        0,
        np.nan
    )

    urban_rural_income_ratio = (
        urban_income / valid_rural_income
    )

    # -----------------------------------------------------
    # Indicator 2: Rural electricity consumption per capita
    #
    # Rural electricity: 100 million kWh
    # Rural population: 10,000 persons
    #
    # REPC = rural electricity / rural population × 10,000
    #
    # Unit: kWh/person
    # Direction: positive
    # -----------------------------------------------------
    valid_rural_population = rural_population.replace(
        0,
        np.nan
    )

    rural_electricity_per_capita = (
        rural_electricity
        / valid_rural_population
        * 10000
    )

    # Negative values are treated as invalid
    rural_electricity_per_capita = (
        rural_electricity_per_capita.mask(
            rural_electricity_per_capita < 0,
            np.nan
        )
    )

    # -----------------------------------------------------
    # Build output panel
    # -----------------------------------------------------
    result = pd.DataFrame(index=df.index)

    if admin_col is not None:
        result["ADMINCODE"] = df[admin_col]

    result["REGION"] = df[region_col]

    if zone_col is not None:
        result["ZONE"] = df[zone_col]

    result["YEAR"] = year.astype("Int64")

    result["URIR"] = urban_rural_income_ratio
    result["REPC"] = rural_electricity_per_capita

    # Retain the research period
    result = result.loc[
        result["YEAR"].between(
            START_YEAR,
            END_YEAR
        )
    ].copy()

    # Sort by province and year
    result = result.sort_values(
        ["REGION", "YEAR"]
    ).reset_index(drop=True)

    # Round results
    result["URIR"] = result["URIR"].round(6)
    result["REPC"] = result["REPC"].round(6)

    return result


# =========================================================
# Main
# =========================================================
def main() -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    df = read_data(
        INPUT_PATH,
        INPUT_SHEET
    )

    result = build_indicators(df)

    result.to_excel(
        OUTPUT_FILE,
        index=False
    )

    print("=" * 70)
    print("Finished successfully.")
    print(f"Input file: {INPUT_PATH}")
    print(f"Input sheet: {INPUT_SHEET}")
    print(f"Research period: {START_YEAR}-{END_YEAR}")
    print(f"Output file: {OUTPUT_FILE.resolve()}")

    print("\nIndicators:")
    print(
        "URIR = Urban per capita disposable income "
        "/ Rural per capita disposable income"
    )
    print(
        "REPC = Rural electricity consumption "
        "per capita"
    )

    print("\nMissing values:")
    print(
        result[["URIR", "REPC"]]
        .isna()
        .sum()
    )

    print("=" * 70)


if __name__ == "__main__":
    main()