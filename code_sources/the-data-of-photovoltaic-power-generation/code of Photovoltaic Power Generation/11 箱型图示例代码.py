import matplotlib.pyplot as plt
import numpy as np

# 示例数据
data = np.random.normal(0, 1, 100)

# 绘制箱型图
plt.boxplot(data)

# 添加标题
plt.title('Box Plot Example')

# 显示图表
plt.show()
