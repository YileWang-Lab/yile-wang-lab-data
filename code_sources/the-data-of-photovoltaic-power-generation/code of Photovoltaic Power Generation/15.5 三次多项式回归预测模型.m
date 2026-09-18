% 数据准备
years = (2000:2023)';
electricity_production = [13556, 14808, 16540, 19105.8, 22033.1, 25002.6, 28657.3, 32815.5, 34668.8, ...
    37146.5, 42071.6, 47130.2, 49875.5, 54316.4, 57944.6, 58145.7, 61331.6, 66044.5, 71661.3, 75034.3, ...
    77790.6, 85342.5, 87752.5, 92070.6]';

% 三次多项式回归模型
p = polyfit(years, electricity_production, 3);

% 预测未来的电力生产量 (2024-2060)
future_years = (2024:2060)';
predicted_production = polyval(p, future_years);

% 计算性能指标
y_pred = polyval(p, years);
mape = mean(abs((electricity_production - y_pred) ./ electricity_production)) * 100;
rmse = sqrt(mean((electricity_production - y_pred).^2));
r2 = 1 - sum((electricity_production - y_pred).^2) / sum((electricity_production - mean(electricity_production)).^2);

% 绘制原始数据和预测数据
figure;
hold on;
plot(years, electricity_production, 'bo-', 'LineWidth', 1.5);
plot(future_years, predicted_production, 'r*-', 'LineWidth', 1.5);
xlabel('Year');
ylabel('Electricity Production');
title('Electricity Production and Prediction');
legend('Actual Production', 'Predicted Production');
grid on;
hold off;

% 展示性能指标
figure;
sgtitle('Performance Metrics');
subplot(3,1,1);
bar(1, mape);
ylabel('MAPE (%)');
xlim([0 2]);
title('Mean Absolute Percentage Error');

subplot(3,1,2);
bar(1, rmse);
ylabel('RMSE');
xlim([0 2]);
title('Root Mean Square Error');

subplot(3,1,3);
bar(1, r2);
ylabel('R^2');
xlim([0 2]);
title('Coefficient of Determination');

% 调整子图间距
set(gcf, 'Position', [100, 100, 500, 700]);
