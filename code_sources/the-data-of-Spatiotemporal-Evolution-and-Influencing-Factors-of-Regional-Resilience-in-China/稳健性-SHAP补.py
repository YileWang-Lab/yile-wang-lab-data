# -*- coding: utf-8 -*-
"""
SHAP robustness analysis for PRI and INC collinearity.

Two figures:
1. Recalculate SHAP after removing PRI
2. Recalculate SHAP after removing INC

Temporal division:
- Training:   2007-2019
- Validation: 2020-2021
- Test:       2022-2024

Outputs:
- SHAP_WITHOUT_PRI.png / pdf
- SHAP_WITHOUT_INC.png / pdf
- SHAP_DROP_ONE_RESULTS.xlsx
"""

import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import cm

from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.metrics import (
    r2_score,
    mean_absolute_error,
    mean_squared_error,
)

from xgboost import XGBRegressor
from catboost import CatBoostRegressor

import shap


# =========================================================
# 0. Plotting style
# =========================================================
plt.rcParams.update({
    "font.family": "Times New Roman",
    "font.weight": "bold",
    "font.size": 16,
    "axes.labelweight": "bold",
    "axes.titleweight": "bold",
    "axes.labelsize": 18,
    "axes.titlesize": 20,
    "xtick.labelsize": 16,
    "ytick.labelsize": 16,
    "legend.fontsize": 16,
    "axes.linewidth": 2.0,
    "axes.edgecolor": "black",
    "axes.unicode_minus": True,
    "xtick.major.width": 2.0,
    "ytick.major.width": 2.0,
    "xtick.major.size": 8,
    "ytick.major.size": 8,
})


# =========================================================
# 1. Settings
# =========================================================
DATA_PATH = r"PANEL_ANALYSIS_DATA - 副本.xlsx"
SHEET_NAME = 0

TARGET_COL = "Spearman-CRITIC"

ALL_FEATURE_COLS = [
    "URB",
    "GOV",
    "INNO",
    "EDU",
    "OPENPC",
    "FIN",
    "DIG",
    "PRI",
    "INC",
    "SOC",
]

ID_COLS = [
    "ADMINCODE",
    "REGION",
    "ZONE",
    "YEAR",
]

TRAIN_YEARS = list(range(2007, 2020))
VALIDATION_YEARS = list(range(2020, 2022))
TEST_YEARS = list(range(2022, 2025))

RANDOM_STATE = 42

FIXED_PARAMS = {
    "alpha": 0.3,
    "cat_depth": 6,
    "cat_iterations": 500,
    "cat_l2_leaf_reg": 5,
    "cat_learning_rate": 0.05,
    "xgb_colsample_bytree": 0.8,
    "xgb_learning_rate": 0.05,
    "xgb_max_depth": 5,
    "xgb_n_estimators": 500,
    "xgb_subsample": 1.0,
}

