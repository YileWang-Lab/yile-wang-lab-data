# -*- coding: utf-8 -*-

from pathlib import Path

import numpy as np
import pandas as pd


# =========================================================
# 1. File settings
# =========================================================
INPUT_PATH = Path(
    r"RESILIENCE_PANEL_EN_INTERPOLATED.xlsx"
)

INPUT_SHEET = 0

OUTPUT_DIR = Path(
    "LEAVE_ONE_INDICATOR_OUT_RESULTS"
)

OUTPUT_PATH = (
    OUTPUT_DIR
    / "TABLE_A4_LEAVE_ONE_INDICATOR_OUT.xlsx"
)


# =========================================================
# 2. Identification columns
# =========================================================
ID_COLS = [
    "ADMINCODE",
    "REGION",
    "ZONE",
    "YEAR",
]


# =========================================================
# 3. Regional resilience indicators
# =========================================================
POSITIVE_INDICATORS = [
    "PCGDP",
    "PCRS",
    "FSR",
    "TIG",
    "HBTP",
    "IPR",
    "GCR",
    "EPES",
    "UGPR",
    "UWPR",
    "PCURA",
    "REPC",
]

NEGATIVE_INDICATORS = [
    "RUUR",
    "URIR",
    "WEI",
    "SDEI",
]

ALL_INDICATORS = (
    POSITIVE_INDICATORS
    + NEGATIVE_INDICATORS
)


# =========================================================
# 4. Utility functions
# =========================================================
def clean_colname(name):
    return (
        str(name)
        .strip()
        .replace("\u3000", " ")
        .replace("\n", "")
        .replace("\r", "")
    )


def safe_to_numeric(series):
    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.strip(),
        errors="coerce",
    )


# =========================================================
# 5. Read data
# =========================================================
def read_data():
    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"未找到输入文件：{INPUT_PATH.resolve()}"
        )

    suffix = INPUT_PATH.suffix.lower()

    if suffix in [".xlsx", ".xls"]:
        df = pd.read_excel(
            INPUT_PATH,
            sheet_name=INPUT_SHEET,
        )

    elif suffix == ".csv":
        df = pd.read_csv(
            INPUT_PATH,
            encoding="utf-8-sig",
        )

    else:
        raise ValueError(
            "仅支持Excel或CSV文件。"
        )

    df.columns = [
        clean_colname(col)
        for col in df.columns
    ]

    return df


# =========================================================
# 6. Check and prepare data
# =========================================================
def prepare_data(df):
    required_cols = [
        "REGION",
        "YEAR",
    ] + ALL_INDICATORS

    missing_cols = [
        col
        for col in required_cols
        if col not in df.columns
    ]

    if missing_cols:
        raise ValueError(
            "数据缺少以下字段：\n"
            + "\n".join(missing_cols)
        )

    keep_cols = [
        col
        for col in ID_COLS
        if col in df.columns
    ] + ALL_INDICATORS

    df = df[keep_cols].copy()

    df["YEAR"] = safe_to_numeric(
        df["YEAR"]
    ).astype("Int64")

    for col in ALL_INDICATORS:
        df[col] = safe_to_numeric(
            df[col]
        )

        df[col] = df[col].replace(
            [np.inf, -np.inf],
            np.nan,
        )

    missing_counts = (
        df[ALL_INDICATORS]
        .isna()
        .sum()
    )

    if missing_counts.sum() > 0:
        print("\n各指标缺失值数量：")
        print(
            missing_counts[
                missing_counts > 0
            ]
        )

        raise ValueError(
            "\n数据仍然存在缺失值。"
            "请先使用完成线性插值的数据。"
        )

    duplicated = df.duplicated(
        subset=["REGION", "YEAR"]
    )

    if duplicated.any():
        duplicate_rows = df.loc[
            duplicated,
            ["REGION", "YEAR"],
        ]

        raise ValueError(
            "存在重复的省份—年份观测：\n"
            f"{duplicate_rows}"
        )

    df = df.sort_values(
        ["YEAR", "REGION"]
    ).reset_index(drop=True)

    return df


# =========================================================
# 7. Min-max standardization
# =========================================================
def min_max_standardize(
    df,
    indicators,
):
    standardized = pd.DataFrame(
        index=df.index
    )

    for col in indicators:
        values = df[col].astype(float)

        minimum = values.min()
        maximum = values.max()
        value_range = maximum - minimum

        if np.isclose(value_range, 0):
            raise ValueError(
                f"指标 {col} 没有变化，"
                "无法进行极差标准化。"
            )

        if col in POSITIVE_INDICATORS:
            standardized[col] = (
                values - minimum
            ) / value_range

        elif col in NEGATIVE_INDICATORS:
            standardized[col] = (
                maximum - values
            ) / value_range

        else:
            raise ValueError(
                f"没有设置指标方向：{col}"
            )

    return standardized


