import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

# Loading the data from the uploaded image and manually inputting the values into a DataFrame
# The data represents electricity production (in 100 million kWh) and per capita GDP (in 2015 constant US dollars)

data = {
    "Electricity_Production": [
        13556, 14808, 16540, 19105.8, 22033.1, 25002.6, 28657.3, 32815.5,
        34668.8, 37146.5, 42071.6, 47130.2, 49875.5, 54316.4, 57944.6,
        58145.7, 61331.6, 66044.5, 71661.3, 75034.3, 77790.6, 85342.5,
        87752.5, 92070.6
    ],
    "Per_Capita_GDP": [
        2193.896866, 2359.572385, 2557.891612, 2797.176659, 3061.833173,
        3390.716159, 3800.765796, 4319.031398, 4711.643449, 5128.904128,
        5647.068727, 6152.696873, 6591.662494, 7056.423092, 7532.785301,
        8016.445595, 8516.528742, 9053.228725, 9619.209475, 10155.51088,
        10358.17, 11223.25535, 11560.24212, 11781.93762
    ]
}

df = pd.DataFrame(data)

# Sort the data
df_sorted = df.sort_values(by="Electricity_Production")

# Generate Q-Q plot
plt.figure(figsize=(8,8))
stats.probplot(df_sorted["Per_Capita_GDP"], dist="norm", plot=plt)
plt.title('Q-Q Plot of Per Capita GDP')
plt.xlabel('Theoretical Quantiles')
plt.ylabel('Ordered Values')
plt.grid(True)
plt.show()
