import pandas as pd
import numpy as np
from matplotlib import pyplot as plt
from scipy.interpolate import interp1d

# For this dataset, since we have missing values for the years 2000-2009 and 2022-2023, we will focus on interpolating the missing values for 2022 and 2023 only.
# As before, we'll use a quadratic polynomial fit based on the available data from 2010 to 2021.

# Creating a dataframe for the new data based on the image provided.
data_wind = {
    "年份": list(range(2010, 2024)),
    "风电生产电力量(亿千瓦小时)": [
        446.2, 703.3, 959.8, 1412, 1599.8, 1857.7, 2370.7, 2972.3, 3659.7,
        4060.3, 4664.7, 6561, np.nan, np.nan  # 2022 and 2023 are NaNs
    ]
}

df_wind = pd.DataFrame(data_wind)

# Interpolating the missing values using a quadratic polynomial.
known_years_wind = df_wind['年份'][:-2]
wind_production_values = df_wind["风电生产电力量(亿千瓦小时)"][:-2]

# Fitting a quadratic polynomial
coefficients_wind = np.polyfit(known_years_wind, wind_production_values, 2)
polynomial_wind = np.poly1d(coefficients_wind)

# Predicting the values for 2022 and 2023
df_wind.loc[df_wind['年份'] == 2022, "风电生产电力量(亿千瓦小时)"] = polynomial_wind(2022)
df_wind.loc[df_wind['年份'] == 2023, "风电生产电力量(亿千瓦小时)"] = polynomial_wind(2023)

# Plotting the results to visualize the interpolation
plt.figure(figsize=(10, 5))
plt.plot(known_years_wind, wind_production_values, 'o', label='Known Data')
plt.plot(df_wind['年份'], polynomial_wind(df_wind['年份']), '-', label='Polynomial Fit')
plt.xlabel('Year')
plt.ylabel('Wind Electricity Production (100 million kWh)')
plt.title('Wind Electricity Production Over Years with Polynomial Interpolation')
plt.legend()
plt.grid(True)
plt.show()

# Returning the updated dataframe with interpolated values.
df_wind.tail()  # Show the last 5 entries, including interpolated values for 2022 and 2023
