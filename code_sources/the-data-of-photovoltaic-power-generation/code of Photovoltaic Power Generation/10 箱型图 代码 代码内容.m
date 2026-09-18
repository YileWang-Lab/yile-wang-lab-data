% Assume your data is stored in a matrix named 'data'
% Here we'll perform min-max normalization

% Calculate the minimum and maximum for each column
minData = min(data, [], 1);
maxData = max(data, [], 1);

% Normalize the data to the [0, 1] range
normalizedData = (data - minData) ./ (maxData - minData);

% Now plot the boxplot of the normalized data
boxplot(normalizedData, 'Whisker', 1.5);

% Add grid lines
grid on;

% Set the line width of the boxplot
set(findobj(gca,'type','line'),'linew',2);

% Set the marker and size for outliers
set(findobj(gca,'tag','Outlier'),'MarkerEdgeColor','r','MarkerSize',4);

% Optionally add labels and a title
xlabel('Column Number');
ylabel('Normalized Data Values');
title('Boxplot of 18 Columns of Normalized Data');

% Set the range of the axes
axis([0 19 ylim]);

% Set the axis ticks and labels
set(gca, 'XTick', 1:18, 'XTickLabel', arrayfun(@num2str, 1:18, 'UniformOutput', false));

