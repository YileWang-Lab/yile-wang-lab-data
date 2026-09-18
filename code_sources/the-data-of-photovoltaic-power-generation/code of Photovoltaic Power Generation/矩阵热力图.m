% 相关系数矩阵
correlationMatrix = [
    1.0000, 0.8720, 0.9728, 0.7744;
    0.8720, 1.0000, 0.9412, 0.9062;
    0.9728, 0.9412, 1.0000, 0.7940;
    0.7744, 0.9062, 0.7940, 1.0000
];

% 变量名
variables = {'Carbon Emissions', 'GDP', 'Energy Consumption', 'Renewable Energy'};

% 创建热力图
figure;
h = heatmap(variables, variables, correlationMatrix);

% 设置热力图属性
h.Title = 'Correlation Matrix';
h.XLabel = 'Variables';
h.YLabel = 'Variables';
h.ColorScaling = 'scaledcolumns';
h.Colormap = jet; % 使用 jet 颜色图
h.CellLabelFormat = '%.4f'; % 设置单元格标签的格式

% 显示图形
drawnow;
