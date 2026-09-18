# -*- coding: utf-8 -*-
"""
CatBoost-XGBoost + SHAP
单文件导入版本：
- 一个文件同时包含目标变量和外生变量
- 目标变量：Spearman-CRITIC, EWM, CV, DM, PCA, Factor
- 外生变量：URB, GOV, INNO, EDU, OPENPC, FIN, DIG, PRI, INC, SOC
- 仅输出核心图：SHAP beeswarm + right-side bar
"""

import warnings
warnings.filterwarnings("ignore")

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import cm

from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error

from xgboost import XGBRegressor
from catboost import CatBoostRegressor
import shap


# ======================
# 全局绘图风格
# ======================
plt.rcParams.update({
    'font.family': 'Times New Roman',
    'font.weight': 'bold',
    'font.size': 16,
    'axes.labelweight': 'bold',
    'axes.titleweight': 'bold',
    'axes.labelsize': 18,
    'axes.titlesize': 20,
    'xtick.labelsize': 16,
    'ytick.labelsize': 16,
    'legend.fontsize': 16,
    'axes.linewidth': 2.0,
    'axes.edgecolor': 'black',
    'axes.unicode_minus': True,
    'xtick.major.width': 2.0,
    'ytick.major.width': 2.0,
    'xtick.major.size': 8,
    'ytick.major.size': 8,
})


# ======================
# 配置区
# ======================
DATA_PATH = r"PANEL_ANALYSIS_DATA - 副本.xlsx"

# 若你知道 sheet 名，直接写成字符串；不知道就保持 0
SHEET_NAME = 0

FEATURE_COLS = [
    "URB", "GOV", "INNO", "EDU", "OPENPC",
    "FIN", "DIG", "PRI", "INC", "SOC"
]

TARGETS = [
    "Spearman-CRITIC",
    "EWM",
    "CV",
    "DM",
    "PCA",
    "Factor"
]

ID_COLS = ["ADMINCODE", "REGION", "ZONE", "YEAR"]

TEST_SIZE = 0.2
RANDOM_STATE = 42

# 固定参数
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
    "xgb_subsample": 1.0
}

OUTPUT_DIR = Path("ML_SHAP_MULTI_TARGET")
OUTPUT_DIR.mkdir(exist_ok=True)


# ======================
# 工具函数
# ======================
def safe_mape(y_true, y_pred, eps=1e-8):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return np.mean(np.abs((y_true - y_pred) / np.maximum(np.abs(y_true), eps))) * 100


def save_png_pdf(base_path_no_suffix: Path):
    plt.tight_layout()
    plt.savefig(base_path_no_suffix.with_suffix(".png"), dpi=300, bbox_inches="tight", format="png")
    plt.savefig(base_path_no_suffix.with_suffix(".pdf"), dpi=300, bbox_inches="tight", format="pdf")
    plt.close()


def sanitize_name(name: str) -> str:
    return (
        str(name)
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
    )


def read_excel_auto(path, sheet_name=0, required_cols=None):
    """
    优先按指定sheet读取。
    若指定sheet缺少所需列，则自动扫描所有sheet。
    """
    xls = pd.ExcelFile(path)

    # 先试指定sheet
    try:
        df0 = pd.read_excel(path, sheet_name=sheet_name)
        if required_cols is None or all(c in df0.columns for c in required_cols):
            print(f"[INFO] Using sheet: {sheet_name}")
            return df0
    except Exception:
        pass

    # 再自动扫描
    for sh in xls.sheet_names:
        df_tmp = pd.read_excel(path, sheet_name=sh, nrows=5)
        if required_cols is None or all(c in df_tmp.columns for c in required_cols):
            print(f"[INFO] Auto-detected sheet: {sh}")
            return pd.read_excel(path, sheet_name=sh)

    raise ValueError(f"在文件 {path} 中未找到包含所需列的sheet。缺少列: {required_cols}")


