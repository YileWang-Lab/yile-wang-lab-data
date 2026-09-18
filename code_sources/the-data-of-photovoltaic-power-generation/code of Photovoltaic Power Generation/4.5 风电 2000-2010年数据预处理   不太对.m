% Data for the years and wind electricity production
years = (2000:2023)';
wind_electricity = [NaN; NaN; NaN; NaN; NaN; NaN; NaN; NaN; NaN; NaN; ...
                    446.2; 703.3; 959.8; 1412; 1599.8; 1857.7; 2370.7; 2972.3; ...
                    3659.7; 4060.3; 4664.7; 6561; 6994.08; 8037.09];

% Known data (excluding the NaN values for extrapolation)
known_years = years(~isnan(wind_electricity));
known_wind_electricity = wind_electricity(~isnan(wind_electricity));

% Linear polynomial fit
p = polyfit(known_years, known_wind_electricity, 1);

% Use the polynomial to extrapolate the values for 2000-2009
extrapolated_values = polyval(p, years(1:10));

% Ensure the extrapolated values are non-negative
extrapolated_values(extrapolated_values < 0) = 0;

% Replace the NaN values with the extrapolated non-negative values for 2000-2009
wind_electricity(1:10) = extrapolated_values;

% Plotting the known data and the extrapolated line
figure;
hold on;
grid on;

plot(known_years, known_wind_electricity, 'o', 'DisplayName', 'Known Data');
plot(years, polyval(p, years), '-', 'DisplayName', 'Linear Extrapolation');

xlabel('Year');
ylabel('Wind Electricity Production (100 million kWh)');
title('Wind Electricity Production Over Years with Linear Extrapolation (Non-negative)');
legend('Location', 'northwest');

% Print out the first 15 entries including the extrapolated non-negative values for 2000-2010
disp('First 15 entries with extrapolated non-negative values for 2000-2010:');
disp(table(years(1:15), wind_electricity(1:15)));

