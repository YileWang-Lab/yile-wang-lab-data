# -*- coding: utf-8 -*-
"""
Temporal model evaluation for regional resilience.

Baseline split:
- Training:   2007-2019
- Validation: 2020-2021
- Test:       2022-2024

Alternative splits:
1. Pre-pandemic tuning
   Training:   2007-2017
   Validation: 2018-2019
   Test:       2020-2024

2. Recovery-period test
   Training:   2007-2020
   Validation: 2021-2022
   Test:       2023-2024

Outputs:
- Predictive performance
- Adjusted R-squared
- AIC and BIC for OLS and Ridge
- Validation results
- Optimal parameters
- Temporal robustness results
"""

import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from sklearn.base import (
    BaseEstimator,
    RegressorMixin,
)
from sklearn.ensemble import (
    AdaBoostRegressor,
    GradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.linear_model import (
    LinearRegression,
    Ridge,
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
# 1. Basic settings
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

OUTPUT_DIR = Path(
    "model_evaluation_output"
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / "MODEL_EVALUATION_WITH_INFORMATION_CRITERIA.xlsx"
)


# =========================================================
# 2. Temporal split schemes
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


# =========================================================
# 3. Model order
# =========================================================
MODEL_ORDER = [
    "Ours",
    "Random Forest",
    "SVR",
    "XGBoost",
    "GBDT",
    "ELM",
    "CatBoost",
    "AdaBoost",
    "OLS",
    "Ridge Regression",
]

# Alternative temporal divisions only need to test
# the proposed model.
ROBUSTNESS_MODELS = [
    "Ours",
]


# =========================================================
# 4. CatBoost-XGBoost hybrid model
# =========================================================
class CatBoostXGBoostHybridRegressor(
    BaseEstimator,
    RegressorMixin,
):
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

        self.xgb_colsample_bytree = (
            xgb_colsample_bytree
        )
        self.xgb_learning_rate = (
            xgb_learning_rate
        )
        self.xgb_max_depth = xgb_max_depth
        self.xgb_n_estimators = xgb_n_estimators
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
            colsample_bytree=(
                self.xgb_colsample_bytree
            ),
            random_state=self.random_state,
            n_jobs=-1,
            verbosity=0,
        )

        self.cat_model_.fit(
            X,
            y,
        )

        self.xgb_model_.fit(
            X,
            y,
        )

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


# =========================================================
# 5. Extreme Learning Machine
# =========================================================
class ELMRegressor(
    BaseEstimator,
    RegressorMixin,
):
    def __init__(
        self,
        hidden_layer_size=100,
        activation="tanh",
        alpha=0.001,
        random_state=42,
    ):
        self.hidden_layer_size = (
            hidden_layer_size
        )
        self.activation = activation
        self.alpha = alpha
        self.random_state = random_state

    def _activate(self, X):
        if self.activation == "tanh":
            return np.tanh(X)

        if self.activation == "relu":
            return np.maximum(
                0,
                X,
            )

        if self.activation == "sigmoid":
            X = np.clip(
                X,
                -30,
                30,
            )

            return 1.0 / (
                1.0 + np.exp(-X)
            )

        raise ValueError(
            f"Unsupported activation: "
            f"{self.activation}"
        )

    def fit(self, X, y):
        X = np.asarray(
            X,
            dtype=float,
        )

        y = np.asarray(
            y,
            dtype=float,
        )

        random_generator = (
            np.random.RandomState(
                self.random_state
            )
        )

        n_features = X.shape[1]

        self.input_weights_ = (
            random_generator.normal(
                loc=0.0,
                scale=(
                    1.0
                    / np.sqrt(n_features)
                ),
                size=(
                    n_features,
                    self.hidden_layer_size,
                ),
            )
        )

        self.bias_ = (
            random_generator.normal(
                loc=0.0,
                scale=1.0,
                size=self.hidden_layer_size,
            )
        )

        hidden_output = self._activate(
            X @ self.input_weights_
            + self.bias_
        )

        identity = np.eye(
            self.hidden_layer_size
        )

        self.output_weights_ = (
            np.linalg.solve(
                hidden_output.T
                @ hidden_output
                + self.alpha * identity,
                hidden_output.T @ y,
            )
        )

        return self

    def predict(self, X):
        X = np.asarray(
            X,
            dtype=float,
        )

        hidden_output = self._activate(
            X @ self.input_weights_
            + self.bias_
        )

        return (
            hidden_output
            @ self.output_weights_
        )


# =========================================================
# 6. Hyperparameter grids
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

    "OLS": {},

    "Ridge Regression": {
        "alpha": [
            0.001,
            0.01,
            0.1,
            1.0,
            10.0,
            100.0,
        ],
    },
}


