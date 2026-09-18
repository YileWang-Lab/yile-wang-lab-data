clc;
clear;

%--------------------------------------------
% 设置数据文件路径
cd('C:\Users\15549\Desktop\CurvNetAttack-main\Other\区域韧性');

% 读取数据
X = xlsread('全国-中部-东部_数据汇总.xlsx','全国');

[m,n] = size(X);
min_val = min(min(X));
max_val = max(max(X));

%--------------------------------------------
% 年份设置
years = 2007:2024;

if n ~= length(years)
    error('数据列数与年份数量不一致，请检查Excel数据。');
end

%--------------------------------------------
% 核密度估计
x_vals = linspace(min_val, max_val, 100);
f = zeros(length(years), length(x_vals));

for i = 1:length(years)
    f(i, :) = ksdensity(X(:, i), x_vals);
end

%--------------------------------------------
% 创建网格
[x, y] = meshgrid(x_vals, years);

%--------------------------------------------
% 设置画布大小
figure('Position', [200, 200, 1000, 700]);

% 绘制三维曲面图
mesh(x, y, f);

% 坐标轴标签
ylabel('Years', 'FontName', 'Times New Roman', 'FontSize', 16, 'FontWeight', 'bold');
xlabel('Regional Resilience', 'FontName', 'Times New Roman', 'FontSize', 16, 'FontWeight', 'bold');
zlabel('Density', 'FontName', 'Times New Roman', 'FontSize', 16, 'FontWeight', 'bold');

% 标题和字体
title('National Region Resilience', 'FontName', 'Times New Roman', 'FontSize', 18, 'FontWeight', 'bold');
set(gca, 'FontName', 'Times New Roman', 'FontSize', 14, 'FontWeight', 'bold');

%--------------------------------------------
% 关键：y轴从2007开始，并且每两个显示一个
ylim([2007 2024]);
set(gca, 'YDir', 'normal');          % 保证从2007到2024正向显示
yticks(2007:2:2024);                % 每隔2年显示一个刻度
yticklabels(string(2007:2:2024));   % 显示标签