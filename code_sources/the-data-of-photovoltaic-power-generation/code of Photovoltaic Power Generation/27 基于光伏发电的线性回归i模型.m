
% 假设你有以下数据：

% 碳排放量
Carbon_Emissions = [56360.05, 65193.34, 67502.61, 66749.38, 64853.28, 66074.81, ...
                    68526.12, 70451.56, 71502, 74096.33, 72633.32];

% GDP
GDP = [41383.87, 45952.65, 50660.2, 55580.11, 60359.43, 65552, 70665.71, ...
       75752.2, 80827.71, 85556.13, 88683.21];

% 能源消费量
Energy_Consumption = [23539.31, 26860.03, 27999.22, 28203.1, 28170.51, 29033.61, ...
                      29947.98, 30669.89, 31373.13, 32227.51, 31437.99];

% 新能源电力
Renewable_Energy = [238.98, 248.21, 265.8, 271.92, 366.22, 326.08, 376.5, ...
                    496.07, 697.74, 857.41, 963.07];

% 创建一个table，将所有数据列放入其中
tbl = table(Carbon_Emissions', GDP', Energy_Consumption', Renewable_Energy',...
            'VariableNames', {'Carbon_Emissions', 'GDP', 'Energy_Consumption', 'Renewable_Energy'});

% 使用fitlm函数拟合多元线性回归模型
model = fitlm(tbl, 'Carbon_Emissions ~ GDP + Energy_Consumption + Renewable_Energy')

% 显示模型摘要
disp(model)
