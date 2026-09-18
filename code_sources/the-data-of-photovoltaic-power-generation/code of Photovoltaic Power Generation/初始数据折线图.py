import pandas as pd
import matplotlib.pyplot as plt

# Creating a dataframe from the provided data
data = {
    "Year": list(range(2010, 2062)),
    "Carbon Emissions": [
        56360.05184, 65193.34223, 67502.61337, 66749.3757, 64853.27604,
        66074.80995, 68526.12467, 70451.55739, 71502.00286, 74096.33108,
        72633.32425, 78473.416, 76147.756, 77751.046, 74155.613,
        75245.457, 77784.454, 79947.171, 81753.207, 83222.159,
        84373.627, 85227.209, 85802.502, 86119.106, 86196.619,
        86054.638, 85712.763, 85190.592, 84507.722, 83683.753,
        82738.283, 81690.91, 80561.233, 79368.849, 78133.357,
        76874.356, 75611.444, 74364.219, 73152.279, 71995.224,
        70912.65, 69924.157, 69049.344, 68307.807, 67719.146,
        67302.959, 67078.84462, 66974.95138, 66731.62992, 66415.67403,
        65589.38462, 65496.63771
    ]
}

df = pd.DataFrame(data)

# Plotting the line chart
plt.figure(figsize=(14, 7))
plt.plot(df["Year"], df["Carbon Emissions"], marker='o')
plt.title("Carbon Emissions from 2010 to 2061")
plt.xlabel("Year")
plt.ylabel("Carbon Emissions")
plt.grid(True)
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('C:\\Users\\24404\\Desktop\\carbon_emissions.png')

plt.show()
