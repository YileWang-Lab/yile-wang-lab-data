import pandas as pd
import numpy as np
from matplotlib import pyplot as plt
from scipy.interpolate import interp1d

# Since the actual data is not available as a CSV or any downloadable format, we will recreate the dataframe from the image provided.
# We will then interpolate the missing values for 2022 and 2023.

# Creating a dataframe based on the image data.
data = {
    "年份": list(range(2000, 2024)),
    "电力生产量(亿千瓦小时)": [
        13556, 14808, 16540, 19105.8, 22033.1, 25002.6, 28657.3, 32815.5, 34668.8,
        37146.5, 42071.6, 47130.2, 49875.5, 54316.4, 57944.6, 58145.7, 61331.6,
        66044.5, 71661.3, 75034.3, 77790.6, 85342.5, np.nan, np.nan  # 2022 and 2023 are NaNs
    ]
}

df = pd.DataFrame(data)

# Using interpolation to estimate the missing values for 2022 and 2023.
# Assuming the trend can be modelled with a polynomial function as it seems to be non-linear.
# We will use a quadratic polynomial which is the simplest form that allows for non-linear trends.

# Extracting known years and production values
known_years = df['年份'][:-2]
production_values = df['电力生产量(亿千瓦小时)'][:-2]

# Fitting a quadratic polynomial
coefficients = np.polyfit(known_years, production_values, 2)
polynomial = np.poly1d(coefficients)

# Predicting the values for 2022 and 2023
df.loc[df['年份'] == 2022, '电力生产量(亿千瓦小时)'] = polynomial(2022)
df.loc[df['年份'] == 2023, '电力生产量(亿千瓦小时)'] = polynomial(2023)

# Plotting the results to visualize the interpolation
plt.figure(figsize=(10, 5))
plt.plot(known_years, production_values, 'o', label='Known Data')
plt.plot(df['年份'], polynomial(df['年份']), '-', label='Polynomial Fit')
plt.xlabel('Year')
plt.ylabel('Electricity Production (100 million kWh)')
plt.title('Electricity Production Over Years with Polynomial Interpolation')
plt.legend()
plt.grid(True)
plt.show()

# Returning the updated dataframe with interpolated values.
df.tail()  # Show the last 5 entries, including interpolated values for 2022 and 2023
