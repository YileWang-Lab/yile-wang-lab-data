# -*- coding: utf-8 -*-
"""
Spatial weight matrix sensitivity analysis for Getis-Ord Gi*.

Spatial weights:
1. Fixed Distance Band: baseline, reproducing the ArcGIS default principle
2. Queen Contiguity
3. K-Nearest Neighbors, k=4

Outputs:
- spatial_weight_sensitivity_output/
  SPATIAL_WEIGHT_SENSITIVITY.xlsx
"""

import warnings
from pathlib import Path
from urllib.request import urlretrieve

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import geopandas as gpd

from scipy.spatial.distance import cdist
from scipy.stats import norm

from libpysal.weights import (
    DistanceBand,
    Queen,
    KNN,
    attach_islands,
)
from esda.getisord import G_Local


# =========================================================
# 0. Settings
# =========================================================
DATA_PATH = r"粘贴的文本 (1)(94).txt"

REGION_COL = "REGION"
YEAR_COL = "YEAR"
VALUE_COL = "RESILIENCE"

START_YEAR = 2007
END_YEAR = 2024

# Alternative nearest-neighbor matrix
K_NEIGHBORS = 4

# Fixed random seed
RANDOM_STATE = 42

OUTPUT_DIR = Path(
    "spatial_weight_sensitivity_output"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "SPATIAL_WEIGHT_SENSITIVITY.xlsx"
)

# GADM China provincial boundary
BOUNDARY_URL = (
    "https://geodata.ucdavis.edu/"
    "gadm/gadm4.1/json/"
    "gadm41_CHN_1.json"
)

BOUNDARY_FILE = (
    OUTPUT_DIR
    / "gadm41_CHN_1.json"
)

# China Albers Equal Area projection
CHINA_ALBERS = (
    "+proj=aea "
    "+lat_1=25 "
    "+lat_2=47 "
    "+lat_0=0 "
    "+lon_0=105 "
    "+datum=WGS84 "
    "+units=m "
    "+no_defs"
)


# =========================================================
# 1. English-Chinese province name mapping
# =========================================================
PROVINCE_NAME_MAP = {
    "Anhui": "安徽",
    "Beijing": "北京",
    "Chongqing": "重庆",
    "Fujian": "福建",
    "Gansu": "甘肃",
    "Guangdong": "广东",
    "Guangxi": "广西",
    "Guizhou": "贵州",
    "Hainan": "海南",
    "Hebei": "河北",
    "Heilongjiang": "黑龙江",
    "Henan": "河南",
    "Hubei": "湖北",
    "Hunan": "湖南",
    "Jiangsu": "江苏",
    "Jiangxi": "江西",
    "Jilin": "吉林",
    "Liaoning": "辽宁",
    "Nei Mongol": "内蒙古",
    "Ningxia Hui": "宁夏",
    "Qinghai": "青海",
    "Shaanxi": "陕西",
    "Shandong": "山东",
    "Shanghai": "上海",
    "Shanxi": "山西",
    "Sichuan": "四川",
    "Tianjin": "天津",
    "Xinjiang Uygur": "新疆",
    "Xizang": "西藏",
    "Yunnan": "云南",
    "Zhejiang": "浙江",
}


# =========================================================
# 2. Data utilities
# =========================================================
def clean_region_name(name):
    name = str(name).strip()

    suffixes = [
        "壮族自治区",
        "回族自治区",
        "维吾尔自治区",
        "自治区",
        "特别行政区",
        "省",
        "市",
    ]

    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[
                : -len(suffix)
            ]

    replacements = {
        "西藏自治": "西藏",
        "内蒙古自治": "内蒙古",
        "广西壮族": "广西",
        "宁夏回族": "宁夏",
        "新疆维吾尔": "新疆",
    }

    return replacements.get(
        name,
        name,
    )