# =========================================================
# 7. Build models
# =========================================================
def build_model(
    model_name,
    params,
):
    if model_name == "Ours":
        return (
            CatBoostXGBoostHybridRegressor(
                **params,
                random_state=RANDOM_STATE,
            )
        )

    if model_name == "Random Forest":
        return RandomForestRegressor(
            **params,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        )

    if model_name == "SVR":
        return Pipeline([
            (
                "scaler",
                StandardScaler(),
            ),
            (
                "model",
                SVR(
                    kernel="rbf",
                    **params,
                ),
            ),
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
            (
                "scaler",
                StandardScaler(),
            ),
            (
                "model",
                ELMRegressor(
                    **params,
                    random_state=RANDOM_STATE,
                ),
            ),
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

    if model_name == "OLS":
        return LinearRegression()

    if model_name == "Ridge Regression":
        return Pipeline([
            (
                "scaler",
                StandardScaler(),
            ),
            (
                "model",
                Ridge(
                    alpha=params["alpha"],
                    fit_intercept=True,
                ),
            ),
        ])

    raise ValueError(
        f"Unknown model: {model_name}"
    )


# =========================================================
# 8. Basic evaluation functions
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


def calculate_adjusted_r2(
    r2,
    n_observations,
    n_predictors,
):
    if (
        n_observations
        <= n_predictors + 1
    ):
        return np.nan

    return (
        1.0
        - (1.0 - r2)
        * (
            (n_observations - 1)
            / (
                n_observations
                - n_predictors
                - 1
            )
        )
    )


# =========================================================
# 9. AIC and BIC
# =========================================================
def calculate_information_criteria(
    y_true,
    y_pred,
    effective_parameter_count,
):
    """
    Gaussian residual likelihood.

    AIC and BIC are only calculated when an
    effective parameter count is available.

    For OLS:
        k = coefficients + intercept + variance

    For Ridge:
        k = effective regression degrees of freedom
            + variance parameter
    """
    if (
        effective_parameter_count is None
        or not np.isfinite(
            effective_parameter_count
        )
    ):
        return np.nan, np.nan

    y_true = np.asarray(
        y_true,
        dtype=float,
    )

    y_pred = np.asarray(
        y_pred,
        dtype=float,
    )

    n_observations = len(y_true)

    residuals = (
        y_true - y_pred
    )

    rss = np.sum(
        residuals ** 2
    )

    rss = max(
        float(rss),
        np.finfo(float).tiny,
    )

    residual_variance = (
        rss / n_observations
    )

    minus_two_log_likelihood = (
        n_observations
        * (
            np.log(2.0 * np.pi)
            + 1.0
            + np.log(
                residual_variance
            )
        )
    )

    aic = (
        minus_two_log_likelihood
        + 2.0
        * effective_parameter_count
    )

    bic = (
        minus_two_log_likelihood
        + np.log(n_observations)
        * effective_parameter_count
    )

    return (
        float(aic),
        float(bic),
    )


def get_effective_parameter_count(
    model_name,
    fitted_model,
    X_train,
):
    """
    Return effective parameter count used by AIC/BIC.

    The variance parameter is included.
    """
    n_predictors = X_train.shape[1]

    if model_name == "OLS":
        # p coefficients + intercept + variance
        return float(
            n_predictors + 2
        )

    if model_name == "Ridge Regression":
        scaler = (
            fitted_model.named_steps[
                "scaler"
            ]
        )

        ridge_model = (
            fitted_model.named_steps[
                "model"
            ]
        )

        X_scaled = scaler.transform(
            X_train
        )

        singular_values = (
            np.linalg.svd(
                X_scaled,
                compute_uv=False,
            )
        )

        squared_singular_values = (
            singular_values ** 2
        )

        ridge_df = np.sum(
            squared_singular_values
            / (
                squared_singular_values
                + ridge_model.alpha
            )
        )

        # +1 intercept
        # +1 residual variance parameter
        return float(
            ridge_df + 2.0
        )

    # Conventional AIC/BIC are not directly
    # applicable to the remaining models.
    return np.nan


def calculate_metrics(
    y_true,
    y_pred,
    n_predictors,
    effective_parameter_count=np.nan,
):
    r2 = r2_score(
        y_true,
        y_pred,
    )

    adjusted_r2 = (
        calculate_adjusted_r2(
            r2,
            len(y_true),
            n_predictors,
        )
    )

    aic, bic = (
        calculate_information_criteria(
            y_true,
            y_pred,
            effective_parameter_count,
        )
    )

    return {
        "N": len(y_true),
        "R2": r2,
        "ADJUSTED_R2": adjusted_r2,
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
        "AIC": aic,
        "BIC": bic,
    }


# =========================================================
# 10. Temporal split
# =========================================================
def temporal_split(
    df,
    split_definition,
):
    train_df = df[
        df["YEAR"].isin(
            split_definition["train"]
        )
    ].copy()

    validation_df = df[
        df["YEAR"].isin(
            split_definition["validation"]
        )
    ].copy()

    test_df = df[
        df["YEAR"].isin(
            split_definition["test"]
        )
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

    return (
        train_df,
        validation_df,
        test_df,
    )


def year_range_text(years):
    return (
        f"{min(years)}-"
        f"{max(years)}"
    )


# =========================================================
# 11. Hyperparameter search and evaluation
# =========================================================
def tune_and_evaluate(
    model_name,
    train_df,
    validation_df,
    test_df,
):
    X_train = (
        train_df[FEATURE_COLS]
        .to_numpy(dtype=float)
    )

    y_train = (
        train_df[TARGET_COL]
        .to_numpy(dtype=float)
    )

    X_validation = (
        validation_df[FEATURE_COLS]
        .to_numpy(dtype=float)
    )

    y_validation = (
        validation_df[TARGET_COL]
        .to_numpy(dtype=float)
    )

    X_test = (
        test_df[FEATURE_COLS]
        .to_numpy(dtype=float)
    )

    y_test = (
        test_df[TARGET_COL]
        .to_numpy(dtype=float)
    )

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
        f"Model: {model_name}"
    )
    print(
        f"Grid size: "
        f"{len(parameter_list)}"
    )

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

        validation_prediction = (
            model.predict(
                X_validation
            )
        )

        validation_rmse = np.sqrt(
            mean_squared_error(
                y_validation,
                validation_prediction,
            )
        )

        validation_mae = (
            mean_absolute_error(
                y_validation,
                validation_prediction,
            )
        )

        is_better = (
            validation_rmse
            < best_validation_rmse
            or (
                np.isclose(
                    validation_rmse,
                    best_validation_rmse,
                )
                and validation_mae
                < best_validation_mae
            )
        )

        if is_better:
            best_validation_rmse = (
                validation_rmse
            )

            best_validation_mae = (
                validation_mae
            )

            best_params = (
                params.copy()
            )

        if (
            index == 1
            or index % 20 == 0
            or index
            == len(parameter_list)
        ):
            print(
                f"Completed: "
                f"{index}/"
                f"{len(parameter_list)}"
            )

    best_model = build_model(
        model_name,
        best_params,
    )

    best_model.fit(
        X_train,
        y_train,
    )

    train_prediction = (
        best_model.predict(
            X_train
        )
    )

    validation_prediction = (
        best_model.predict(
            X_validation
        )
    )

    test_prediction = (
        best_model.predict(
            X_test
        )
    )

    effective_parameter_count = (
        get_effective_parameter_count(
            model_name,
            best_model,
            X_train,
        )
    )

    n_predictors = len(
        FEATURE_COLS
    )

    train_metrics = (
        calculate_metrics(
            y_train,
            train_prediction,
            n_predictors,
            effective_parameter_count,
        )
    )

    validation_metrics = (
        calculate_metrics(
            y_validation,
            validation_prediction,
            n_predictors,
            effective_parameter_count,
        )
    )

    test_metrics = (
        calculate_metrics(
            y_test,
            test_prediction,
            n_predictors,
            effective_parameter_count,
        )
    )

    print(
        f"Best parameters: "
        f"{best_params}"
    )

    print(
        f"Training R2: "
        f"{train_metrics['R2']:.6f}"
    )

    print(
        f"Training adjusted R2: "
        f"{train_metrics['ADJUSTED_R2']:.6f}"
    )

    print(
        f"Test R2: "
        f"{test_metrics['R2']:.6f}"
    )

    print(
        f"Test adjusted R2: "
        f"{test_metrics['ADJUSTED_R2']:.6f}"
    )

    if np.isfinite(
        effective_parameter_count
    ):
        print(
            "Effective parameter count: "
            f"{effective_parameter_count:.6f}"
        )

        print(
            f"Training AIC: "
            f"{train_metrics['AIC']:.6f}"
        )

        print(
            f"Training BIC: "
            f"{train_metrics['BIC']:.6f}"
        )

        print(
            f"Test AIC: "
            f"{test_metrics['AIC']:.6f}"
        )

        print(
            f"Test BIC: "
            f"{test_metrics['BIC']:.6f}"
        )

    else:
        print(
            "AIC/BIC: N.A. for this model"
        )

    return {
        "model": model_name,
        "best_params": best_params,
        "effective_parameter_count": (
            effective_parameter_count
        ),
        "train_metrics": train_metrics,
        "validation_metrics": (
            validation_metrics
        ),
        "test_metrics": test_metrics,
    }


# =========================================================
# 12. Convert results to table record
# =========================================================
def result_to_record(result):
    train = result["train_metrics"]
    validation = (
        result["validation_metrics"]
    )
    test = result["test_metrics"]

    return {
        "MODEL": result["model"],

        "N_PREDICTORS": len(
            FEATURE_COLS
        ),

        "IC_EFFECTIVE_K": result[
            "effective_parameter_count"
        ],

        "TRAIN_N": train["N"],
        "TRAIN_R2": train["R2"],
        "TRAIN_ADJUSTED_R2": (
            train["ADJUSTED_R2"]
        ),
        "TRAIN_MAE": train["MAE"],
        "TRAIN_RMSE": train["RMSE"],
        "TRAIN_MAPE(%)": (
            train["MAPE(%)"]
        ),
        "TRAIN_AIC": train["AIC"],
        "TRAIN_BIC": train["BIC"],

        "VAL_N": validation["N"],
        "VAL_R2": validation["R2"],
        "VAL_ADJUSTED_R2": (
            validation["ADJUSTED_R2"]
        ),
        "VAL_MAE": validation["MAE"],
        "VAL_RMSE": validation["RMSE"],
        "VAL_MAPE(%)": (
            validation["MAPE(%)"]
        ),
        "VAL_AIC": validation["AIC"],
        "VAL_BIC": validation["BIC"],

        "TEST_N": test["N"],
        "TEST_R2": test["R2"],
        "TEST_ADJUSTED_R2": (
            test["ADJUSTED_R2"]
        ),
        "TEST_MAE": test["MAE"],
        "TEST_RMSE": test["RMSE"],
        "TEST_MAPE(%)": (
            test["MAPE(%)"]
        ),
        "TEST_AIC": test["AIC"],
        "TEST_BIC": test["BIC"],

        "BEST_PARAMS": json.dumps(
            result["best_params"],
            ensure_ascii=False,
        ),
    }


# =========================================================
# 13. Read data
# =========================================================
def read_panel_data():
    input_path = Path(
        DATA_PATH
    )

    if not input_path.exists():
        raise FileNotFoundError(
            f"File not found: "
            f"{input_path.resolve()}"
        )

    if (
        input_path.suffix.lower()
        == ".csv"
    ):
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
        + [
            TARGET_COL,
            "YEAR",
        ]
    )

    missing_cols = [
        col
        for col in required_cols
        if col not in df.columns
    ]

    if missing_cols:
        raise ValueError(
            "Missing columns: "
            + ", ".join(
                missing_cols
            )
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

    df = df[
        keep_cols
    ].copy()

    numeric_cols = (
        FEATURE_COLS
        + [
            TARGET_COL,
            "YEAR",
        ]
    )

    for col in numeric_cols:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce",
        )

    missing_before = (
        df[
            FEATURE_COLS
            + [TARGET_COL]
        ]
        .isna()
        .sum()
    )

    df = df.dropna(
        subset=(
            FEATURE_COLS
            + [
                TARGET_COL,
                "YEAR",
            ]
        )
    ).copy()

    df["YEAR"] = (
        df["YEAR"]
        .astype(int)
    )

    sort_cols = [
        col
        for col in [
            "YEAR",
            "REGION",
        ]
        if col in df.columns
    ]

    df = (
        df.sort_values(
            sort_cols
        )
        .reset_index(drop=True)
    )

    print("=" * 80)
    print(
        "Data successfully loaded."
    )
    print(
        f"Number of observations: "
        f"{len(df)}"
    )
    print(
        f"Year range: "
        f"{df['YEAR'].min()}-"
        f"{df['YEAR'].max()}"
    )
    print(
        "\nMissing values before deletion:"
    )
    print(missing_before)
    print("=" * 80)

    return df


# =========================================================
# 14. Round tables
# =========================================================
def round_numeric_columns(
    df,
    decimals=6,
):
    output = df.copy()

    numeric_cols = (
        output.select_dtypes(
            include=[np.number]
        ).columns
    )

    output[numeric_cols] = (
        output[numeric_cols]
        .round(decimals)
    )

    return output


# =========================================================
# 15. Main
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
        (
            train_df,
            validation_df,
            test_df,
        ) = temporal_split(
            df,
            definition,
        )

        for (
            subset_name,
            subset_df,
            years,
        ) in [
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
                "YEARS": (
                    year_range_text(
                        years
                    )
                ),
                "N_OBSERVATIONS": (
                    len(subset_df)
                ),
            }

            if (
                "REGION"
                in subset_df.columns
            ):
                record["N_REGIONS"] = (
                    subset_df[
                        "REGION"
                    ].nunique()
                )

            split_count_records.append(
                record
            )

    split_counts_df = (
        pd.DataFrame(
            split_count_records
        )
    )

    # -----------------------------------------------------
    # Baseline comparison
    # -----------------------------------------------------
    baseline_definition = (
        SPLIT_SCHEMES[
            BASELINE_SCHEME
        ]
    )

    (
        baseline_train,
        baseline_validation,
        baseline_test,
    ) = temporal_split(
        df,
        baseline_definition,
    )

    print("\n" + "=" * 80)
    print(
        "BASELINE MODEL COMPARISON"
    )
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

        baseline_results[
            model_name
        ] = result

        baseline_records.append(
            result_to_record(result)
        )

    baseline_raw_df = (
        pd.DataFrame(
            baseline_records
        )
    )

    baseline_raw_df["MODEL"] = (
        pd.Categorical(
            baseline_raw_df["MODEL"],
            categories=MODEL_ORDER,
            ordered=True,
        )
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

    # -----------------------------------------------------
    # Main predictive-performance table
    # -----------------------------------------------------
    predictive_cols = [
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

    predictive_table = (
        baseline_raw_df[
            predictive_cols
        ].copy()
    )

    predictive_table = (
        round_numeric_columns(
            predictive_table,
            decimals=3,
        )
    )

    # -----------------------------------------------------
    # Reviewer-requested criteria
    # -----------------------------------------------------
    reviewer_cols = [
        "MODEL",
        "N_PREDICTORS",
        "IC_EFFECTIVE_K",

        "TRAIN_N",
        "TRAIN_R2",
        "TRAIN_ADJUSTED_R2",
        "TRAIN_AIC",
        "TRAIN_BIC",

        "TEST_N",
        "TEST_R2",
        "TEST_ADJUSTED_R2",
        "TEST_AIC",
        "TEST_BIC",
    ]

    reviewer_table = (
        baseline_raw_df[
            reviewer_cols
        ].copy()
    )

    reviewer_table = (
        round_numeric_columns(
            reviewer_table,
            decimals=4,
        )
    )

    reviewer_table[
        "AIC_BIC_APPLICABILITY"
    ] = np.where(
        reviewer_table[
            "MODEL"
        ].isin(
            [
                "OLS",
                "Ridge Regression",
            ]
        ),
        "Applicable",
        "N.A.: no directly comparable likelihood/effective df",
    )

    # -----------------------------------------------------
    # Validation table
    # -----------------------------------------------------
    validation_cols = [
        "MODEL",
        "VAL_N",
        "VAL_R2",
        "VAL_ADJUSTED_R2",
        "VAL_MAE",
        "VAL_RMSE",
        "VAL_MAPE(%)",
        "VAL_AIC",
        "VAL_BIC",
    ]

    validation_table = (
        baseline_raw_df[
            validation_cols
        ].copy()
    )

    validation_table = (
        round_numeric_columns(
            validation_table,
            decimals=4,
        )
    )

    # -----------------------------------------------------
    # Best parameters
    # -----------------------------------------------------
    best_params_table = (
        baseline_raw_df[
            [
                "MODEL",
                "BEST_PARAMS",
            ]
        ].copy()
    )

    # -----------------------------------------------------
    # Alternative temporal split robustness
    # -----------------------------------------------------
    robustness_records = []

    print("\n" + "=" * 80)
    print(
        "TEMPORAL-SPLIT ROBUSTNESS TEST"
    )
    print("=" * 80)

    for scheme_name, definition in (
        SPLIT_SCHEMES.items()
    ):
        (
            train_df,
            validation_df,
            test_df,
        ) = temporal_split(
            df,
            definition,
        )

        for model_name in (
            ROBUSTNESS_MODELS
        ):
            if (
                scheme_name
                == BASELINE_SCHEME
                and model_name
                in baseline_results
            ):
                result = (
                    baseline_results[
                        model_name
                    ]
                )

            else:
                print(
                    f"\nScheme: "
                    f"{scheme_name}"
                )

                result = tune_and_evaluate(
                    model_name,
                    train_df,
                    validation_df,
                    test_df,
                )

            train_metrics = (
                result[
                    "train_metrics"
                ]
            )

            validation_metrics = (
                result[
                    "validation_metrics"
                ]
            )

            test_metrics = (
                result[
                    "test_metrics"
                ]
            )

            robustness_records.append({
                "SCHEME": scheme_name,
                "MODEL": model_name,

                "TRAIN_YEARS": (
                    year_range_text(
                        definition["train"]
                    )
                ),

                "VALIDATION_YEARS": (
                    year_range_text(
                        definition[
                            "validation"
                        ]
                    )
                ),

                "TEST_YEARS": (
                    year_range_text(
                        definition["test"]
                    )
                ),

                "TRAIN_N": (
                    train_metrics["N"]
                ),

                "TRAIN_R2": (
                    train_metrics["R2"]
                ),

                "TRAIN_ADJUSTED_R2": (
                    train_metrics[
                        "ADJUSTED_R2"
                    ]
                ),

                "TRAIN_MAE": (
                    train_metrics["MAE"]
                ),

                "TRAIN_RMSE": (
                    train_metrics["RMSE"]
                ),

                "TRAIN_MAPE(%)": (
                    train_metrics[
                        "MAPE(%)"
                    ]
                ),

                "VAL_N": (
                    validation_metrics["N"]
                ),

                "VAL_R2": (
                    validation_metrics["R2"]
                ),

                "VAL_ADJUSTED_R2": (
                    validation_metrics[
                        "ADJUSTED_R2"
                    ]
                ),

                "TEST_N": (
                    test_metrics["N"]
                ),

                "TEST_R2": (
                    test_metrics["R2"]
                ),

                "TEST_ADJUSTED_R2": (
                    test_metrics[
                        "ADJUSTED_R2"
                    ]
                ),

                "TEST_MAE": (
                    test_metrics["MAE"]
                ),

                "TEST_RMSE": (
                    test_metrics["RMSE"]
                ),

                "TEST_MAPE(%)": (
                    test_metrics[
                        "MAPE(%)"
                    ]
                ),

                "BEST_PARAMS": json.dumps(
                    result["best_params"],
                    ensure_ascii=False,
                ),
            })

    robustness_table = (
        pd.DataFrame(
            robustness_records
        )
    )

    robustness_table = (
        round_numeric_columns(
            robustness_table,
            decimals=4,
        )
    )

    # -----------------------------------------------------
    # Notes
    # -----------------------------------------------------
    notes_table = pd.DataFrame({
        "Item": [
            "Adjusted R-squared",
            "OLS AIC/BIC",
            "Ridge AIC/BIC",
            "Machine-learning AIC/BIC",
            "Test AIC/BIC",
            "Model selection",
        ],

        "Explanation": [
            (
                "Calculated as 1-(1-R2)"
                "*(n-1)/(n-p-1), where "
                "p=10 for all models."
            ),

            (
                "Uses p regression "
                "coefficients, one intercept, "
                "and one residual-variance "
                "parameter."
            ),

            (
                "Uses the effective Ridge "
                "degrees of freedom obtained "
                "from the singular values of "
                "the standardized training "
                "design matrix, plus the "
                "intercept and variance."
            ),

            (
                "Reported as N.A. because "
                "conventional AIC/BIC require "
                "a comparable likelihood and "
                "identifiable effective "
                "degrees of freedom."
            ),

            (
                "Reported for OLS and Ridge "
                "as residual-based descriptive "
                "criteria using the effective "
                "parameter count estimated "
                "from the training model."
            ),

            (
                "The primary comparison is "
                "based on out-of-time test R2, "
                "MAE, RMSE and MAPE."
            ),
        ],
    })

    # -----------------------------------------------------
    # Save results
    # -----------------------------------------------------
    with pd.ExcelWriter(
        OUTPUT_FILE,
        engine="openpyxl",
    ) as writer:

        predictive_table.to_excel(
            writer,
            sheet_name="Predictive_Performance",
            index=False,
        )

        reviewer_table.to_excel(
            writer,
            sheet_name="Reviewer_Criteria",
            index=False,
        )

        validation_table.to_excel(
            writer,
            sheet_name="Validation",
            index=False,
        )

        baseline_raw_df.to_excel(
            writer,
            sheet_name="Baseline_Raw",
            index=False,
        )

        best_params_table.to_excel(
            writer,
            sheet_name="Best_Parameters",
            index=False,
        )

        robustness_table.to_excel(
            writer,
            sheet_name="Temporal_Robustness",
            index=False,
        )

        split_counts_df.to_excel(
            writer,
            sheet_name="Sample_Counts",
            index=False,
        )

        notes_table.to_excel(
            writer,
            sheet_name="Method_Notes",
            index=False,
        )

    # -----------------------------------------------------
    # Print results
    # -----------------------------------------------------
    print("\n" + "=" * 80)
    print(
        "MODEL EVALUATION COMPLETED"
    )
    print("=" * 80)

    print(
        "\nPredictive performance:"
    )

    print(
        predictive_table.to_string(
            index=False
        )
    )

    print(
        "\nReviewer-requested criteria:"
    )

    print(
        reviewer_table.to_string(
            index=False
        )
    )

    print(
        "\nTemporal robustness:"
    )

    print(
        robustness_table[
            [
                "SCHEME",
                "MODEL",
                "TRAIN_YEARS",
                "VALIDATION_YEARS",
                "TEST_YEARS",
                "TRAIN_ADJUSTED_R2",
                "TEST_ADJUSTED_R2",
                "TEST_R2",
                "TEST_MAE",
                "TEST_RMSE",
                "TEST_MAPE(%)",
            ]
        ].to_string(
            index=False
        )
    )

    print(
        f"\nOutput file: "
        f"{OUTPUT_FILE.resolve()}"
    )

    print("=" * 80)


if __name__ == "__main__":
    main()