
% 定义数据
years = 2010:2020;
carbonEmissions = [56360.05184, 65193.34223, 67502.61337, 66749.3757, 64853.27604, 66074.80995, 68526.12467, 70451.55739, 71502.00286, 74096.33108, 72633.32425];
GDP = [41383.87, 45952.65, 50660.2, 55580.11, 60359.43, 65552, 70665.70683, 75752.20149, 80827.71193, 85556.13387, 88683.21463];
energyConsumption = [23539.31443, 26860.02581, 27999.21811, 28203.10427, 28170.50576, 29033.60807, 29947.97662, 30669.88646, 31373.12665, 32227.50539, 31437.99755];
renewableEnergy = [238.9790267, 248.2088158, 265.7958041, 271.9162235, 366.2173843, 326.0782482, 376.5041133, 496.0735116, 697.7401019, 857.4117663, 963.068886];

% 计算相关系数
correlationMatrix = corrcoef([carbonEmissions; GDP; energyConsumption; renewableEnergy]');

% 可视化
figure;
subplot(2,2,1);
plot(years, carbonEmissions);
title('Carbon Emissions over Years');
xlabel('Year');
ylabel('Carbon Emissions');

subplot(2,2,2);
plot(years, GDP);
title('GDP over Years');
xlabel('Year');
ylabel('GDP');

subplot(2,2,3);
plot(years, energyConsumption);
title('Energy Consumption over Years');
xlabel('Year');
ylabel('Energy Consumption');

subplot(2,2,4);
plot(years, renewableEnergy);
title('Renewable Energy Power over Years');
xlabel('Year');
ylabel('Renewable Energy Power');

% 显示相关系数
disp('Correlation Matrix:');
disp(correlationMatrix);
