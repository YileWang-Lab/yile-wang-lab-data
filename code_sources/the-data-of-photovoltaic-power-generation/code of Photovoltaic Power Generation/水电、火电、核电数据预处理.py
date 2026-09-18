import pandas as pd
import numpy as np
from matplotlib import pyplot as plt
from scipy.interpolate import interp1d

# Since the data is similar to the previous dataset but with three variables instead of one, we can use the same polynomial fitting approach for each of the variables.

# Creating a dataframe for the new data based on the image provided.
data_multi = {
    "年份": list(range(2000, 2024)),
    "水电生产电力量(亿千瓦小时)": [
        2224.1, 2774.3, 2879.7, 2836.8, 3535.4, 3970.2, 4357.9, 4852.6, 5851.9,
        6156.4, 7221.7, 6989.5, 8721.1, 9202.9, 10728.8, 11302.7, 11840.5, 11978.7,
        12317.9, 13044.4, 13552.1, 13390, np.nan, np.nan  # 2022 and 2023 are NaNs
    ],
    "火电生产电力量(亿千瓦小时)": [
        11141.9, 11834.3, 13381.4, 15803.6, 17955.9, 20473.4, 23696, 27229.3, 27900.8,
        29827.8, 33319.3, 38337, 38928.1, 42470.1, 44001.1, 42841.9, 44370.7, 47546,
        50963.2, 52201.5, 53302.5, 58058.7, np.nan, np.nan
    ],
    "核电生产电力量(亿千瓦小时)": [
        167.4, 174.7, 251.3, 433.4, 504.7, 530.9, 548.4, 621.3, 683.9,
        701.3, 738.8, 863.5, 973.9, 1116.1, 1325.4, 1707.9, 2132.9, 2480.7,
        2943.6, 3483.5, 3662.5, 4075.2, np.nan, np.nan
    ]
}

df_multi = pd.DataFrame(data_multi)

# Interpolating each column separately using a quadratic polynomial.
for column in df_multi.columns[1:]:
    # Extracting known years and production values
    known_years = df_multi['年份'][:-2]
    production_values = df_multi[column][:-2]

    # Fitting a quadratic polynomial
    coefficients = np.polyfit(known_years, production_values, 2)
    polynomial = np.poly1d(coefficients)

    # Predicting the values for 2022 and 2023
    df_multi.loc[df_multi['年份'] == 2022, column] = polynomial(2022)
    df_multi.loc[df_multi['年份'] == 2023, column] = polynomial(2023)

# Plotting the results to visualize the interpolation for each type of electricity production
plt.figure(figsize=(15, 5))

for index, column in enumerate(df_multi.columns[1:], 1):
    plt.subplot(1, 3, index)
    plt.plot(known_years, df_multi[column][:-2], 'o', label=f'Known Data for {column}')
    plt.plot(df_multi['年份'], polynomial(df_multi['年份']), '-', label=f'Polynomial Fit for {column}')
    plt.xlabel('Year')
    plt.ylabel(column)
    plt.title(f'{column} Over Years')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()

plt.show()

# Returning the updated dataframe with interpolated values.
df_multi.tail()  # Show the last 5 entries, including interpolated values for 2022 and 2023