# ======================
# CatBoost-XGBoost 融合模型
# ======================
class CatBoostXGBoostHybridRegressor(BaseEstimator, RegressorMixin):
    """
    pred = alpha * CatBoost_pred + (1 - alpha) * XGBoost_pred
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
        random_state=42
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
            random_state=self.random_state,
            verbose=0
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
            verbosity=0
        )

        self.cat_model_.fit(X, y)
        self.xgb_model_.fit(X, y)
        return self

    def predict(self, X):
        X = np.asarray(X, dtype=float)
        cat_pred = self.cat_model_.predict(X)
        xgb_pred = self.xgb_model_.predict(X)
        return self.alpha * cat_pred + (1.0 - self.alpha) * xgb_pred


# ======================
# 核心 SHAP 图
# ======================
def plot_shap_beeswarm_bar(shap_values_arr, X_df, shap_df, output_path_no_suffix, title_text):
    plt.figure(figsize=(16, 10), dpi=300)

    shap.summary_plot(
        shap_values_arr,
        X_df,
        plot_type="dot",
        cmap=plt.get_cmap("plasma"),
        show=False
    )

    ax1 = plt.gca()
    ax1.set_position([0.30, 0.10, 0.62, 0.85])

    # 放大点
    for collection in ax1.collections:
        try:
            collection.set_sizes([42])
        except Exception:
            pass

    # 右侧条形图
    ax2 = ax1.twiny()
    feature_order = [t.get_text() for t in ax1.get_yticklabels()]
    ordered_importance = [np.abs(shap_df[f]).mean() for f in feature_order]

    cmap_bar = cm.get_cmap("plasma", len(feature_order))
    colors = cmap_bar(np.linspace(0.15, 0.90, len(feature_order)))

    ax2.barh(
        range(len(feature_order)),
        ordered_importance,
        height=0.68,
        color=colors,
        alpha=0.35,
        edgecolor="black",
        linewidth=1.8
    )

    ax1.set_xlabel("SHAP Value", fontweight='bold', fontsize=16, color='black')
    ax2.set_xlabel("Mean |SHAP Value|", fontweight='bold', fontsize=16, color='black')
    ax2.xaxis.set_label_position('top')
    ax2.xaxis.tick_top()
    ax1.set_ylabel("Features", fontweight='bold', fontsize=16, color='black')

    # 标题格式按你给的那个来
    ax1.set_title(title_text, fontweight='bold', fontsize=18, color='black', pad=12)

    ax1.grid(True, axis='x', linestyle='--', alpha=0.3, linewidth=1.4)
    ax2.grid(True, axis='x', linestyle='--', alpha=0.3, linewidth=1.4)
    ax1.axvline(x=0, color='black', linestyle='-', linewidth=2.0, alpha=0.75)

    for spine in ax1.spines.values():
        spine.set_linewidth(2.0)
        spine.set_color("black")
    for spine in ax2.spines.values():
        spine.set_linewidth(2.0)
        spine.set_color("black")

    for tick in ax1.get_xticklabels() + ax1.get_yticklabels() + ax2.get_xticklabels():
        tick.set_color("black")
        tick.set_fontweight("bold")

    save_png_pdf(output_path_no_suffix)


# ======================
# 读取数据
# ======================
required_cols = FEATURE_COLS + TARGETS
df = read_excel_auto(DATA_PATH, sheet_name=SHEET_NAME, required_cols=required_cols)

keep_cols = [c for c in ID_COLS if c in df.columns] + FEATURE_COLS + TARGETS
df = df[keep_cols].copy()

for c in FEATURE_COLS + TARGETS:
    df[c] = pd.to_numeric(df[c], errors="coerce")


# ======================
# 循环不同目标变量
# ======================
all_metrics = []

excel_output_path = OUTPUT_DIR / "ML_SHAP_Multi_Target_Result.xlsx"
with pd.ExcelWriter(excel_output_path, engine="openpyxl") as writer:

    for target_col in TARGETS:
        print("=" * 70)
        print(f"正在处理目标变量: {target_col}")

        sub_df = df[[c for c in ID_COLS if c in df.columns] + FEATURE_COLS + [target_col]].copy()
        sub_df = sub_df.dropna(subset=FEATURE_COLS + [target_col]).reset_index(drop=True)

        if sub_df.empty:
            print(f"[Skip] {target_col} 没有可用数据。")
            continue

        X = sub_df[FEATURE_COLS].copy()
        y = sub_df[target_col].copy()

        # 划分训练/测试集
        X_train, X_test, y_train, y_test = train_test_split(
            X, y,
            test_size=TEST_SIZE,
            random_state=RANDOM_STATE
        )

        # 建模
        model = CatBoostXGBoostHybridRegressor(
            alpha=FIXED_PARAMS["alpha"],
            cat_depth=FIXED_PARAMS["cat_depth"],
            cat_iterations=FIXED_PARAMS["cat_iterations"],
            cat_l2_leaf_reg=FIXED_PARAMS["cat_l2_leaf_reg"],
            cat_learning_rate=FIXED_PARAMS["cat_learning_rate"],
            xgb_colsample_bytree=FIXED_PARAMS["xgb_colsample_bytree"],
            xgb_learning_rate=FIXED_PARAMS["xgb_learning_rate"],
            xgb_max_depth=FIXED_PARAMS["xgb_max_depth"],
            xgb_n_estimators=FIXED_PARAMS["xgb_n_estimators"],
            xgb_subsample=FIXED_PARAMS["xgb_subsample"],
            random_state=RANDOM_STATE
        )
        model.fit(X_train, y_train)

        # 评估
        y_train_pred = model.predict(X_train)
        y_test_pred = model.predict(X_test)
        y_all_pred = model.predict(X)

        metrics_df = pd.DataFrame([
            {
                "Target": target_col,
                "Dataset": "Train",
                "R2": r2_score(y_train, y_train_pred),
                "MAE": mean_absolute_error(y_train, y_train_pred),
                "RMSE": np.sqrt(mean_squared_error(y_train, y_train_pred)),
                "MAPE(%)": safe_mape(y_train, y_train_pred)
            },
            {
                "Target": target_col,
                "Dataset": "Test",
                "R2": r2_score(y_test, y_test_pred),
                "MAE": mean_absolute_error(y_test, y_test_pred),
                "RMSE": np.sqrt(mean_squared_error(y_test, y_test_pred)),
                "MAPE(%)": safe_mape(y_test, y_test_pred)
            },
            {
                "Target": target_col,
                "Dataset": "All",
                "R2": r2_score(y, y_all_pred),
                "MAE": mean_absolute_error(y, y_all_pred),
                "RMSE": np.sqrt(mean_squared_error(y, y_all_pred)),
                "MAPE(%)": safe_mape(y, y_all_pred)
            }
        ])

        all_metrics.append(metrics_df)

        # SHAP
        cat_explainer = shap.TreeExplainer(model.cat_model_)
        xgb_explainer = shap.TreeExplainer(model.xgb_model_)

        cat_shap_values = cat_explainer.shap_values(X)
        xgb_shap_values = xgb_explainer.shap_values(X)

        if isinstance(cat_shap_values, list):
            cat_shap_values = cat_shap_values[0]
        if isinstance(xgb_shap_values, list):
            xgb_shap_values = xgb_shap_values[0]

        shap_values = FIXED_PARAMS["alpha"] * cat_shap_values + (1.0 - FIXED_PARAMS["alpha"]) * xgb_shap_values

        shap_df = pd.DataFrame(
            shap_values,
            columns=X.columns,
            index=X.index
        )

        importance_df = pd.DataFrame({
            "Feature": X.columns,
            "MeanAbsSHAP": np.abs(shap_values).mean(axis=0)
        }).sort_values("MeanAbsSHAP", ascending=False).reset_index(drop=True)

        # 画图
        target_safe = sanitize_name(target_col)
        plot_shap_beeswarm_bar(
            shap_values_arr=shap_values,
            X_df=X,
            shap_df=shap_df,
            output_path_no_suffix=OUTPUT_DIR / f"SHAP_Beeswarm_Bar_{target_safe}",
            title_text=f"SHAP Summary ({target_col})"
        )

        # 导出到 Excel
        metrics_df.to_excel(writer, sheet_name=f"M_{target_safe}"[:31], index=False)
        importance_df.to_excel(writer, sheet_name=f"I_{target_safe}"[:31], index=False)
        shap_df.to_excel(writer, sheet_name=f"S_{target_safe}"[:31], index=False)

# 汇总指标
all_metrics_df = pd.concat(all_metrics, axis=0, ignore_index=True)
with pd.ExcelWriter(OUTPUT_DIR / "ML_SHAP_Multi_Target_Metrics.xlsx", engine="openpyxl") as writer:
    all_metrics_df.to_excel(writer, sheet_name="ALL_METRICS", index=False)

print("=" * 70)
print("多目标 CatBoost-XGBoost + SHAP 完成。")
print(f"输入文件: {Path(DATA_PATH).resolve()}")
print(f"输出目录: {OUTPUT_DIR.resolve()}")
print("目标变量:", TARGETS)
print("外生变量:", FEATURE_COLS)
print("输出内容：")
print("1. 每个目标变量对应的核心 SHAP 图（png/pdf）")
print("2. ML_SHAP_Multi_Target_Result.xlsx")
print("3. ML_SHAP_Multi_Target_Metrics.xlsx")
print("=" * 70)
print("\n汇总指标：")
print(all_metrics_df)