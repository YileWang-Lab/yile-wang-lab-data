% 打开中国的地图视图
figure;
worldmap('china');

% 设置地图的背景颜色
setm(gca, 'FFaceColor', [0.9 0.9 0.9]);

% 加载并展示海岸线
load coastlines;
geoshow(coastlat, coastlon, 'DisplayType', 'polygon', 'FaceColor', [0.68 0.85 0.90]);

% 中国大致的地理坐标范围
lat_range = [30, 40];
lon_range = [80, 120];

% 随机生成 10 个位置
num_points = 10;
rand_lats = lat_range(1) + (lat_range(2) - lat_range(1)) .* rand(num_points, 1);
rand_lons = lon_range(1) + (lon_range(2) - lon_range(1)) .* rand(num_points, 1);

% 在地图上展示这些随机位置
geoshow(rand_lats, rand_lons, 'DisplayType', 'point', 'Marker', 'o', 'MarkerEdgeColor', 'k', 'MarkerFaceColor', 'r', 'MarkerSize', 5);

% 增加网格线
setm(gca, 'Grid', 'on', 'GLineStyle', '-', 'Gcolor', [0.8 0.8 0.8], 'Galtitude', 0);

% 设置标题
title(' Locations in China', 'FontSize', 14, 'FontWeight', 'bold');

% 可以添加更多元素如比例尺、指北针等，根据个人喜好调整
