import matplotlib.pyplot as plt
import numpy as np

# Assuming random data for illustration; replace this with your actual data.
np.random.seed(0)
data_sample = np.random.rand(10, 11)  # 10 regions and 11 variables

# Normalize the data
data_normalized = (data_sample - np.min(data_sample, axis=0)) / (np.max(data_sample, axis=0) - np.min(data_sample, axis=0))

# Plot settings
plt.figure(figsize=(14, 7))

# Assign a unique color to each variable using a colormap
colors = plt.cm.viridis(np.linspace(0, 1, data_normalized.shape[1]))

# Plot each variable with a unique color
for i in range(data_normalized.shape[1]):
    plt.plot(data_normalized[:, i], marker='o', color=colors[i], label=f'Variable {i+1}')

# Add legend, title, and labels
plt.legend()
plt.title('Normalized Data Comparison Across Regions')
plt.xlabel('Region Index')
plt.ylabel('Normalized Value')

# Show grid
plt.grid(True)

# Display the plot
plt.show()