def read_panel_data(path):
    path_obj = Path(path)

    if not path_obj.exists():
        raise FileNotFoundError(
            f"Data file not found: "
            f"{path_obj.resolve()}"
        )

    suffix = path_obj.suffix.lower()

    if suffix in [".xlsx", ".xls"]:
        df = pd.read_excel(path_obj)

    elif suffix == ".csv":
        df = pd.read_csv(
            path_obj,
            encoding="utf-8-sig",
        )

    elif suffix in [".txt", ".tsv"]:
        df = pd.read_csv(
            path_obj,
            sep=None,
            engine="python",
            encoding="utf-8-sig",
        )

    else:
        raise ValueError(
            "Only Excel, CSV, TXT, "
            "and TSV files are supported."
        )

    df.columns = [
        str(column).strip()
        for column in df.columns
    ]

    required_cols = [
        REGION_COL,
        YEAR_COL,
        VALUE_COL,
    ]

    missing_cols = [
        column
        for column in required_cols
        if column not in df.columns
    ]

    if missing_cols:
        raise ValueError(
            f"Missing columns: "
            f"{missing_cols}"
        )

    df = df[
        required_cols
    ].copy()

    df[REGION_COL] = (
        df[REGION_COL]
        .apply(clean_region_name)
    )

    df[YEAR_COL] = pd.to_numeric(
        df[YEAR_COL],
        errors="coerce",
    )

    df[VALUE_COL] = pd.to_numeric(
        df[VALUE_COL],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            REGION_COL,
            YEAR_COL,
            VALUE_COL,
        ]
    ).copy()

    df[YEAR_COL] = (
        df[YEAR_COL].astype(int)
    )

    df = df[
        df[YEAR_COL].between(
            START_YEAR,
            END_YEAR,
        )
    ].copy()

    duplicate_count = (
        df.duplicated(
            subset=[
                REGION_COL,
                YEAR_COL,
            ]
        ).sum()
    )

    if duplicate_count > 0:
        raise ValueError(
            "Duplicate province-year "
            f"observations found: "
            f"{duplicate_count}"
        )

    return (
        df.sort_values(
            [YEAR_COL, REGION_COL]
        )
        .reset_index(drop=True)
    )


# =========================================================
# 3. Download and process boundaries
# =========================================================
def load_province_boundaries():
    if not BOUNDARY_FILE.exists():
        print(
            "Downloading China provincial "
            "boundary data ..."
        )

        try:
            urlretrieve(
                BOUNDARY_URL,
                BOUNDARY_FILE,
            )

        except Exception as error:
            raise RuntimeError(
                "Boundary download failed. "
                "Please check the internet "
                "connection and run again."
            ) from error

    gdf = gpd.read_file(
        BOUNDARY_FILE
    )

    if "NAME_1" not in gdf.columns:
        raise ValueError(
            "NAME_1 was not found in "
            "the boundary data."
        )

    # 补充GADM边界数据中的特殊名称
    province_name_map = PROVINCE_NAME_MAP.copy()

    province_name_map.update({
        "NeiMongol": "内蒙古",
        "NingxiaHui": "宁夏",
        "XinjiangUygur": "新疆",
    })

    # 本文仅研究中国大陆31个省级地区，排除港澳
    gdf = gdf.loc[
        ~gdf["NAME_1"].isin(
            ["HongKong", "Macau"]
        )
    ].copy()

    # 将英文名称转换为中文省名
    gdf["REGION"] = (
        gdf["NAME_1"]
        .map(province_name_map)
    )

    # 检查剩余未匹配名称
    unmatched = sorted(
        gdf.loc[
            gdf["REGION"].isna(),
            "NAME_1"
        ]
        .dropna()
        .unique()
        .tolist()
    )

    if unmatched:
        raise ValueError(
            "Unmatched boundary names: "
            f"{unmatched}"
        )

    gdf = gdf[
        ["REGION", "geometry"]
    ].copy()

    # 新疆在边界文件中可能包含多个几何对象，
    # 按省名合并为一个完整的省级空间单元
    gdf = gdf.dissolve(
        by="REGION",
        as_index=False
    )

    gdf = (
        gdf.sort_values("REGION")
        .reset_index(drop=True)
    )

    if len(gdf) != 31:
        region_list = sorted(
            gdf["REGION"]
            .dropna()
            .unique()
            .tolist()
        )

        raise ValueError(
            "The boundary file should "
            f"contain 31 regions, but "
            f"{len(gdf)} were found.\n"
            f"Matched regions: {region_list}"
        )

    print(
        "Successfully matched "
        f"{len(gdf)} provincial regions."
    )

    return gdf