# =========================================================
# 8. Spearman-CRITIC weights
# =========================================================
def calculate_spearman_critic(
    df,
    indicators,
):
    standardized = min_max_standardize(
        df,
        indicators,
    )

    standard_deviation = (
        standardized[indicators]
        .std(axis=0, ddof=1)
    )

    spearman_correlation = (
        standardized[indicators]
        .corr(method="spearman")
    )

    information_conflict = (
        1.0 - spearman_correlation
    ).sum(axis=1)

    information_content = (
        standard_deviation
        * information_conflict
    )

    total_information = (
        information_content.sum()
    )

    if (
        pd.isna(total_information)
        or np.isclose(
            total_information,
            0,
        )
    ):
        raise ValueError(
            "CRITIC信息量之和为0，"
            "无法计算权重。"
        )

    weights = (
        information_content
        / total_information
    )

    resilience_score = (
        standardized[indicators]
        * weights
    ).sum(axis=1)

    weight_table = pd.DataFrame(
        {
            "Indicator": indicators,
            "Standard_Deviation": (
                standard_deviation[
                    indicators
                ].values
            ),
            "Information_Conflict": (
                information_conflict[
                    indicators
                ].values
            ),
            "Information_Content": (
                information_content[
                    indicators
                ].values
            ),
            "Weight": (
                weights[
                    indicators
                ].values
            ),
        }
    )

    return (
        resilience_score,
        weight_table,
    )


# =========================================================
# 9. Calculate province rankings
# =========================================================
def calculate_yearly_rank(
    data,
    score_col,
):
    return (
        data.groupby("YEAR")[score_col]
        .rank(
            method="average",
            ascending=False,
        )
    )


# =========================================================
# 10. Calculate comparison statistics
# =========================================================
def compare_with_complete_index(
    data,
    reduced_score_col,
    reduced_rank_col,
):
    valid_data = data[
        [
            "FULL_INDEX",
            reduced_score_col,
            "FULL_RANK",
            reduced_rank_col,
        ]
    ].dropna()

    correlation = (
        valid_data["FULL_INDEX"]
        .corr(
            valid_data[reduced_score_col],
            method="spearman",
        )
    )

    absolute_rank_change = (
        valid_data["FULL_RANK"]
        - valid_data[reduced_rank_col]
    ).abs()

    mean_absolute_rank_change = (
        absolute_rank_change.mean()
    )

    maximum_rank_change = (
        absolute_rank_change.max()
    )

    unchanged_rank_percentage = (
        absolute_rank_change.eq(0).mean()
        * 100
    )

    return {
        "Correlation with the complete index": (
            correlation
        ),
        "Mean absolute rank change": (
            mean_absolute_rank_change
        ),
        "Maximum rank change": (
            maximum_rank_change
        ),
        "Unchanged ranks (%)": (
            unchanged_rank_percentage
        ),
    }


