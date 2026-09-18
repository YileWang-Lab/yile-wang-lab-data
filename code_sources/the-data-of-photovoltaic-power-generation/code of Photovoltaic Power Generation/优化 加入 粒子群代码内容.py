# Importing necessary libraries
import pandas as pd
import numpy as np
from pyswarm import pso

# Example data range
years = np.arange(2024, 2061)
num_regions = 3  # Number of regions

# Economic factors
installation_cost_per_mw = 1000  # Installation cost assumption
maintenance_cost_per_mw = 50     # Annual maintenance cost
government_subsidy = 200         # Government subsidy per MW

# Technological progress
efficiency_improvement_rate = 0.005  # Annual efficiency improvement rate

# Grid capacity limit
grid_capacity_limit = 5000  # Total grid capacity limit in MW

# Simulated data generation
np.random.seed(0)  # Ensuring reproducibility

# Capacity growth rates for each region
capacity_growth_rates = 0.01 + np.random.rand(len(years), num_regions) * 0.04
initial_capacities = 100 * np.ones(num_regions)  # Initial capacities for each region
cumulative_capacities = np.cumprod(1 + capacity_growth_rates, axis=0) * initial_capacities

# Efficiency assumption
efficiency = 0.15 + np.random.rand(len(years)) * 0.10

# Radiation levels for each region
radiations = 1500 + np.random.rand(len(years), num_regions) * 500

# Effective generation hours per year
hours_per_year = 1825

# Objective function for maximizing total revenue
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

# Setting PSO algorithm parameters
lb = cumulative_capacities.flatten()  # Lower bound
ub = np.minimum((cumulative_capacities * 1.2).flatten(), grid_capacity_limit)  # Upper bound
swarmsize = 100  # Number of particles
maxiter = 100   # Maximum number of iterations

# Optimization using PSO
optimized_capacity_pso, total_revenue_pso = pso(objective, lb, ub, swarmsize=swarmsize, maxiter=maxiter)

# Processing results
optimized_capacity_pso = optimized_capacity_pso.reshape((len(years), num_regions))
print(f"Total revenue with PSO: {total_revenue_pso:.2f}")

# Results data
optimized_data_pso = pd.DataFrame({
    'Year': np.tile(years, num_regions),
    'Region': np.repeat(np.arange(1, num_regions + 1), len(years)),
    'Optimized Capacity (MW)': optimized_capacity_pso.flatten()
})

optimized_data_pso.head()  # Displaying the first few rows of data