# =========================================================
# 4. Validate province matching
# =========================================================
def validate_regions(
    panel_df,
    boundary_gdf,
):
    panel_regions = set(
        panel_df[REGION_COL].unique()
    )

    boundary_regions = set(
        boundary_gdf["REGION"].unique()
    )

    missing_in_boundary = sorted(
        panel_regions
        - boundary_regions
    )

    missing_in_data = sorted(
        boundary_regions
        - panel_regions
    )

    if missing_in_boundary:
        raise ValueError(
            "Regions missing from boundary "
            f"data: {missing_in_boundary}"
        )

    if missing_in_data:
        raise ValueError(
            "Regions missing from panel "
            f"data: {missing_in_data}"
        )

    expected_years = set(
        range(
            START_YEAR,
            END_YEAR + 1,
        )
    )

    for region, group in panel_df.groupby(
        REGION_COL
    ):
        years = set(group[YEAR_COL])

        if years != expected_years:
            missing_years = sorted(
                expected_years - years
            )

            raise ValueError(
                f"{region} is missing years: "
                f"{missing_years}"
            )


# =========================================================
# 5. Construct spatial weight matrices
# =========================================================
def build_spatial_weights(
    boundary_gdf,
):
    projected_gdf = (
        boundary_gdf
        .to_crs(CHINA_ALBERS)
        .copy()
    )

    # Polygon centroids in projected coordinates
    centroids = (
        projected_gdf.geometry
        .centroid
    )

    coordinates = np.column_stack([
        centroids.x.to_numpy(),
        centroids.y.to_numpy(),
    ])

    region_order = (
        projected_gdf["REGION"]
        .tolist()
    )

    # -----------------------------------------------------
    # Baseline: ArcGIS default Fixed Distance Band
    #
    # Automatically choose the minimum threshold
    # that ensures every province has at least
    # one neighbor.
    # -----------------------------------------------------
    distance_matrix = cdist(
        coordinates,
        coordinates,
        metric="euclidean",
    )

    np.fill_diagonal(
        distance_matrix,
        np.inf,
    )

    nearest_distance = (
        distance_matrix.min(axis=1)
    )

    threshold_distance = (
        nearest_distance.max()
        * 1.000001
    )

    fixed_distance_w = DistanceBand(
        coordinates,
        threshold=threshold_distance,
        binary=True,
        ids=region_order,
        silence_warnings=True,
    )

    # -----------------------------------------------------
    # Alternative 1: Queen contiguity
    # -----------------------------------------------------
    queen_w = Queen.from_dataframe(
        projected_gdf,
        ids=region_order,
        use_index=False,
        silence_warnings=True,
    )

    # Attach islands, such as Hainan,
    # to their nearest spatial neighbor
    if queen_w.islands:
        knn1_w = KNN(
            coordinates,
            k=1,
            ids=region_order,
            silence_warnings=True,
        )

        queen_w = attach_islands(
            queen_w,
            knn1_w,
        )

    # -----------------------------------------------------
    # Alternative 2: K-nearest neighbors
    # -----------------------------------------------------
    knn4_w = KNN(
        coordinates,
        k=K_NEIGHBORS,
        ids=region_order,
        silence_warnings=True,
    )

    spatial_weights = {
        "Fixed Distance Band":
            fixed_distance_w,
        "Queen Contiguity":
            queen_w,
        f"{K_NEIGHBORS}-Nearest Neighbors":
            knn4_w,
    }

    weight_information = []

    for method, weights in (
        spatial_weights.items()
    ):
        neighbor_counts = np.array([
            len(weights.neighbors[
                region
            ])
            for region in region_order
        ])

        weight_information.append({
            "Spatial weight matrix":
                method,
            "Number of regions":
                weights.n,
            "Minimum neighbors":
                neighbor_counts.min(),
            "Mean neighbors":
                neighbor_counts.mean(),
            "Maximum neighbors":
                neighbor_counts.max(),
            "Isolated regions":
                len(weights.islands),
            "Threshold distance (km)":
                (
                    threshold_distance
                    / 1000
                    if method
                    == "Fixed Distance Band"
                    else np.nan
                ),
        })

    weight_info_df = pd.DataFrame(
        weight_information
    )

    return (
        spatial_weights,
        region_order,
        threshold_distance,
        weight_info_df,
    )


