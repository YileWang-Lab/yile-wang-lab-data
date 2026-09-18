# -*- coding: utf-8 -*-
"""
Evaluation of parsimonious statistical models.

Models:
1. Ordinary Least Squares (OLS)
2. Ridge Regression

Temporal division:
- Training:   2007–2019
- Validation: 2020–2021
- Test:       2022–2024

Output:
- simple_model_output/SIMPLE_MODEL_RESULTS.xlsx
"""

import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.preprocessing import StandardScaler


# =========================================================
# 0. Basic settings
# =========================================================
DATA_PATH = r"PANEL_ANALYSIS_DATA.xlsx"
SHEET_NAME = "PANEL_ANALYSIS"

TARGET_COL = "RESILIENCE"

FEATURE_COLS = [
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

TRAIN_YEARS = list(range(2007, 2020))
VALIDATION_YEARS = list(range(2020, 2022))
TEST_YEARS = list(range(2022, 2025))

# Ridge候选正则化参数
RIDGE_ALPHA_GRID = [
    0.0001,
    0.001,
    0.01,
    0.1,
    1,
    10,
    100,
    1000,
]

OUTPUT_DIR = Path("simple_model_output")
OUTPUT_FILE = OUTPUT_DIR / "SIMPLE_MODEL_RESULTS.xlsx"


# =========================================================
# 1. Evaluation metrics
# =========================================================
def safe_mape(y_true, y_pred, eps=1e-8):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    denominator = np.maximum(
        np.abs(y_true),
        eps,
    )

    return (
        np.mean(
            np.abs(
                (y_true - y_pred) / denominator
            )
        )
        * 100
    )


def calculate_metrics(y_true, y_pred):
    return {
        "R2": r2_score(y_true, y_pred),
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


# =========================================================
# 2. Read and prepare data
# =========================================================
def read_data():
    input_path = Path(DATA_PATH)

    if not input_path.exists():
        raise FileNotFoundError(
            f"File not found: {input_path.resolve()}"
        )

    if input_path.suffix.lower() == ".csv":
        df = pd.read_csv(
            input_path,
            encoding="utf-8-sig",
        )
    else:
        df = pd.read_excel(
            input_path,
            sheet_name=SHEET_NAME,
        )

    required_cols = (
        ["YEAR"]
        + FEATURE_COLS
        + [TARGET_COL]
    )

    missing_cols = [
        col
        for col in required_cols
        if col not in df.columns
    ]

    if missing_cols:
        raise ValueError(
            "Missing columns: "
            + ", ".join(missing_cols)
        )

    for col in required_cols:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce",
        )

    df = df.dropna(
        subset=required_cols
    ).copy()

    df["YEAR"] = df["YEAR"].astype(int)

    sort_cols = [
        col
        for col in ["YEAR", "REGION"]
        if col in df.columns
    ]

    df = (
        df.sort_values(sort_cols)
        .reset_index(drop=True)
    )

    return df


# =========================================================
# 3. Temporal split
# =========================================================
def temporal_split(df):
    train_df = df[
        df["YEAR"].isin(TRAIN_YEARS)
    ].copy()

    validation_df = df[
        df["YEAR"].isin(VALIDATION_YEARS)
    ].copy()

    test_df = df[
        df["YEAR"].isin(TEST_YEARS)
    ].copy()

    if train_df.empty:
        raise ValueError("Training set is empty.")

    if validation_df.empty:
        raise ValueError("Validation set is empty.")

    if test_df.empty:
        raise ValueError("Test set is empty.")

    return train_df, validation_df, test_df


# =========================================================
# 4. Convert one model result to a record
# =========================================================
def create_result_record(
    model_name,
    train_metrics,
    validation_metrics,
    test_metrics,
    best_alpha=None,
):
    return {
        "MODEL": model_name,

        "TRAIN_R2": train_metrics["R2"],
        "TRAIN_MAE": train_metrics["MAE"],
        "TRAIN_RMSE": train_metrics["RMSE"],
        "TRAIN_MAPE(%)": train_metrics["MAPE(%)"],

        "VAL_R2": validation_metrics["R2"],
        "VAL_MAE": validation_metrics["MAE"],
        "VAL_RMSE": validation_metrics["RMSE"],
        "VAL_MAPE(%)": validation_metrics["MAPE(%)"],

        "TEST_R2": test_metrics["R2"],
        "TEST_MAE": test_metrics["MAE"],
        "TEST_RMSE": test_metrics["RMSE"],
        "TEST_MAPE(%)": test_metrics["MAPE(%)"],

        "BEST_ALPHA": best_alpha,
    }


# =========================================================
# 5. Main
# =========================================================
def main():
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    df = read_data()

    train_df, validation_df, test_df = (
        temporal_split(df)
    )

    X_train = train_df[FEATURE_COLS].to_numpy()
    y_train = train_df[TARGET_COL].to_numpy()

    X_validation = validation_df[
        FEATURE_COLS
    ].to_numpy()

    y_validation = validation_df[
        TARGET_COL
    ].to_numpy()

    X_test = test_df[FEATURE_COLS].to_numpy()
    y_test = test_df[TARGET_COL].to_numpy()

    print("=" * 75)
    print("Temporal sample division")
    print(
        f"Training:   2007-2019, "
        f"N = {len(train_df)}"
    )
    print(
        f"Validation: 2020-2021, "
        f"N = {len(validation_df)}"
    )
    print(
        f"Test:       2022-2024, "
        f"N = {len(test_df)}"
    )
    print("=" * 75)

    # -----------------------------------------------------
    # Standardization
    # Fit the scaler using the training set only
    # -----------------------------------------------------
    scaler = StandardScaler()

    X_train_scaled = scaler.fit_transform(
        X_train
    )

    X_validation_scaled = scaler.transform(
        X_validation
    )

    X_test_scaled = scaler.transform(
        X_test
    )

    result_records = []

    # =====================================================
    # 6. Ordinary Least Squares
    # =====================================================
    ols_model = LinearRegression()

    ols_model.fit(
        X_train_scaled,
        y_train,
    )

    ols_train_pred = ols_model.predict(
        X_train_scaled
    )

    ols_validation_pred = ols_model.predict(
        X_validation_scaled
    )

    ols_test_pred = ols_model.predict(
        X_test_scaled
    )

    ols_train_metrics = calculate_metrics(
        y_train,
        ols_train_pred,
    )

    ols_validation_metrics = calculate_metrics(
        y_validation,
        ols_validation_pred,
    )

    ols_test_metrics = calculate_metrics(
        y_test,
        ols_test_pred,
    )

    result_records.append(
        create_result_record(
            model_name="OLS",
            train_metrics=ols_train_metrics,
            validation_metrics=ols_validation_metrics,
            test_metrics=ols_test_metrics,
        )
    )

    # =====================================================
    # 7. Ridge Regression
    # =====================================================
    ridge_search_records = []

    best_alpha = None
    best_validation_rmse = np.inf
    best_validation_mae = np.inf

    for alpha in RIDGE_ALPHA_GRID:
        ridge_model = Ridge(
            alpha=alpha,
            fit_intercept=True,
        )

        ridge_model.fit(
            X_train_scaled,
            y_train,
        )

        validation_pred = ridge_model.predict(
            X_validation_scaled
        )

        validation_metrics = calculate_metrics(
            y_validation,
            validation_pred,
        )

        ridge_search_records.append({
            "ALPHA": alpha,
            "VAL_R2": validation_metrics["R2"],
            "VAL_MAE": validation_metrics["MAE"],
            "VAL_RMSE": validation_metrics["RMSE"],
            "VAL_MAPE(%)":
                validation_metrics["MAPE(%)"],
        })

        current_rmse = validation_metrics["RMSE"]
        current_mae = validation_metrics["MAE"]

        is_better = (
            current_rmse < best_validation_rmse
            or (
                np.isclose(
                    current_rmse,
                    best_validation_rmse,
                )
                and current_mae
                < best_validation_mae
            )
        )

        if is_better:
            best_alpha = alpha
            best_validation_rmse = current_rmse
            best_validation_mae = current_mae

    # Fit Ridge with the selected alpha
    # using the training set only
    best_ridge_model = Ridge(
        alpha=best_alpha,
        fit_intercept=True,
    )

    best_ridge_model.fit(
        X_train_scaled,
        y_train,
    )

    ridge_train_pred = best_ridge_model.predict(
        X_train_scaled
    )

    ridge_validation_pred = best_ridge_model.predict(
        X_validation_scaled
    )

    # Test set is evaluated only after alpha selection
    ridge_test_pred = best_ridge_model.predict(
        X_test_scaled
    )

    ridge_train_metrics = calculate_metrics(
        y_train,
        ridge_train_pred,
    )

    ridge_validation_metrics = calculate_metrics(
        y_validation,
        ridge_validation_pred,
    )

    ridge_test_metrics = calculate_metrics(
        y_test,
        ridge_test_pred,
    )

    result_records.append(
        create_result_record(
            model_name="Ridge Regression",
            train_metrics=ridge_train_metrics,
            validation_metrics=(
                ridge_validation_metrics
            ),
            test_metrics=ridge_test_metrics,
            best_alpha=best_alpha,
        )
    )

    # =====================================================
    # 8. Results
    # =====================================================
    raw_results_df = pd.DataFrame(
        result_records
    )

    table4_columns = [
        "MODEL",
        "TRAIN_R2",
        "TRAIN_MAE",
        "TRAIN_RMSE",
        "TRAIN_MAPE(%)",
        "TEST_R2",
        "TEST_MAE",
        "TEST_RMSE",
        "TEST_MAPE(%)",
    ]

    table4_df = raw_results_df[
        table4_columns
    ].copy()

    table4_df = table4_df.round({
        "TRAIN_R2": 3,
        "TRAIN_MAE": 3,
        "TRAIN_RMSE": 3,
        "TRAIN_MAPE(%)": 3,
        "TEST_R2": 3,
        "TEST_MAE": 3,
        "TEST_RMSE": 3,
        "TEST_MAPE(%)": 3,
    })

    ridge_search_df = pd.DataFrame(
        ridge_search_records
    ).sort_values(
        "VAL_RMSE",
        ascending=True,
    )

    # Coefficients based on standardized predictors
    coefficient_df = pd.DataFrame({
        "VARIABLE": FEATURE_COLS,
        "OLS_COEFFICIENT":
            ols_model.coef_,
        "RIDGE_COEFFICIENT":
            best_ridge_model.coef_,
    })

    # =====================================================
    # 9. Save results
    # =====================================================
    with pd.ExcelWriter(
        OUTPUT_FILE,
        engine="openpyxl",
    ) as writer:
        table4_df.to_excel(
            writer,
            sheet_name="Table4_Rows",
            index=False,
        )

        raw_results_df.to_excel(
            writer,
            sheet_name="Complete_Metrics",
            index=False,
        )

        ridge_search_df.to_excel(
            writer,
            sheet_name="Ridge_Search",
            index=False,
        )

        coefficient_df.to_excel(
            writer,
            sheet_name="Coefficients",
            index=False,
        )

    print("\nOLS and Ridge evaluation results:")
    print(
        table4_df.to_string(
            index=False
        )
    )

    print(
        f"\nBest Ridge alpha: {best_alpha}"
    )

    print(
        f"\nOutput file: "
        f"{OUTPUT_FILE.resolve()}"
    )

    print("=" * 75)


if __name__ == "__main__":
    main()