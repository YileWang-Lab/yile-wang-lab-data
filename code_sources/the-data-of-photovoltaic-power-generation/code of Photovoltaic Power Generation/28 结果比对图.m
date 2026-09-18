% Assuming you have the data in a CSV file named 'carbon_data.csv'
tbl = readtable('data.xlsx');

% Extracting the data
years = tbl.Year;
carbonWithNewEnergy = tbl.WithNewRenewableEnergyPower;
carbonWithoutNewEnergy = tbl.WithoutNewRenewableEnergyPower;

% Plotting the data
figure;
plot(years, carbonWithNewEnergy, 'b-o', 'LineWidth', 1.5);
hold on;
plot(years, carbonWithoutNewEnergy, 'r--*', 'LineWidth', 1.5);
hold off;

% Beautifying the plot
xlabel('Year', 'FontSize', 12, 'FontWeight', 'bold');
ylabel('Carbon Emission (kt)', 'FontSize', 12, 'FontWeight', 'bold');
title('Carbon Emission with and without New Renewable Energy Power', 'FontSize', 14, 'FontWeight', 'bold');
legend('With New Renewable Energy', 'Without New Renewable Energy', 'Location', 'northwest');
grid on;

% Fine-tuning figure properties
set(gcf, 'Color', 'w'); % Set figure background to white
set(gca, 'FontSize', 10, 'FontWeight', 'bold');

% Optionally, save the figure
saveas(gcf, 'CarbonEmissionComparison.png');