# =========================================================
# 6. Getis-Ord Gi* classification
# =========================================================
def classify_gi_bin(z_score):
    """
    ArcGIS-style Gi_Bin classification:

     3 = hot spot, 99%
     2 = hot spot, 95%
     1 = hot spot, 90%
     0 = not significant
    -1 = cold spot, 90%
    -2 = cold spot, 95%
    -3 = cold spot, 99%
    """

    if z_score >= 2.576:
        return 3

    if z_score >= 1.960:
        return 2

    if z_score >= 1.645:
        return 1

    if z_score <= -2.576:
        return -3

    if z_score <= -1.960:
        return -2

    if z_score <= -1.645:
        return -1

    return 0


def classify_three_groups(z_score):
    """
    Three-category classification at 95%:
    Hot Spot / Cold Spot / Not Significant
    """

    if z_score >= 1.960:
        return "Hot Spot"

    if z_score <= -1.960:
        return "Cold Spot"

    return "Not Significant"


# =========================================================
# 7. Calculate yearly Getis-Ord Gi*
# =========================================================
def calculate_gi_star(
    panel_df,
    spatial_weights,
    region_order,
):
    result_records = []

    for year in range(
        START_YEAR,
        END_YEAR + 1,
    ):
        year_df = (
            panel_df[
                panel_df[YEAR_COL]
                == year
            ]
            .set_index(REGION_COL)
            .loc[region_order]
        )

        values = year_df[
            VALUE_COL
        ].to_numpy(dtype=float)

        for method, weights in (
            spatial_weights.items()
        ):
            local_g = G_Local(
                values,
                weights,
                transform="B",
                permutations=0,
                star=True,
            )

            z_scores = np.asarray(
                local_g.Zs,
                dtype=float,
            )

            p_values = (
                2
                * norm.sf(
                    np.abs(z_scores)
                )
            )

            for index, region in enumerate(
                region_order
            ):
                result_records.append({
                    "YEAR": year,
                    "REGION": region,
                    "RESILIENCE":
                        values[index],
                    "WEIGHT_METHOD":
                        method,
                    "GI_STAR_Z":
                        z_scores[index],
                    "P_VALUE":
                        p_values[index],
                    "GI_BIN":
                        classify_gi_bin(
                            z_scores[index]
                        ),
                    "CLASS_95":
                        classify_three_groups(
                            z_scores[index]
                        ),
                })

    return pd.DataFrame(
        result_records
    )


# =========================================================
# 8. Sensitivity comparison
# =========================================================
def calculate_jaccard(
    baseline_labels,
    alternative_labels,
    target_label,
):
    baseline_set = set(
        baseline_labels[
            baseline_labels
            == target_label
        ].index
    )

    alternative_set = set(
        alternative_labels[
            alternative_labels
            == target_label
        ].index
    )

    union = (
        baseline_set
        | alternative_set
    )

    if len(union) == 0:
        return 100.0

    intersection = (
        baseline_set
        & alternative_set
    )

    return (
        len(intersection)
        / len(union)
        * 100
    )


