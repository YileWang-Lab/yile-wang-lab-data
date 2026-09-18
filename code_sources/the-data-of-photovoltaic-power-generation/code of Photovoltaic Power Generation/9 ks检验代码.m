% 加载Excel文件中的数据
filename = 'C:\Users\24404\PycharmProjects\pythonProject1\工作簿4.xlsx'; % 你需要替换为实际的文件路径
data = xlsread(filename);

% 初始化结果向量
[numRows, numCols] = size(data);
pValues = zeros(1, numCols);
hypothesis = zeros(1, numCols);

% 对每一列数据执行Shapiro-Wilk正态性检验
for i = 1:numCols
    [h, pValue] = kstest(data(:, i));
    pValues(i) = pValue;
    hypothesis(i) = h;
end

% 输出结果
for i = 1:numCols
    fprintf('第 %d 列数据的Shapiro-Wilk检验p值为: %f\n', i, pValues(i));
    if hypothesis(i) == 0
        fprintf('第 %d 列数据未拒绝正态分布的原假设。\n', i);
    else
        fprintf('第 %d 列数据拒绝了正态分布的原假设。\n', i);
    end
end
