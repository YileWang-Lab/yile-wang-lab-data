# -*- coding: utf-8 -*-
"""
Temporal model evaluation for regional resilience.

Baseline temporal split:
- Training set:   2007–2019
- Validation set: 2020–2021
- Test set:       2022–2024

Alternative temporal splits:
1. Pre-pandemic tuning:
   Training: 2007–2017
   Validation: 2018–2019
   Test: 2020–2024

2. Recovery-period testing:
   Training: 2007–2020
   Validation: 2021–2022
   Test: 2023–2024

Models:
- CatBoost-XGBoost hybrid (Ours)
- Random Forest
- SVR
- XGBoost
- GBDT
- ELM
- CatBoost
- AdaBoost

Output:
- MODEL_EVALUATION_RESULTS.xlsx
"""

import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.ensemble import (
    AdaBoostRegressor,
    GradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import ParameterGrid
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR

from catboost import CatBoostRegressor
from xgboost import XGBRegressor


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

ID_COLS = [
    "ADMINCODE",
    "REGION",
    "ZONE",
    "YEAR",
]

RANDOM_STATE = 42

OUTPUT_DIR = Path("model_evaluation_output")
OUTPUT_FILE = OUTPUT_DIR / "MODEL_EVALUATION_RESULTS.xlsx"


# =========================================================
# 1. Temporal split schemes
# =========================================================
SPLIT_SCHEMES = {
    "Baseline": {
        "train": list(range(2007, 2020)),
        "validation": list(range(2020, 2022)),
        "test": list(range(2022, 2025)),
    },

    "Pre-pandemic tuning": {
        "train": list(range(2007, 2018)),
        "validation": list(range(2018, 2020)),
        "test": list(range(2020, 2025)),
    },

    "Recovery-period test": {
        "train": list(range(2007, 2021)),
        "validation": list(range(2021, 2023)),
        "test": list(range(2023, 2025)),
    },
}

BASELINE_SCHEME = "Baseline"


# Models compared in Table 4
MODEL_ORDER = [
    "Ours",
    "Random Forest",
    "SVR",
    "XGBoost",
    "GBDT",
    "ELM",
    "CatBoost",
    "AdaBoost",
]

# Models used in the temporal-split robustness test.
# The proposed model is sufficient for responding to Reviewer 1.
# To test every model, replace this with:
# ROBUSTNESS_MODELS = MODEL_ORDER
ROBUSTNESS_MODELS = ["Ours"]


# =========================================================
# 2. CatBoost-XGBoost hybrid model
# =========================================================
class CatBoostXGBoostHybridRegressor(
    BaseEstimator,
    RegressorMixin
):
    """
    Weighted prediction:

    prediction =
        alpha * CatBoost prediction
        + (1 - alpha) * XGBoost prediction
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
        self.cat_l2_leaf_reg = cat_l2_leaf_reg
        self.cat_learning_rate = cat_learning_rate
        self.xgb_colsample_bytree = xgb_colsample_bytree
        self.xgb_learning_rate = xgb_learning_rate
        self.xgb_max_depth = xgb_max_depth
        self.xgb_n_estimators = xgb_n_estimators
        self.xgb_subsample = xgb_subsample
        self.random_state = random_state

    def fit(self, X, y):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)

        self.cat_model_ = CatBoostRegressor(
            iterations=self.cat_iterations,
            learning_rate=self.cat_learning_rate,
            depth=self.cat_depth,
            l2_leaf_reg=self.cat_l2_leaf_reg,
            loss_function="RMSE",
            random_seed=self.random_state,
            verbose=0,
            allow_writing_files=False,
            thread_count=-1,
        )

        self.xgb_model_ = XGBRegressor(
            objective="reg:squarederror",
            n_estimators=self.xgb_n_estimators,
            learning_rate=self.xgb_learning_rate,
            max_depth=self.xgb_max_depth,
            subsample=self.xgb_subsample,
            colsample_bytree=self.xgb_colsample_bytree,
            random_state=self.random_state,
            n_jobs=-1,
            verbosity=0,
        )

        self.cat_model_.fit(X, y)
        self.xgb_model_.fit(X, y)

        return self

    def predict(self, X):
        X = np.asarray(X, dtype=float)

        cat_pred = self.cat_model_.predict(X)
        xgb_pred = self.xgb_model_.predict(X)

        return (
            self.alpha * cat_pred
            + (1.0 - self.alpha) * xgb_pred
        )


# =========================================================
# 3. Extreme Learning Machine
# =========================================================
class ELMRegressor(BaseEstimator, RegressorMixin):
    """
    Single-hidden-layer Extreme Learning Machine.
    """

    def __init__(
        self,
        hidden_layer_size=100,
        activation="tanh",
        alpha=0.001,
        random_state=42,
    ):
        self.hidden_layer_size = hidden_layer_size
        self.activation = activation
        self.alpha = alpha
        self.random_state = random_state

    def _activate(self, X):
        if self.activation == "tanh":
            return np.tanh(X)

        if self.activation == "relu":
            return np.maximum(0, X)

        if self.activation == "sigmoid":
            X = np.clip(X, -30, 30)
            return 1.0 / (1.0 + np.exp(-X))

        raise ValueError(
            f"Unsupported activation function: "
            f"{self.activation}"
        )

    def fit(self, X, y):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)

        rng = np.random.RandomState(
            self.random_state
        )

        n_features = X.shape[1]

        self.input_weights_ = rng.normal(
            loc=0.0,
            scale=1.0 / np.sqrt(n_features),
            size=(n_features, self.hidden_layer_size),
        )

        self.bias_ = rng.normal(
            loc=0.0,
            scale=1.0,
            size=self.hidden_layer_size,
        )

        hidden_output = self._activate(
            X @ self.input_weights_ + self.bias_
        )

        identity = np.eye(
            self.hidden_layer_size
        )

        self.output_weights_ = np.linalg.solve(
            hidden_output.T @ hidden_output
            + self.alpha * identity,
            hidden_output.T @ y,
        )

        return self

    def predict(self, X):
        X = np.asarray(X, dtype=float)

        hidden_output = self._activate(
            X @ self.input_weights_ + self.bias_
        )

        return hidden_output @ self.output_weights_


# =========================================================
# 4. Hyperparameter grids
# =========================================================
PARAM_GRIDS = {
    "Ours": {
        "alpha": [0.3, 0.5],
        "cat_depth": [4, 6],
        "cat_iterations": [500],
        "cat_l2_leaf_reg": [3, 5],
        "cat_learning_rate": [0.03, 0.05],
        "xgb_colsample_bytree": [0.8, 1.0],
        "xgb_learning_rate": [0.03, 0.05],
        "xgb_max_depth": [3, 5],
        "xgb_n_estimators": [500],
        "xgb_subsample": [0.8, 1.0],
    },

    "Random Forest": {
        "n_estimators": [300, 500],
        "max_depth": [None, 6, 10],
        "min_samples_leaf": [1, 2],
        "max_features": [0.8, 1.0],
    },

    "SVR": {
        "C": [1, 10, 100],
        "epsilon": [0.001, 0.01, 0.05],
        "gamma": ["scale", 0.01, 0.1],
    },

    "XGBoost": {
        "n_estimators": [300, 500],
        "learning_rate": [0.03, 0.05],
        "max_depth": [3, 5],
        "subsample": [0.8, 1.0],
        "colsample_bytree": [0.8],
    },

    "GBDT": {
        "n_estimators": [200, 300],
        "learning_rate": [0.03, 0.05],
        "max_depth": [2, 3],
        "min_samples_leaf": [1, 2],
    },

    "ELM": {
        "hidden_layer_size": [50, 100, 200],
        "activation": ["tanh", "relu"],
        "alpha": [0.0001, 0.001, 0.01],
    },

    "CatBoost": {
        "iterations": [300, 500],
        "learning_rate": [0.03, 0.05],
        "depth": [4, 6],
        "l2_leaf_reg": [3, 5],
    },

    "AdaBoost": {
        "n_estimators": [100, 300, 500],
        "learning_rate": [0.01, 0.05, 0.1],
        "loss": ["linear", "square"],
    },
}


# =========================================================
# 5. Build models
# =========================================================
def build_model(model_name, params):
    if model_name == "Ours":
        return CatBoostXGBoostHybridRegressor(
            **params,
            random_state=RANDOM_STATE,
        )

    if model_name == "Random Forest":
        return RandomForestRegressor(
            **params,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )

    if model_name == "SVR":
        return Pipeline([
            ("scaler", StandardScaler()),
            ("model", SVR(
                kernel="rbf",
                **params,
            )),
        ])

    if model_name == "XGBoost":
        return XGBRegressor(
            objective="reg:squarederror",
            **params,
            random_state=RANDOM_STATE,
            n_jobs=-1,
            verbosity=0,
        )

    if model_name == "GBDT":
        return GradientBoostingRegressor(
            **params,
            random_state=RANDOM_STATE,
            loss="squared_error",
        )

    if model_name == "ELM":
        return Pipeline([
            ("scaler", StandardScaler()),
            ("model", ELMRegressor(
                **params,
                random_state=RANDOM_STATE,
            )),
        ])

    if model_name == "CatBoost":
        return CatBoostRegressor(
            **params,
            loss_function="RMSE",
            random_seed=RANDOM_STATE,
            verbose=0,
            allow_writing_files=False,
            thread_count=-1,
        )

    if model_name == "AdaBoost":
        return AdaBoostRegressor(
            **params,
            random_state=RANDOM_STATE,
        )

    raise ValueError(
        f"Unknown model: {model_name}"
    )


# =========================================================
# 6. Evaluation functions
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


def temporal_split(df, split_definition):
    train_years = split_definition["train"]
    validation_years = split_definition["validation"]
    test_years = split_definition["test"]

    train_df = df[
        df["YEAR"].isin(train_years)
    ].copy()

    validation_df = df[
        df["YEAR"].isin(validation_years)
    ].copy()

    test_df = df[
        df["YEAR"].isin(test_years)
    ].copy()

    if train_df.empty:
        raise ValueError(
            "The training set is empty."
        )

    if validation_df.empty:
        raise ValueError(
            "The validation set is empty."
        )

    if test_df.empty:
        raise ValueError(
            "The test set is empty."
        )

    return (
        train_df,
        validation_df,
        test_df,
    )


def year_range_text(years):
    return f"{min(years)}-{max(years)}"


# =========================================================
# 7. Hyperparameter search
# =========================================================
def tune_and_evaluate(
    model_name,
    train_df,
    validation_df,
    test_df,
):
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

    parameter_list = list(
        ParameterGrid(
            PARAM_GRIDS[model_name]
        )
    )

    best_params = None
    best_validation_rmse = np.inf
    best_validation_mae = np.inf

    print("-" * 80)
    print(
        f"Model: {model_name} | "
        f"Grid size: {len(parameter_list)}"
    )

    # The test set is not used during this loop.
    for index, params in enumerate(
        parameter_list,
        start=1,
    ):
        model = build_model(
            model_name,
            params,
        )

        model.fit(
            X_train,
            y_train,
        )

        validation_prediction = model.predict(
            X_validation
        )

        validation_metrics = calculate_metrics(
            y_validation,
            validation_prediction,
        )

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
            best_validation_rmse = current_rmse
            best_validation_mae = current_mae
            best_params = params.copy()

        if (
            index == 1
            or index % 20 == 0
            or index == len(parameter_list)
        ):
            print(
                f"Completed: "
                f"{index}/{len(parameter_list)}"
            )

    # Refit the selected model using the training set only.
    best_model = build_model(
        model_name,
        best_params,
    )

    best_model.fit(
        X_train,
        y_train,
    )

    train_prediction = best_model.predict(
        X_train
    )

    validation_prediction = best_model.predict(
        X_validation
    )

    # The test set is evaluated only after
    # hyperparameter selection has been completed.
    test_prediction = best_model.predict(
        X_test
    )

    train_metrics = calculate_metrics(
        y_train,
        train_prediction,
    )

    validation_metrics = calculate_metrics(
        y_validation,
        validation_prediction,
    )

    test_metrics = calculate_metrics(
        y_test,
        test_prediction,
    )

    print(f"Best parameters: {best_params}")
    print(
        "Validation RMSE: "
        f"{validation_metrics['RMSE']:.6f}"
    )
    print(
        "Test R2: "
        f"{test_metrics['R2']:.6f}"
    )

    return {
        "model": model_name,
        "best_params": best_params,
        "train_metrics": train_metrics,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
    }


# =========================================================
# 8. Convert results to table records
# =========================================================
def result_to_record(result):
    train = result["train_metrics"]
    validation = result["validation_metrics"]
    test = result["test_metrics"]

    return {
        "MODEL": result["model"],

        "TRAIN_R2": train["R2"],
        "TRAIN_MAE": train["MAE"],
        "TRAIN_RMSE": train["RMSE"],
        "TRAIN_MAPE(%)": train["MAPE(%)"],

        "VAL_R2": validation["R2"],
        "VAL_MAE": validation["MAE"],
        "VAL_RMSE": validation["RMSE"],
        "VAL_MAPE(%)": validation["MAPE(%)"],

        "TEST_R2": test["R2"],
        "TEST_MAE": test["MAE"],
        "TEST_RMSE": test["RMSE"],
        "TEST_MAPE(%)": test["MAPE(%)"],

        "BEST_PARAMS": json.dumps(
            result["best_params"],
            ensure_ascii=False,
        ),
    }


# =========================================================
# 9. Read and clean data
# =========================================================
def read_panel_data():
    input_path = Path(DATA_PATH)

    if not input_path.exists():
        raise FileNotFoundError(
            f"File not found: "
            f"{input_path.resolve()}"
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
        FEATURE_COLS
        + [TARGET_COL, "YEAR"]
    )

    missing_cols = [
        col
        for col in required_cols
        if col not in df.columns
    ]

    if missing_cols:
        raise ValueError(
            "The following columns are missing: "
            + ", ".join(missing_cols)
        )

    keep_cols = list(
        dict.fromkeys(
            [
                col
                for col in ID_COLS
                if col in df.columns
            ]
            + FEATURE_COLS
            + [TARGET_COL]
        )
    )

    df = df[keep_cols].copy()

    numeric_cols = (
        FEATURE_COLS
        + [TARGET_COL, "YEAR"]
    )

    for col in numeric_cols:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce",
        )

    missing_before = df[
        FEATURE_COLS + [TARGET_COL]
    ].isna().sum()

    df = df.dropna(
        subset=FEATURE_COLS
        + [TARGET_COL, "YEAR"]
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

    print("=" * 80)
    print("Data successfully loaded.")
    print(f"Number of observations: {len(df)}")
    print(
        f"Year range: "
        f"{df['YEAR'].min()}-"
        f"{df['YEAR'].max()}"
    )
    print("\nMissing values before deletion:")
    print(missing_before)
    print("=" * 80)

    return df


# =========================================================
# 10. Main
# =========================================================
def main():
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    df = read_panel_data()

    split_count_records = []

    for scheme_name, definition in (
        SPLIT_SCHEMES.items()
    ):
        train_df, validation_df, test_df = (
            temporal_split(
                df,
                definition,
            )
        )

        for subset_name, subset_df, years in [
            (
                "Training",
                train_df,
                definition["train"],
            ),
            (
                "Validation",
                validation_df,
                definition["validation"],
            ),
            (
                "Test",
                test_df,
                definition["test"],
            ),
        ]:
            record = {
                "SCHEME": scheme_name,
                "SUBSET": subset_name,
                "YEARS": year_range_text(years),
                "N_OBSERVATIONS": len(subset_df),
            }

            if "REGION" in subset_df.columns:
                record["N_REGIONS"] = (
                    subset_df["REGION"].nunique()
                )

            split_count_records.append(record)

    split_counts_df = pd.DataFrame(
        split_count_records
    )

    # -----------------------------------------------------
    # Baseline model comparison
    # -----------------------------------------------------
    baseline_definition = SPLIT_SCHEMES[
        BASELINE_SCHEME
    ]

    (
        baseline_train,
        baseline_validation,
        baseline_test,
    ) = temporal_split(
        df,
        baseline_definition,
    )

    print("\n" + "=" * 80)
    print("BASELINE MODEL COMPARISON")
    print(
        "Training: 2007-2019 | "
        "Validation: 2020-2021 | "
        "Test: 2022-2024"
    )
    print("=" * 80)

    baseline_results = {}
    baseline_records = []

    for model_name in MODEL_ORDER:
        result = tune_and_evaluate(
            model_name,
            baseline_train,
            baseline_validation,
            baseline_test,
        )

        baseline_results[model_name] = result
        baseline_records.append(
            result_to_record(result)
        )

    baseline_raw_df = pd.DataFrame(
        baseline_records
    )

    baseline_raw_df["MODEL"] = pd.Categorical(
        baseline_raw_df["MODEL"],
        categories=MODEL_ORDER,
        ordered=True,
    )

    baseline_raw_df = (
        baseline_raw_df
        .sort_values("MODEL")
        .reset_index(drop=True)
    )

    baseline_raw_df["MODEL"] = (
        baseline_raw_df["MODEL"]
        .astype(str)
    )

    # Table 4 contains only training and test results.
    table4_cols = [
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

    table4_df = baseline_raw_df[
        table4_cols
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

    validation_cols = [
        "MODEL",
        "VAL_R2",
        "VAL_MAE",
        "VAL_RMSE",
        "VAL_MAPE(%)",
    ]

    validation_df = baseline_raw_df[
        validation_cols
    ].copy()

    best_params_df = baseline_raw_df[
        ["MODEL", "BEST_PARAMS"]
    ].copy()

    # -----------------------------------------------------
    # Robustness under alternative temporal splits
    # -----------------------------------------------------
    robustness_records = []

    print("\n" + "=" * 80)
    print("TEMPORAL-SPLIT ROBUSTNESS TEST")
    print("=" * 80)

    for scheme_name, definition in (
        SPLIT_SCHEMES.items()
    ):
        (
            train_df,
            validation_split_df,
            test_df,
        ) = temporal_split(
            df,
            definition,
        )

        for model_name in ROBUSTNESS_MODELS:
            # Reuse the baseline result to avoid
            # estimating the same model twice.
            if (
                scheme_name == BASELINE_SCHEME
                and model_name
                in baseline_results
            ):
                result = baseline_results[
                    model_name
                ]
            else:
                print(
                    f"\nScheme: {scheme_name}"
                )

                result = tune_and_evaluate(
                    model_name,
                    train_df,
                    validation_split_df,
                    test_df,
                )

            record = {
                "SCHEME": scheme_name,
                "MODEL": model_name,
                "TRAIN_YEARS": year_range_text(
                    definition["train"]
                ),
                "VALIDATION_YEARS": year_range_text(
                    definition["validation"]
                ),
                "TEST_YEARS": year_range_text(
                    definition["test"]
                ),
                "TRAIN_N": len(train_df),
                "VALIDATION_N": len(
                    validation_split_df
                ),
                "TEST_N": len(test_df),

                "TRAIN_R2":
                    result["train_metrics"]["R2"],
                "TRAIN_MAE":
                    result["train_metrics"]["MAE"],
                "TRAIN_RMSE":
                    result["train_metrics"]["RMSE"],
                "TRAIN_MAPE(%)":
                    result["train_metrics"]["MAPE(%)"],

                "VAL_R2":
                    result["validation_metrics"]["R2"],
                "VAL_MAE":
                    result["validation_metrics"]["MAE"],
                "VAL_RMSE":
                    result["validation_metrics"]["RMSE"],
                "VAL_MAPE(%)":
                    result["validation_metrics"]["MAPE(%)"],

                "TEST_R2":
                    result["test_metrics"]["R2"],
                "TEST_MAE":
                    result["test_metrics"]["MAE"],
                "TEST_RMSE":
                    result["test_metrics"]["RMSE"],
                "TEST_MAPE(%)":
                    result["test_metrics"]["MAPE(%)"],

                "BEST_PARAMS": json.dumps(
                    result["best_params"],
                    ensure_ascii=False,
                ),
            }

            robustness_records.append(record)

    robustness_df = pd.DataFrame(
        robustness_records
    )

    metric_cols = [
        col
        for col in robustness_df.columns
        if col.endswith(
            (
                "_R2",
                "_MAE",
                "_RMSE",
                "MAPE(%)",
            )
        )
    ]

    robustness_df[metric_cols] = (
        robustness_df[metric_cols]
        .round(4)
    )

    # -----------------------------------------------------
    # Save results
    # -----------------------------------------------------
    with pd.ExcelWriter(
        OUTPUT_FILE,
        engine="openpyxl",
    ) as writer:
        table4_df.to_excel(
            writer,
            sheet_name="Table4",
            index=False,
        )

        baseline_raw_df.to_excel(
            writer,
            sheet_name="Baseline_Raw",
            index=False,
        )

        validation_df.to_excel(
            writer,
            sheet_name="Validation",
            index=False,
        )

        best_params_df.to_excel(
            writer,
            sheet_name="Best_Parameters",
            index=False,
        )

        robustness_df.to_excel(
            writer,
            sheet_name="Temporal_Robustness",
            index=False,
        )

        split_counts_df.to_excel(
            writer,
            sheet_name="Sample_Counts",
            index=False,
        )

    print("\n" + "=" * 80)
    print("MODEL EVALUATION COMPLETED")
    print("=" * 80)

    print("\nTable 4:")
    print(
        table4_df.to_string(
            index=False
        )
    )

    print("\nTemporal robustness results:")
    print(
        robustness_df[
            [
                "SCHEME",
                "MODEL",
                "TRAIN_YEARS",
                "VALIDATION_YEARS",
                "TEST_YEARS",
                "TEST_R2",
                "TEST_MAE",
                "TEST_RMSE",
                "TEST_MAPE(%)",
            ]
        ].to_string(index=False)
    )

    print(
        f"\nOutput file: "
        f"{OUTPUT_FILE.resolve()}"
    )

    print("=" * 80)


if __name__ == "__main__":
    main()