def compare_weight_matrices(
    gi_results,
):
    baseline_method = (
        "Fixed Distance Band"
    )

    alternative_methods = [
        method
        for method in (
            gi_results[
                "WEIGHT_METHOD"
            ].unique()
        )
        if method != baseline_method
    ]

    comparison_records = []

    for year in range(
        START_YEAR,
        END_YEAR + 1,
    ):
        baseline = (
            gi_results[
                (
                    gi_results["YEAR"]
                    == year
                )
                & (
                    gi_results[
                        "WEIGHT_METHOD"
                    ]
                    == baseline_method
                )
            ]
            .set_index("REGION")
            .sort_index()
        )

        for method in alternative_methods:
            alternative = (
                gi_results[
                    (
                        gi_results["YEAR"]
                        == year
                    )
                    & (
                        gi_results[
                            "WEIGHT_METHOD"
                        ]
                        == method
                    )
                ]
                .set_index("REGION")
                .sort_index()
            )

            z_correlation = (
                baseline["GI_STAR_Z"]
                .corr(
                    alternative[
                        "GI_STAR_Z"
                    ],
                    method="spearman",
                )
            )

            exact_bin_agreement = (
                (
                    baseline["GI_BIN"]
                    == alternative["GI_BIN"]
                )
                .mean()
                * 100
            )

            class_95_agreement = (
                (
                    baseline["CLASS_95"]
                    == alternative[
                        "CLASS_95"
                    ]
                )
                .mean()
                * 100
            )

            hot_spot_overlap = (
                calculate_jaccard(
                    baseline["CLASS_95"],
                    alternative["CLASS_95"],
                    "Hot Spot",
                )
            )

            cold_spot_overlap = (
                calculate_jaccard(
                    baseline["CLASS_95"],
                    alternative["CLASS_95"],
                    "Cold Spot",
                )
            )

            comparison_records.append({
                "YEAR": year,
                "BASELINE_MATRIX":
                    baseline_method,
                "ALTERNATIVE_MATRIX":
                    method,
                "SPEARMAN_Z_CORRELATION":
                    z_correlation,
                "EXACT_GI_BIN_AGREEMENT(%)":
                    exact_bin_agreement,
                "CLASS_95_AGREEMENT(%)":
                    class_95_agreement,
                "HOT_SPOT_OVERLAP(%)":
                    hot_spot_overlap,
                "COLD_SPOT_OVERLAP(%)":
                    cold_spot_overlap,
            })

    yearly_comparison = pd.DataFrame(
        comparison_records
    )

    summary_records = []

    for method, group in (
        yearly_comparison.groupby(
            "ALTERNATIVE_MATRIX"
        )
    ):
        mean_correlation = group[
            "SPEARMAN_Z_CORRELATION"
        ].mean()

        mean_agreement = group[
            "CLASS_95_AGREEMENT(%)"
        ].mean()

        if (
            mean_correlation >= 0.90
            and mean_agreement >= 80
        ):
            conclusion = "Highly robust"

        elif (
            mean_correlation >= 0.70
            and mean_agreement >= 70
        ):
            conclusion = "Generally robust"

        else:
            conclusion = (
                "Sensitive to weight matrix"
            )

        summary_records.append({
            "Alternative spatial weight matrix":
                method,
            "Mean Spearman correlation of Gi* z-scores":
                mean_correlation,
            "Minimum yearly correlation":
                group[
                    "SPEARMAN_Z_CORRELATION"
                ].min(),
            "Mean 95% classification agreement (%)":
                mean_agreement,
            "Minimum yearly classification agreement (%)":
                group[
                    "CLASS_95_AGREEMENT(%)"
                ].min(),
            "Mean hot-spot overlap (%)":
                group[
                    "HOT_SPOT_OVERLAP(%)"
                ].mean(),
            "Mean cold-spot overlap (%)":
                group[
                    "COLD_SPOT_OVERLAP(%)"
                ].mean(),
            "Conclusion":
                conclusion,
        })

    summary_table = pd.DataFrame(
        summary_records
    )

    return (
        yearly_comparison,
        summary_table,
    )