# =========================================================
# 11. Main calculation
# =========================================================
def main():
    print("=" * 72)
    print(
        "Leave-one-indicator-out analysis "
        "for URIR and REPC"
    )
    print("=" * 72)

    df = read_data()
    df = prepare_data(df)

    print(f"输入文件：{INPUT_PATH.resolve()}")
    print(f"样本数量：{len(df)}")
    print(
        f"年份范围："
        f"{df['YEAR'].min()}-"
        f"{df['YEAR'].max()}"
    )
    print(
        f"省份数量："
        f"{df['REGION'].nunique()}"
    )

    # -----------------------------------------------------
    # Complete index
    # -----------------------------------------------------
    full_indicators = ALL_INDICATORS.copy()

    full_score, full_weights = (
        calculate_spearman_critic(
            df,
            full_indicators,
        )
    )

    df["FULL_INDEX"] = full_score

    # -----------------------------------------------------
    # Index excluding URIR
    # -----------------------------------------------------
    indicators_without_urir = [
        col
        for col in ALL_INDICATORS
        if col != "URIR"
    ]

    score_without_urir, weights_without_urir = (
        calculate_spearman_critic(
            df,
            indicators_without_urir,
        )
    )

    df["INDEX_WITHOUT_URIR"] = (
        score_without_urir
    )

    # -----------------------------------------------------
    # Index excluding REPC
    # -----------------------------------------------------
    indicators_without_repc = [
        col
        for col in ALL_INDICATORS
        if col != "REPC"
    ]

    score_without_repc, weights_without_repc = (
        calculate_spearman_critic(
            df,
            indicators_without_repc,
        )
    )

    df["INDEX_WITHOUT_REPC"] = (
        score_without_repc
    )

    # -----------------------------------------------------
    # Index excluding both URIR and REPC
    # -----------------------------------------------------
    indicators_without_both = [
        col
        for col in ALL_INDICATORS
        if col not in ["URIR", "REPC"]
    ]

    score_without_both, weights_without_both = (
        calculate_spearman_critic(
            df,
            indicators_without_both,
        )
    )

    df["INDEX_WITHOUT_BOTH"] = (
        score_without_both
    )

    # -----------------------------------------------------
    # Provincial rankings within each year
    # -----------------------------------------------------
    df["FULL_RANK"] = (
        calculate_yearly_rank(
            df,
            "FULL_INDEX",
        )
    )

    df["RANK_WITHOUT_URIR"] = (
        calculate_yearly_rank(
            df,
            "INDEX_WITHOUT_URIR",
        )
    )

    df["RANK_WITHOUT_REPC"] = (
        calculate_yearly_rank(
            df,
            "INDEX_WITHOUT_REPC",
        )
    )

    df["RANK_WITHOUT_BOTH"] = (
        calculate_yearly_rank(
            df,
            "INDEX_WITHOUT_BOTH",
        )
    )

    # -----------------------------------------------------
    # Absolute rank changes
    # -----------------------------------------------------
    df["RANK_CHANGE_WITHOUT_URIR"] = (
        df["FULL_RANK"]
        - df["RANK_WITHOUT_URIR"]
    ).abs()

    df["RANK_CHANGE_WITHOUT_REPC"] = (
        df["FULL_RANK"]
        - df["RANK_WITHOUT_REPC"]
    ).abs()

    df["RANK_CHANGE_WITHOUT_BOTH"] = (
        df["FULL_RANK"]
        - df["RANK_WITHOUT_BOTH"]
    ).abs()

    # -----------------------------------------------------
    # Summary results
    # -----------------------------------------------------
    result_without_urir = (
        compare_with_complete_index(
            df,
            "INDEX_WITHOUT_URIR",
            "RANK_WITHOUT_URIR",
        )
    )

    result_without_repc = (
        compare_with_complete_index(
            df,
            "INDEX_WITHOUT_REPC",
            "RANK_WITHOUT_REPC",
        )
    )

    result_without_both = (
        compare_with_complete_index(
            df,
            "INDEX_WITHOUT_BOTH",
            "RANK_WITHOUT_BOTH",
        )
    )

    summary_table = pd.DataFrame(
        [
            {
                "Index specification":
                    "Excluding URIR",
                **result_without_urir,
            },
            {
                "Index specification":
                    "Excluding REPC",
                **result_without_repc,
            },
            {
                "Index specification":
                    "Excluding both",
                **result_without_both,
            },
        ]
    )

    numeric_cols = [
        "Correlation with the complete index",
        "Mean absolute rank change",
        "Maximum rank change",
        "Unchanged ranks (%)",
    ]

    summary_table[numeric_cols] = (
        summary_table[numeric_cols]
        .round(4)
    )

    # -----------------------------------------------------
    # Combine weight tables
    # -----------------------------------------------------
    full_weights["Specification"] = (
        "Complete index"
    )

    weights_without_urir[
        "Specification"
    ] = "Excluding URIR"

    weights_without_repc[
        "Specification"
    ] = "Excluding REPC"

    weights_without_both[
        "Specification"
    ] = "Excluding both"

    weight_results = pd.concat(
        [
            full_weights,
            weights_without_urir,
            weights_without_repc,
            weights_without_both,
        ],
        ignore_index=True,
    )

    weight_results = weight_results[
        [
            "Specification",
            "Indicator",
            "Standard_Deviation",
            "Information_Conflict",
            "Information_Content",
            "Weight",
        ]
    ]

    # -----------------------------------------------------
    # Save results
    # -----------------------------------------------------
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_cols = [
        col
        for col in ID_COLS
        if col in df.columns
    ] + [
        "FULL_INDEX",
        "INDEX_WITHOUT_URIR",
        "INDEX_WITHOUT_REPC",
        "INDEX_WITHOUT_BOTH",
        "FULL_RANK",
        "RANK_WITHOUT_URIR",
        "RANK_WITHOUT_REPC",
        "RANK_WITHOUT_BOTH",
        "RANK_CHANGE_WITHOUT_URIR",
        "RANK_CHANGE_WITHOUT_REPC",
        "RANK_CHANGE_WITHOUT_BOTH",
    ]

    with pd.ExcelWriter(
        OUTPUT_PATH,
        engine="openpyxl",
    ) as writer:

        summary_table.to_excel(
            writer,
            sheet_name="Table_A4",
            index=False,
        )

        df[output_cols].to_excel(
            writer,
            sheet_name="Index_and_Rank",
            index=False,
        )

        weight_results.to_excel(
            writer,
            sheet_name="Weights",
            index=False,
        )

    print("\n计算结果：")
    print(
        summary_table.to_string(
            index=False
        )
    )

    print(
        "\n输出文件："
        f"{OUTPUT_PATH.resolve()}"
    )

    print("\n工作表说明：")
    print(
        "1. Table_A4：最终稳健性检验表"
    )
    print(
        "2. Index_and_Rank："
        "各指数得分和省份年度排名"
    )
    print(
        "3. Weights："
        "删除指标前后重新计算的权重"
    )

    print("=" * 72)


if __name__ == "__main__":
    main()