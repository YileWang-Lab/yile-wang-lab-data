import pandas as pd
import numpy as np
from scipy.optimize import minimize

# 示例数据的年份范围
years = np.arange(2024, 2061)

# 生成模拟数据
np.random.seed(0)  # 确保结果可复现

# 装机容量增长率（假设每年随机在1%到5%之间）
capacity_growth_rate = 0.01 + np.random.rand(len(years)) * 0.04
initial_capacity = 100  # 假设2024年初始装机容量为100MW
cumulative_capacity = np.cumprod(np.ones_like(years) + capacity_growth_rate) * initial_capacity

# 发电效率（假设每年在15%到25%之间）
efficiency = 0.15 + np.random.rand(len(years)) * 0.10

# 太阳辐射量（假设在1500到2000 kWh/m²之间）
radiation = 1500 + np.random.rand(len(years)) * 500

# 有效发电小时数，假设为平均每天5小时，即年度1825小时
hours_per_year = 1825

# 目标函数：最大化总发电量
def objective(variables):
    # 变量是每年的装机容量
    capacity = variables
    total_energy = sum(capacity * efficiency * radiation * hours_per_year)
    return -total_energy  # 因为是最大化问题，所以返回负值

# 初始猜测
initial_guess = cumulative_capacity

# 约束条件（装机容量不得低于初始值，不得高于某个上限，这里假设为每年最大增加20%）
lower_bounds = cumulative_capacity
upper_bounds = cumulative_capacity * 1.2
bounds = [(low, high) for low, high in zip(lower_bounds, upper_bounds)]

# 使用优化算法求解
result = minimize(objective, initial_guess, bounds=bounds, method='SLSQP')

# 检查是否成功找到解
if result.success:
    optimized_capacity = result.x
    total_energy_generated = -result.fun
    print(f"总发电量: {total_energy_generated:.2f} kWh")
else:
    print("优化未成功")

# 结果数据
optimized_data = pd.DataFrame({
    'Year': years,
    'Optimized Capacity (MW)': optimized_capacity,
    'Efficiency': efficiency,
    'Radiation (kWh/m²)': radiation
})

optimized_data.head()  # 显示前几行数据

