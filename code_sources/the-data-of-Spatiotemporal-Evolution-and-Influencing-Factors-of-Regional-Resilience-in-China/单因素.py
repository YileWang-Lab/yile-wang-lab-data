# -*- coding: utf-8 -*-
"""
CatBoost-XGBoost + SHAP
仅绘制前6个重要变量的SHAP依赖图
布局：2行3列
颜色：plasma
不显示颜色条标题
负号：使用数学专用负号
"""

import numpy as np
import pandas as pd
import shap
import matplotlib
import matplotlib.pyplot as plt

from scipy.signal import savgol_filter
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
from sklearn.base import BaseEstimator, RegressorMixin

from xgboost import XGBRegressor
from catboost import CatBoostRegressor
from matplotlib.lines import Line2D

matplotlib.use('TkAgg')

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
    'axes.titlesize': 18,
    'xtick.labelsize': 15,
    'ytick.labelsize': 15,
    'legend.fontsize': 12,
    'axes.linewidth': 2.0,
    'axes.edgecolor': 'black',
    'axes.unicode_minus': True,   # 关键：使用数学专用负号 U+2212
    'xtick.major.width': 2.0,
    'ytick.major.width': 2.0,
    'xtick.major.size': 7,
    'ytick.major.size': 7,
})

# ======================
# 配置区
# ======================
DATA_PATH = r'PANEL_ANALYSIS_DATA - 副本.xlsx'
SHEET_NAME = 0

# 如果画全国，就设为 None
# 如果画某一区域，例如中部，就改成 "中部"
ZONE_FILTER = None

TARGET_COLUMN = 'Spearman-CRITIC'

FEATURE_COLUMNS = [
    "URB", "GOV", "INNO", "EDU", "OPENPC",
    "FIN", "DIG", "PRI", "INC", "SOC"
]

ID_COLS = ["ADMINCODE", "REGION", "ZONE", "YEAR"]

TEST_SIZE = 0.3
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
    "xgb_subsample": 1.0
}

if ZONE_FILTER is None:
    OUTPUT_IMAGE_PATH = r'SHAP_TOP6_DEPENDENCE_NATIONAL.png'
    OUTPUT_PDF_PATH = r'SHAP_TOP6_DEPENDENCE_NATIONAL.pdf'
    OUTPUT_EXCEL_PATH = r'SHAP_TOP6_DEPENDENCE_NATIONAL.xlsx'
else:
    OUTPUT_IMAGE_PATH = rf'SHAP_TOP6_DEPENDENCE_{ZONE_FILTER}.png'
    OUTPUT_PDF_PATH = rf'SHAP_TOP6_DEPENDENCE_{ZONE_FILTER}.pdf'
    OUTPUT_EXCEL_PATH = rf'SHAP_TOP6_DEPENDENCE_{ZONE_FILTER}.xlsx'


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
# 工具函数
# ======================
def safe_mape(y_true, y_pred, eps=1e-8):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return np.mean(np.abs((y_true - y_pred) / np.maximum(np.abs(y_true), eps))) * 100


def find_knee_point(x_data, y_data, window_length=5, polyorder=2):
    x_data = np.asarray(x_data, dtype=float)
    y_data = np.asarray(y_data, dtype=float)

    if len(x_data) < window_length:
        return np.median(x_data)

    if window_length % 2 == 0:
        window_length += 1

    if polyorder >= window_length:
        polyorder = max(1, window_length - 1)

    sort_idx = np.argsort(x_data)
    sorted_x = x_data[sort_idx]
    sorted_y = y_data[sort_idx]

    y_second_deriv = savgol_filter(sorted_y, window_length, polyorder, deriv=2)
    knee_index = np.argmax(np.abs(y_second_deriv))
    return sorted_x[knee_index]


def read_excel_auto(path, sheet_name=0, required_cols=None):
    xls = pd.ExcelFile(path)

    try:
        df0 = pd.read_excel(path, sheet_name=sheet_name)
        if required_cols is None or all(c in df0.columns for c in required_cols):
            print(f"[INFO] Using sheet: {sheet_name}")
            return df0
    except Exception:
        pass

    for sh in xls.sheet_names:
        df_tmp = pd.read_excel(path, sheet_name=sh, nrows=5)
        if required_cols is None or all(c in df_tmp.columns for c in required_cols):
            print(f"[INFO] Auto-detected sheet: {sh}")
            return pd.read_excel(path, sheet_name=sh)

    raise ValueError(f"在文件 {path} 中未找到包含所需列的sheet。缺少列: {required_cols}")


# ======================
# 读取数据
# ======================
print("--> 正在加载数据...")

required_cols = FEATURE_COLUMNS + [TARGET_COLUMN]
if ZONE_FILTER is not None:
    required_cols += ["ZONE"]

df = read_excel_auto(DATA_PATH, sheet_name=SHEET_NAME, required_cols=required_cols)

if ZONE_FILTER is not None:
    df = df[df["ZONE"] == ZONE_FILTER].copy()

keep_cols = [c for c in ID_COLS if c in df.columns] + FEATURE_COLUMNS + [TARGET_COLUMN]
df = df[keep_cols].copy()

for col in FEATURE_COLUMNS + [TARGET_COLUMN]:
    df[col] = pd.to_numeric(df[col], errors='coerce')

df = df.dropna(subset=FEATURE_COLUMNS + [TARGET_COLUMN]).reset_index(drop=True)

if df.empty:
    raise ValueError("数据为空，请检查文件、sheet 或区域筛选条件。")

print(df.head())

X = df[FEATURE_COLUMNS].copy()
y = df[TARGET_COLUMN].copy()