OUTPUT_DIR = Path(
    "ML_SHAP_DROP_ONE"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT_EXCEL = (
    OUTPUT_DIR
    / "SHAP_DROP_ONE_RESULTS.xlsx"
)


# =========================================================
# 2. Utility functions
# =========================================================
def safe_mape(
    y_true,
    y_pred,
    eps=1e-8,
):
    y_true = np.asarray(
        y_true,
        dtype=float,
    )

    y_pred = np.asarray(
        y_pred,
        dtype=float,
    )

    denominator = np.maximum(
        np.abs(y_true),
        eps,
    )

    return (
        np.mean(
            np.abs(
                (y_true - y_pred)
                / denominator
            )
        )
        * 100
    )


def calculate_metrics(
    y_true,
    y_pred,
):
    return {
        "R2": r2_score(
            y_true,
            y_pred,
        ),
        "MAE": mean_absolute_error(
            y_true,
            y_pred,
        ),
        "RMSE": np.sqrt(
            mean_squared_error(
                y_true,
                y_pred,
            )
        ),
        "MAPE(%)": safe_mape(
            y_true,
            y_pred,
        ),
    }


def save_png_pdf(
    output_path_no_suffix,
):
    plt.tight_layout()

    plt.savefig(
        output_path_no_suffix.with_suffix(
            ".png"
        ),
        dpi=300,
        bbox_inches="tight",
        format="png",
    )

    plt.savefig(
        output_path_no_suffix.with_suffix(
            ".pdf"
        ),
        dpi=300,
        bbox_inches="tight",
        format="pdf",
    )

    plt.close()


def read_excel_auto(
    path,
    sheet_name=0,
    required_cols=None,
):
    path_obj = Path(path)

    if not path_obj.exists():
        raise FileNotFoundError(
            f"File not found: "
            f"{path_obj.resolve()}"
        )

    if path_obj.suffix.lower() == ".csv":
        df = pd.read_csv(
            path_obj,
            encoding="utf-8-sig",
        )

        return df

    xls = pd.ExcelFile(path_obj)

    try:
        df = pd.read_excel(
            path_obj,
            sheet_name=sheet_name,
        )

        if (
            required_cols is None
            or all(
                col in df.columns
                for col in required_cols
            )
        ):
            print(
                f"[INFO] Using sheet: "
                f"{sheet_name}"
            )

            return df

    except Exception:
        pass

    for sheet in xls.sheet_names:
        preview = pd.read_excel(
            path_obj,
            sheet_name=sheet,
            nrows=5,
        )

        if (
            required_cols is None
            or all(
                col in preview.columns
                for col in required_cols
            )
        ):
            print(
                f"[INFO] Auto-detected sheet: "
                f"{sheet}"
            )

            return pd.read_excel(
                path_obj,
                sheet_name=sheet,
            )

    raise ValueError(
        "No sheet containing all required "
        f"columns was found: {required_cols}"
    )


def normalize_shap_values(
    values,
):
    if isinstance(values, list):
        values = values[0]

    return np.asarray(
        values,
        dtype=float,
    )


# =========================================================
# 3. CatBoost-XGBoost hybrid model
# =========================================================
class CatBoostXGBoostHybridRegressor(
    BaseEstimator,
    RegressorMixin,
):
    """
    prediction =
        alpha * CatBoost prediction
        + (1-alpha) * XGBoost prediction
    """

    def __init__(
        self,
        alpha=0.3,
        cat_depth=6,
        cat_iterations=500,
        cat_l2_leaf_reg=5,
        cat_learning_rate=0.05,
        xgb_colsample_bytree=0.8,
        xgb_learning_rate=0.05,
        xgb_max_depth=5,
        xgb_n_estimators=500,
        xgb_subsample=1.0,
        random_state=42,
    ):
        self.alpha = alpha
        self.cat_depth = cat_depth
        self.cat_iterations = cat_iterations
        self.cat_l2_leaf_reg = (
            cat_l2_leaf_reg
        )
        self.cat_learning_rate = (
            cat_learning_rate
        )
        self.xgb_colsample_bytree = (
            xgb_colsample_bytree
        )
        self.xgb_learning_rate = (
            xgb_learning_rate
        )
        self.xgb_max_depth = xgb_max_depth
        self.xgb_n_estimators = (
            xgb_n_estimators
        )
        self.xgb_subsample = xgb_subsample
        self.random_state = random_state

    def fit(self, X, y):
        X = np.asarray(
            X,
            dtype=float,
        )

        y = np.asarray(
            y,
            dtype=float,
        )

        self.cat_model_ = CatBoostRegressor(
            iterations=self.cat_iterations,
            learning_rate=(
                self.cat_learning_rate
            ),
            depth=self.cat_depth,
            l2_leaf_reg=(
                self.cat_l2_leaf_reg
            ),
            loss_function="RMSE",
            random_seed=self.random_state,
            verbose=0,
            allow_writing_files=False,
            thread_count=-1,
        )

        self.xgb_model_ = XGBRegressor(
            objective="reg:squarederror",
            n_estimators=(
                self.xgb_n_estimators
            ),
            learning_rate=(
                self.xgb_learning_rate
            ),
            max_depth=self.xgb_max_depth,
            subsample=self.xgb_subsample,
            colsample_bytree=(
                self.xgb_colsample_bytree
            ),
            random_state=self.random_state,
            n_jobs=-1,
            verbosity=0,
        )

        self.cat_model_.fit(X, y)
        self.xgb_model_.fit(X, y)

        return self

    def predict(self, X):
        X = np.asarray(
            X,
            dtype=float,
        )

        cat_prediction = (
            self.cat_model_.predict(X)
        )

        xgb_prediction = (
            self.xgb_model_.predict(X)
        )

        return (
            self.alpha * cat_prediction
            + (1.0 - self.alpha)
            * xgb_prediction
        )


def build_model():
    return CatBoostXGBoostHybridRegressor(
        alpha=FIXED_PARAMS["alpha"],
        cat_depth=(
            FIXED_PARAMS["cat_depth"]
        ),
        cat_iterations=(
            FIXED_PARAMS["cat_iterations"]
        ),
        cat_l2_leaf_reg=(
            FIXED_PARAMS["cat_l2_leaf_reg"]
        ),
        cat_learning_rate=(
            FIXED_PARAMS["cat_learning_rate"]
        ),
        xgb_colsample_bytree=(
            FIXED_PARAMS[
                "xgb_colsample_bytree"
            ]
        ),
        xgb_learning_rate=(
            FIXED_PARAMS[
                "xgb_learning_rate"
            ]
        ),
        xgb_max_depth=(
            FIXED_PARAMS["xgb_max_depth"]
        ),
        xgb_n_estimators=(
            FIXED_PARAMS[
                "xgb_n_estimators"
            ]
        ),
        xgb_subsample=(
            FIXED_PARAMS["xgb_subsample"]
        ),
        random_state=RANDOM_STATE,
    )


# =========================================================
# 4. SHAP beeswarm + bar figure
# =========================================================
def plot_shap_beeswarm_bar(
    shap_values,
    X_df,
    shap_df,
    output_path,
    title,
):
    plt.figure(
        figsize=(16, 10),
        dpi=300,
    )

    shap.summary_plot(
        shap_values,
        X_df,
        plot_type="dot",
        cmap=plt.get_cmap("plasma"),
        show=False,
    )

    ax1 = plt.gca()

    ax1.set_position([
        0.30,
        0.10,
        0.62,
        0.85,
    ])

    for collection in ax1.collections:
        try:
            collection.set_sizes([42])
        except Exception:
            pass

    ax2 = ax1.twiny()

    feature_order = [
        tick.get_text()
        for tick in ax1.get_yticklabels()
    ]

    ordered_importance = [
        np.abs(
            shap_df[feature]
        ).mean()
        for feature in feature_order
    ]

    color_map = cm.get_cmap(
        "plasma",
        len(feature_order),
    )

    colors = color_map(
        np.linspace(
            0.15,
            0.90,
            len(feature_order),
        )
    )

    ax2.barh(
        range(len(feature_order)),
        ordered_importance,
        height=0.68,
        color=colors,
        alpha=0.35,
        edgecolor="black",
        linewidth=1.8,
    )

    ax1.set_xlabel(
        "SHAP Value",
        fontweight="bold",
        fontsize=16,
    )

    ax2.set_xlabel(
        "Mean |SHAP Value|",
        fontweight="bold",
        fontsize=16,
    )

    ax2.xaxis.set_label_position("top")
    ax2.xaxis.tick_top()

    ax1.set_ylabel(
        "Features",
        fontweight="bold",
        fontsize=16,
    )

    ax1.set_title(
        title,
        fontweight="bold",
        fontsize=18,
        pad=12,
    )

    ax1.grid(
        True,
        axis="x",
        linestyle="--",
        alpha=0.3,
        linewidth=1.4,
    )

    ax2.grid(
        True,
        axis="x",
        linestyle="--",
        alpha=0.3,
        linewidth=1.4,
    )

    ax1.axvline(
        x=0,
        color="black",
        linewidth=2.0,
        alpha=0.75,
    )

    for axis in [ax1, ax2]:
        for spine in axis.spines.values():
            spine.set_linewidth(2.0)
            spine.set_color("black")

    for tick in (
        ax1.get_xticklabels()
        + ax1.get_yticklabels()
        + ax2.get_xticklabels()
    ):
        tick.set_color("black")
        tick.set_fontweight("bold")

    save_png_pdf(output_path)


# =========================================================
# 5. Run one reduced-feature model
# =========================================================
def run_model(
    scenario_name,
    feature_cols,
    train_df,
    validation_df,
    test_df,
    output_name,
    figure_title,
):
    print(
        f"\nRunning: {scenario_name}"
    )

    model = build_model()

    X_train = train_df[
        feature_cols
    ].copy()

    y_train = train_df[
        TARGET_COL
    ].copy()

    X_validation = validation_df[
        feature_cols
    ].copy()

    y_validation = validation_df[
        TARGET_COL
    ].copy()

    X_test = test_df[
        feature_cols
    ].copy()

    y_test = test_df[
        TARGET_COL
    ].copy()

    model.fit(
        X_train,
        y_train,
    )

    metrics_records = []

    for dataset_name, X_current, y_current in [
        (
            "Train",
            X_train,
            y_train,
        ),
        (
            "Validation",
            X_validation,
            y_validation,
        ),
        (
            "Test",
            X_test,
            y_test,
        ),
    ]:
        prediction = model.predict(
            X_current
        )

        metrics = calculate_metrics(
            y_current,
            prediction,
        )

        metrics_records.append({
            "Scenario": scenario_name,
            "Dataset": dataset_name,
            **metrics,
        })

    # -----------------------------------------------------
    # SHAP is calculated on the test set only
    # -----------------------------------------------------
    cat_explainer = shap.TreeExplainer(
        model.cat_model_
    )

    xgb_explainer = shap.TreeExplainer(
        model.xgb_model_
    )

    cat_shap_values = normalize_shap_values(
        cat_explainer.shap_values(
            X_test.to_numpy(dtype=float)
        )
    )

    xgb_shap_values = normalize_shap_values(
        xgb_explainer.shap_values(
            X_test.to_numpy(dtype=float)
        )
    )

    shap_values = (
        FIXED_PARAMS["alpha"]
        * cat_shap_values
        + (
            1.0
            - FIXED_PARAMS["alpha"]
        )
        * xgb_shap_values
    )

    shap_df = pd.DataFrame(
        shap_values,
        columns=feature_cols,
        index=X_test.index,
    )

    importance_df = pd.DataFrame({
        "Scenario": scenario_name,
        "Feature": feature_cols,
        "MeanAbsSHAP": np.abs(
            shap_values
        ).mean(axis=0),
    })

    importance_df = (
        importance_df
        .sort_values(
            "MeanAbsSHAP",
            ascending=False,
        )
        .reset_index(drop=True)
    )

    importance_df["Rank"] = (
        np.arange(
            len(importance_df)
        )
        + 1
    )

    plot_shap_beeswarm_bar(
        shap_values=shap_values,
        X_df=X_test,
        shap_df=shap_df,
        output_path=(
            OUTPUT_DIR / output_name
        ),
        title=figure_title,
    )

    shap_export = shap_df.copy()

    if "REGION" in test_df.columns:
        shap_export.insert(
            0,
            "REGION",
            test_df.loc[
                shap_export.index,
                "REGION",
            ],
        )

    shap_export.insert(
        0,
        "YEAR",
        test_df.loc[
            shap_export.index,
            "YEAR",
        ],
    )

    return {
        "metrics": pd.DataFrame(
            metrics_records
        ),
        "importance": importance_df,
        "shap_values": shap_export,
    }


# =========================================================
# 6. Read and clean data
# =========================================================
required_cols = (
    ALL_FEATURE_COLS
    + [TARGET_COL, "YEAR"]
)

df = read_excel_auto(
    DATA_PATH,
    sheet_name=SHEET_NAME,
    required_cols=required_cols,
)

keep_cols = list(
    dict.fromkeys(
        [
            col
            for col in ID_COLS
            if col in df.columns
        ]
        + ALL_FEATURE_COLS
        + [TARGET_COL]
    )
)

df = df[keep_cols].copy()

for column in (
    ALL_FEATURE_COLS
    + [TARGET_COL, "YEAR"]
):
    df[column] = pd.to_numeric(
        df[column],
        errors="coerce",
    )

df = df.dropna(
    subset=(
        ALL_FEATURE_COLS
        + [TARGET_COL, "YEAR"]
    )
).copy()

df["YEAR"] = df["YEAR"].astype(int)

sort_cols = [
    column
    for column in ["YEAR", "REGION"]
    if column in df.columns
]

df = (
    df.sort_values(sort_cols)
    .reset_index(drop=True)
)


# =========================================================
# 7. Chronological split
# =========================================================
train_df = df[
    df["YEAR"].isin(TRAIN_YEARS)
].copy()

validation_df = df[
    df["YEAR"].isin(
        VALIDATION_YEARS
    )
].copy()

test_df = df[
    df["YEAR"].isin(TEST_YEARS)
].copy()

if train_df.empty:
    raise ValueError(
        "Training set is empty."
    )

if validation_df.empty:
    raise ValueError(
        "Validation set is empty."
    )

if test_df.empty:
    raise ValueError(
        "Test set is empty."
    )


# =========================================================
# 8. Model 1: remove PRI
# =========================================================
features_without_pri = [
    feature
    for feature in ALL_FEATURE_COLS
    if feature != "PRI"
]

without_pri_result = run_model(
    scenario_name="Without PRI",
    feature_cols=features_without_pri,
    train_df=train_df,
    validation_df=validation_df,
    test_df=test_df,
    output_name="SHAP_WITHOUT_PRI",
    figure_title="SHAP Summary without PRI",
)


# =========================================================
# 9. Model 2: remove INC
# =========================================================
features_without_inc = [
    feature
    for feature in ALL_FEATURE_COLS
    if feature != "INC"
]

without_inc_result = run_model(
    scenario_name="Without INC",
    feature_cols=features_without_inc,
    train_df=train_df,
    validation_df=validation_df,
    test_df=test_df,
    output_name="SHAP_WITHOUT_INC",
    figure_title="SHAP Summary without INC",
)


# =========================================================
# 10. Export results
# =========================================================
metrics_df = pd.concat(
    [
        without_pri_result["metrics"],
        without_inc_result["metrics"],
    ],
    ignore_index=True,
)

with pd.ExcelWriter(
    OUTPUT_EXCEL,
    engine="openpyxl",
) as writer:
    metrics_df.to_excel(
        writer,
        sheet_name="Model_Metrics",
        index=False,
    )

    without_pri_result[
        "importance"
    ].to_excel(
        writer,
        sheet_name="Importance_No_PRI",
        index=False,
    )

    without_inc_result[
        "importance"
    ].to_excel(
        writer,
        sheet_name="Importance_No_INC",
        index=False,
    )

    without_pri_result[
        "shap_values"
    ].to_excel(
        writer,
        sheet_name="SHAP_No_PRI",
        index=False,
    )

    without_inc_result[
        "shap_values"
    ].to_excel(
        writer,
        sheet_name="SHAP_No_INC",
        index=False,
    )


# =========================================================
# 11. Print information
# =========================================================
print("=" * 75)
print("Two reduced-feature SHAP models completed.")
print("=" * 75)

print(
    f"Training observations: "
    f"{len(train_df)}"
)

print(
    f"Validation observations: "
    f"{len(validation_df)}"
)

print(
    f"Test observations: "
    f"{len(test_df)}"
)

print("\nGenerated figures:")
print("1. SHAP_WITHOUT_PRI.png / pdf")
print("2. SHAP_WITHOUT_INC.png / pdf")

print(
    f"\nExcel output: "
    f"{OUTPUT_EXCEL.resolve()}"
)

print("\nModel metrics:")
print(
    metrics_df.to_string(
        index=False
    )
)

print("=" * 75)