# =========================================================
# 9. Main
# =========================================================
def main():
    print("=" * 75)
    print(
        "Spatial weight matrix "
        "sensitivity analysis"
    )
    print("=" * 75)

    panel_df = read_panel_data(
        DATA_PATH
    )

    boundary_gdf = (
        load_province_boundaries()
    )

    validate_regions(
        panel_df,
        boundary_gdf,
    )

    (
        spatial_weights,
        region_order,
        threshold_distance,
        weight_info_df,
    ) = build_spatial_weights(
        boundary_gdf
    )

    print(
        "Default fixed-distance "
        f"threshold: "
        f"{threshold_distance / 1000:.2f} km"
    )

    gi_results = calculate_gi_star(
        panel_df,
        spatial_weights,
        region_order,
    )

    (
        yearly_comparison,
        summary_table,
    ) = compare_weight_matrices(
        gi_results
    )

    # Round values for output
    weight_info_output = (
        weight_info_df.copy()
    )

    yearly_output = (
        yearly_comparison.copy()
    )

    summary_output = (
        summary_table.copy()
    )

    gi_output = gi_results.copy()

    numeric_cols = (
        weight_info_output
        .select_dtypes(
            include=[np.number]
        )
        .columns
    )

    weight_info_output[
        numeric_cols
    ] = weight_info_output[
        numeric_cols
    ].round(4)

    numeric_cols = (
        yearly_output
        .select_dtypes(
            include=[np.number]
        )
        .columns
    )

    yearly_output[
        numeric_cols
    ] = yearly_output[
        numeric_cols
    ].round(4)

    numeric_cols = (
        summary_output
        .select_dtypes(
            include=[np.number]
        )
        .columns
    )

    summary_output[
        numeric_cols
    ] = summary_output[
        numeric_cols
    ].round(4)

    numeric_cols = (
        gi_output
        .select_dtypes(
            include=[np.number]
        )
        .columns
    )

    gi_output[
        numeric_cols
    ] = gi_output[
        numeric_cols
    ].round(6)

    # ---------------------------------------------
    # Save Excel
    # ---------------------------------------------
    with pd.ExcelWriter(
        OUTPUT_FILE,
        engine="openpyxl",
    ) as writer:
        summary_output.to_excel(
            writer,
            sheet_name="Table_Sensitivity",
            index=False,
        )

        yearly_output.to_excel(
            writer,
            sheet_name="Yearly_Comparison",
            index=False,
        )

        weight_info_output.to_excel(
            writer,
            sheet_name="Weight_Matrix_Info",
            index=False,
        )

        gi_output.to_excel(
            writer,
            sheet_name="GiStar_All_Results",
            index=False,
        )

        panel_df.to_excel(
            writer,
            sheet_name="Input_Data",
            index=False,
        )

        # Basic formatting
        workbook = writer.book

        for worksheet in workbook.worksheets:
            worksheet.freeze_panes = "A2"

            for column_cells in (
                worksheet.columns
            ):
                max_length = 0

                column_letter = (
                    column_cells[0]
                    .column_letter
                )

                for cell in column_cells:
                    value = (
                        ""
                        if cell.value is None
                        else str(cell.value)
                    )

                    max_length = max(
                        max_length,
                        len(value),
                    )

                worksheet.column_dimensions[
                    column_letter
                ].width = min(
                    max_length + 2,
                    45,
                )

    print("\nPaper-ready sensitivity table:")
    print(
        summary_output.to_string(
            index=False
        )
    )

    print(
        f"\nOutput file: "
        f"{OUTPUT_FILE.resolve()}"
    )

    print("=" * 75)


if __name__ == "__main__":
    main()