# 训练集 / 测试集
X_train, X_test, y_train, y_test = train_test_split(
    X, y,
    test_size=TEST_SIZE,
    random_state=RANDOM_STATE
)

# ======================
# 建模
# ======================
print("--> 正在训练 CatBoost-XGBoost 融合模型...")

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

# 模型评估
y_train_pred = model.predict(X_train)
y_test_pred = model.predict(X_test)

metrics_df = pd.DataFrame([
    {
        "Dataset": "Train",
        "R2": r2_score(y_train, y_train_pred),
        "MAE": mean_absolute_error(y_train, y_train_pred),
        "RMSE": np.sqrt(mean_squared_error(y_train, y_train_pred)),
        "MAPE(%)": safe_mape(y_train, y_train_pred)
    },
    {
        "Dataset": "Test",
        "R2": r2_score(y_test, y_test_pred),
        "MAE": mean_absolute_error(y_test, y_test_pred),
        "RMSE": np.sqrt(mean_squared_error(y_test, y_test_pred)),
        "MAPE(%)": safe_mape(y_test, y_test_pred)
    }
])

print("--> 模型评估结果：")
print(metrics_df)

# ======================
# 计算 SHAP
# ======================
print("--> 正在计算 SHAP 值...")

cat_explainer = shap.TreeExplainer(model.cat_model_)
xgb_explainer = shap.TreeExplainer(model.xgb_model_)

cat_shap_values = cat_explainer.shap_values(X_test)
xgb_shap_values = xgb_explainer.shap_values(X_test)

if isinstance(cat_shap_values, list):
    cat_shap_values = cat_shap_values[0]
if isinstance(xgb_shap_values, list):
    xgb_shap_values = xgb_shap_values[0]

shap_values = FIXED_PARAMS["alpha"] * cat_shap_values + (1.0 - FIXED_PARAMS["alpha"]) * xgb_shap_values
shap_df = pd.DataFrame(shap_values, columns=X_test.columns, index=X_test.index)

# 前6个重要变量
importance_df = pd.DataFrame({
    "Feature": X_test.columns,
    "MeanAbsSHAP": np.abs(shap_values).mean(axis=0)
}).sort_values("MeanAbsSHAP", ascending=False).reset_index(drop=True)

top_6_features = importance_df["Feature"].head(6).tolist()

print("--> 前6个重要变量：")
print(top_6_features)

# ======================
# 绘图：2行3列 SHAP依赖图
# ======================
print("--> 正在绘制 2×3 SHAP 依赖图...")

fig, axes = plt.subplots(2, 3, figsize=(14, 8), dpi=300)
axes = axes.flatten()

cmap = plt.get_cmap("plasma")

for i, feature in enumerate(top_6_features):
    ax = axes[i]
    feature_idx = X_test.columns.get_loc(feature)

    x_data = X_test[feature].values
    y_data = shap_values[:, feature_idx]
    color_data = y_test.values

    scatter = ax.scatter(
        x_data,
        y_data,
        c=color_data,
        cmap=cmap,
        s=28,
        alpha=0.85
    )

    # 中位数与阈值
    median_val = np.median(x_data)
    threshold_val = find_knee_point(x_data, y_data)

    ax.axvline(median_val, color='black', linestyle='--', linewidth=1.2)
    ax.axvline(threshold_val, color='red', linestyle=':', linewidth=1.4)

    # 图例
    line_handles = [
        Line2D([0], [0], color='black', lw=1.2, linestyle='--', label=f'Median: {median_val:.2f}'),
        Line2D([0], [0], color='red', lw=1.4, linestyle=':', label=f'Thresholds: {threshold_val:.2f}')
    ]
    ax.legend(handles=line_handles, loc='best', frameon=True, fontsize=10)

    # 标签
    ax.set_xlabel(feature, fontsize=18, fontweight='bold')
    ax.set_ylabel("SHAP", fontsize=16, fontweight='bold')

    # 坐标轴样式
    ax.tick_params(axis='both', which='major', labelsize=15, width=2, length=7)
    for spine in ax.spines.values():
        spine.set_linewidth(2)
        spine.set_color("black")

    # 单独颜色条：不显示标题
    cbar = fig.colorbar(scatter, ax=ax, fraction=0.046, pad=0.02)
    cbar.outline.set_visible(False)
    cbar.ax.tick_params(labelsize=12, width=1.5, length=3)

# 如果不足6个，删除多余子图
for j in range(len(top_6_features), 6):
    fig.delaxes(axes[j])

plt.tight_layout()
plt.savefig(OUTPUT_IMAGE_PATH, dpi=300, bbox_inches='tight')
plt.savefig(OUTPUT_PDF_PATH, dpi=300, bbox_inches='tight')
plt.show()

print(f"--> 图像已保存到: {OUTPUT_IMAGE_PATH}")
print(f"--> PDF已保存到: {OUTPUT_PDF_PATH}")

# ======================
# 导出结果
# ======================
with pd.ExcelWriter(OUTPUT_EXCEL_PATH, engine="openpyxl") as writer:
    metrics_df.to_excel(writer, sheet_name="Model_Metrics", index=False)
    importance_df.to_excel(writer, sheet_name="Feature_Importance", index=False)
    shap_df.to_excel(writer, sheet_name="SHAP_Values", index=False)
    X_test.to_excel(writer, sheet_name="X_Test", index=False)
    y_test.to_frame(name=TARGET_COLUMN).to_excel(writer, sheet_name="Y_Test", index=False)

print(f"--> 结果表已保存到: {OUTPUT_EXCEL_PATH}")