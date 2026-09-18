import pandas as pd
import numpy as np
from matplotlib import pyplot as plt
from scipy.interpolate import interp1d
# For extrapolating data before 2010, we will use the same polynomial fitting approach,
# but we'll extrapolate instead of interpolate.

# Create a dataframe for the wind data including extrapolated values for 2022 and 2023
data_wind_full = {
    "年份": list(range(2000, 2024)),
    "风电生产电力量(亿千瓦小时)": [np.nan] * 10 + [
        446.2, 703.3, 959.8, 1412, 1599.8, 1857.7, 2370.7, 2972.3, 3659.7,
        4060.3, 4664.7, 6561, 6994.08, 8037.09
    ]
}

df_wind_full = pd.DataFrame(data_wind_full)

# Known data (excluding the NaN values for extrapolation)
known_years_full = df_wind_full['年份'][10:]  # from 2010 onwards
known_wind_production_full = df_wind_full["风电生产电力量(亿千瓦小时)"][10:]

# Fitting a polynomial
# We choose a polynomial of degree 3 for a better fit over a longer range.
coefficients_wind_full = np.polyfit(known_years_full, known_wind_production_full, 3)
polynomial_wind_full = np.poly1d(coefficients_wind_full)

# Extrapolating the values for 2000-2009 using the polynomial
for year in range(2000, 2010):
    df_wind_full.loc[df_wind_full['年份'] == year, "风电生产电力量(亿千瓦小时)"] = polynomial_wind_full(year)

# Plotting the results to visualize the extrapolation
plt.figure(figsize=(10, 5))
plt.plot(known_years_full, known_wind_production_full, 'o', label='Known Data')
plt.plot(df_wind_full['年份'], polynomial_wind_full(df_wind_full['年份']), '-', label='Polynomial Extrapolation')
plt.xlabel('Year')
plt.ylabel('Wind Electricity Production (100 million kWh)')
plt.title('Wind Electricity Production Over Years with Polynomial Extrapolation')
plt.legend()
plt.grid(True)
plt.show()

# Returning the updated dataframe with extrapolated values.
df_wind_full.head(15)  # Show the first 15 entries, including extrapolated values for 2000-2009
