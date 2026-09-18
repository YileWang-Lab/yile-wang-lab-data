import pandas as pd
import numpy as np

# 手动输入用户提供的数据
data = {
    '年份': [
        2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020,
        2021, 2022, 2023, 2024, 2025, 2056, 2057, 2058, 2059, 2060, 2061
    ],
    '碳排放量': [
        56360.05184, 65193.34223, 67502.61337, 66749.3757, 64853.27604,
        66074.80995, 68526.12467, 70451.55739, 71502.00286, 74096.33108,
        72633.32425, 78473.416, 76147.756, 77751.046, 74155.613, 75245.457,
        67078.84462, 66974.95138, 66731.62992, 66415.67403, 65589.38462,
        65496.63771
    ]
}

# 将数据转换为DataFrame
df = pd.DataFrame(data)

# 创建一个包含缺失年份的DataFrame
years_missing = pd.DataFrame({'年份': range(2026, 2056)})
# 将现有数据与缺失年份合并，以便进行插值
full_df = pd.concat([df, years_missing], ignore_index=True).sort_values('年份').reset_index(drop=True)

# 使用三次样条插值方法来插值缺失值
full_df['碳排放量'] = full_df['碳排放量'].interpolate(method='cubic')

# 获取插值后的数据
interpolated_values = full_df[(full_df['年份'] >= 2026) & (full_df['年份'] <= 2055)]
interpolated_values
