import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.preprocessing import PolynomialFeatures

# Create a DataFrame from the provided data
data = {
    "Year": np.arange(2000, 2024),
    "Electricity_Production": [
        13556, 14808, 16540, 19105.8, 22033.1, 25002.6, 28657.3, 32815.5, 34668.8,
        37146.5, 42071.6, 47130.2, 49875.5, 54316.4, 57944.6, 58145.7, 61331.6,
        66044.5, 71661.3, 75034.3, 77790.6, 85342.5, 87752.5, 92070.6
    ]
}
df = pd.DataFrame(data)

# Preparing data for modeling
X = df['Year'].values.reshape(-1, 1)
y = df['Electricity_Production'].values

# Polynomial Regression Model
degree = 3  # Degree of polynomial
poly_reg = PolynomialFeatures(degree=degree)
X_poly = poly_reg.fit_transform(X)
pol_reg = LinearRegression()
pol_reg.fit(X_poly, y)

# Predicting future values (2024-2060)
future_years = np.arange(2024, 2061).reshape(-1, 1)
future_years_poly = poly_reg.transform(future_years)
predicted_production = pol_reg.predict(future_years_poly)

# Calculating the metrics
# For the available data
y_pred = pol_reg.predict(X_poly)
mape = np.mean(np.abs((y - y_pred) / y)) * 100
rmse = np.sqrt(mean_squared_error(y, y_pred))
r2 = r2_score(y, y_pred)

# Plotting
plt.figure(figsize=(10, 6))
plt.scatter(X, y, color='blue', label='Actual Data')
plt.plot(X, y_pred, color='red', label='Polynomial Regression Fit')
plt.plot(future_years, predicted_production, color='green', linestyle='--', label='Future Predictions')
plt.xlabel('Year')
plt.ylabel('Electricity Production (Billion kWh)')
plt.title('Electricity Production Prediction (2000-2060)')
plt.legend()
plt.grid(True)
plt.show()

(mape, rmse, r2), predicted_production[:5]  # Displaying first 5 predictions and metrics
