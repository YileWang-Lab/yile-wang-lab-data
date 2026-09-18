import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np

# Creating the factor loading matrix
data = {
    "主成分1": [0.948, 0.789, 0.975, -0.652, -0.526, 0.978, 0.977, 0.666, 0.741, 0.96, 0.678],
    "主成分2": [-0.165, 0.052, -0.159, 0.706, 0.042, -0.057, -0.048, 0.734, 0.029, -0.139, 0.706],
    "主成分3": [0.173, 0.502, -0.028, 0.013, 0.821, 0.088, 0.087, 0.066, -0.587, 0.178, -0.061],
    "共同度（公因子方差）": [0.956, 0.877, 0.977, 0.924, 0.952, 0.967, 0.964, 0.986, 0.895, 0.973, 0.962]
}
index = ["Wind Speed", "Temperature (Celsius)", "Radiation", "Wind Direction", "Rainfall",
         "Temp Probe 1", "Temp Probe 2", "Active Energy Delivered/Received", "Active Power",
         "Max Wind Speed", "Pressure"]

df = pd.DataFrame(data, index=index)

# Plotting the heatmap
plt.figure(figsize=(10, 8))
sns.heatmap(df, annot=True, cmap='coolwarm', fmt=".2f")
plt.title("Factor Loading Matrix Heatmap")
plt.xlabel("Components")
plt.ylabel("Variables")
plt.show()
