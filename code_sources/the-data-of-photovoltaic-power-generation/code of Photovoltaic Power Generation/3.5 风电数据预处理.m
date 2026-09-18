% Data for the years and wind electricity production
years = (2010:2023)';
wind_electricity = [446.2; 703.3; 959.8; 1412; 1599.8; 1857.7; 2370.7; 2972.3; 3659.7; ...
    4060.3; 4664.7; 6561; NaN; NaN];

% Known data (excluding the NaN values for interpolation)
known_years = years(~isnan(wind_electricity));
known_wind_electricity = wind_electricity(~isnan(wind_electricity));

% Quadratic polynomial fit
p = polyfit(known_years, known_wind_electricity, 2);

% Use the polynomial to predict the values for 2022 and 2023
wind_electricity(13) = polyval(p, 2022);
wind_electricity(14) = polyval(p, 2023);

% Plotting the known data and the polynomial fit
figure;
hold on;
grid on;

plot(known_years, known_wind_electricity, 'o', 'DisplayName', 'Known Data');
plot(years, polyval(p, years), '-', 'DisplayName', 'Polynomial Fit');

xlabel('Year');
ylabel('Wind Electricity Production (100 million kWh)');
title('Wind Electricity Production Over Years with Polynomial Interpolation');
legend('Location', 'northwest');

% Print out the last five entries including the interpolated values for 2022 and 2023
disp('Last five entries with interpolated values:');
disp(table(years(end-4:end), wind_electricity(end-4:end)));
