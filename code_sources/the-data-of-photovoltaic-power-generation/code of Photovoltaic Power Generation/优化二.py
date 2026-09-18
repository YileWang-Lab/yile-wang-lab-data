# Based on the further improvements suggested, here's the complete and updated Python code

import pandas as pd
import numpy as np
from scipy.optimize import minimize

# 示例数据的年份范围
years = np.arange(2024, 2061)

# 经济因素
installation_cost_per_mw = 1000  # 假设装机成本
maintenance_cost_per_mw = 50     # 年维护成本
government_subsidy = 200         # 每MW的政府补贴

# 技术进步
efficiency_improvement_rate = 0.005  # 每年效率提升率

# 电网容量限制
grid_capacity_limit = 5000  # 总电网容量限制（MW）

# 生成模拟数据
np.random.seed(0)  # 确保结果可复现

# 装机容量增长率（假设每年随机在1%到5%之间）
capacity_growth_rates = 0.01 + np.random.rand(len(years), num_regions) * 0.04
initial_capacities = 100 * np.ones(num_regions)  # 初始装机容量
cumulative_capacities = np.cumprod(1 + capacity_growth_rates, axis=0) * initial_capacities

# 发电效率（假设每年在15%到25%之间）
efficiency = 0.15 + np.random.rand(len(years)) * 0.10

# 太阳辐射量（假设在1500到2000 kWh/m²之间）
radiations = 1500 + np.random.rand(len(years), num_regions) * 500  # 不同地区的辐射量

# 有效发电小时数，假设为平均每天5小时，即年度1825小时
hours_per_year = 1825

# 目标函数：最大化总收益（总发电量减去成本）
def objective(variables):
    capacities = variables.reshape((len(years), num_regions))
    total_revenue = 0
    for year_idx, year in enumerate(years):
        yearly_capacity = capacities[year_idx, :]
        yearly_efficiency = efficiency[year_idx] * (1 + efficiency_improvement_rate) ** (year - 2024)
        yearly_energy = np.sum(yearly_capacity * yearly_efficiency * radiations[year_idx, :] * hours_per_year)
        yearly_cost = np.sum(yearly_capacity * (installation_cost_per_mw + maintenance_cost_per_mw)) - np.sum(yearly_capacity * government_subsidy)
        total_revenue += yearly_energy - yearly_cost
    return -total_revenue  # Negative for maximization

# 初始猜测和约束条件
initial_guess = cumulative_capacities.flatten()
lower_bounds = cumulative_capacities.flatten()
upper_bounds = np.minimum((cumulative_capacities * 1.2).flatten(), grid_capacity_limit)
bounds = [(low, high) for low, high in zip(lower_bounds, upper_bounds)]

# 使用优化算法求解
result = minimize(objective, initial_guess, bounds=bounds, method='SLSQP')

# 检查是否成功找到解
if result.success:
    optimized_capacity = result.x.reshape((len(years), num_regions))
    total_revenue = -result.fun
    print(f"Total revenue: {total_revenue:.2f}")
else:
    print("Optimization unsuccessful")

# 结果数据
optimized_data = pd.DataFrame({
    'Year': np.tile(years, num_regions),
    'Region': np.repeat(np.arange(1, num_regions + 1), len(years)),
    'Optimized Capacity (MW)': optimized_capacity.flatten()
})

optimized_data.head()  # 显示前几行数据

