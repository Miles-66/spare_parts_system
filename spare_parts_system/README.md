# 子公司备件管理系统

## 项目概述

本项目旨在建立一个自动化、模块化的网页端数据看板，替代 Power BI，实现「文件夹驱动」的数据处理流程。

**核心技术栈**：Python + Streamlit（前端展示）、Pandas（数据处理）、Plotly/Echarts（交互图表）

**设计哲学**：**解耦（Decoupling）**。让数据读取、业务计算、界面展示三个环节互不干涉。

## 目录结构

```
spare_parts_system/
├── app.py                      # 主入口：负责侧边栏导航和模块调度
├── config.py                   # 配置中心：存放列名映射（Column Mapping）
├── core/                       # 核心引擎层
│   ├── __init__.py            # core模块初始化
│   ├── data_engine.py         # 负责多文件夹扫描、自动合并与去重
│   └── calculator.py          # 统一公式库（如满足率、预警逻辑）
├── modules/                    # 业务模块层（四大看板）
│   ├── sales.py               # 销售看板：热力图、满足率、主机厂分析
│   ├── inventory.py           # 库存看板：库存健康度、预警、清理建议
│   ├── procurement.py         # 采购看板：未交付金额、延期率、周期分析
│   └── logistics.py           # 物流看板：运费占比、在途状态、箱量预估
└── data_source/                # 原始数据源（Data Lake）
    ├── sales/                 # 存放销售明细、地址、服务水平等数据表
    ├── inventory/
    ├── procurement/
    └── logistics/
```

## 快速开始

### 环境要求

- Python 3.8+
- pandas
- streamlit
- openpyxl（用于读取Excel文件）

### 安装依赖

```bash
pip install pandas streamlit openpyxl
```

### 运行项目

```bash
streamlit run app.py
```

## 核心模块说明

### 1. 数据引擎（core/data_engine.py）

数据引擎负责从各模块的 data_source/ 子文件夹中读取原始数据，支持以下功能：

- **多文件夹扫描**：自动扫描指定目录下的所有支持格式文件
- **自动合并**：将多个数据文件合并为统一的数据框
- **智能去重**：基于关键列（如订单号、备件号）去除重复数据
- **缓存机制**：使用 Streamlit 的 @st.cache_data 装饰器，只有文件变动时才重新读取
- **防御性报错**：缺失文件时返回空DataFrame，并在界面上提示

#### 主要函数

```python
# 读取销售数据（带缓存）
df, info = load_sales_data_with_cache()

# 获取销售数据摘要
summary = get_sales_data_summary()

# 检查所有数据文件夹状态
status = check_data_folders()

# 强制重新加载销售数据（清除缓存）
df, info = reload_sales_data()
```

### 2. 配置中心（config.py）

所有列名映射集中管理，严禁硬编码。当 Excel 表头变动时，只需修改 config.py 中的映射定义即可。

#### 使用示例

```python
from config import SALES_COL_ORDER_ID, SALES_COL_PART_NO

# 正确做法：引用配置变量
df = df.rename(columns={'原始列名': SALES_COL_ORDER_ID})

# 错误做法：直接硬编码
# df['子公司备件订单']  # 禁止！
```

## 数据源要求

### 销售数据（data_source/sales/）

支持的列名映射：

| 标准列名 | 映射的原始列名示例 | 说明 |
|---------|-------------------|------|
| order_id | 子公司备件订单 | 订单编号 |
| part_no | 备件号 | 备件编号 |
| quantity | 数量 | 销售数量 |
| amount | 金额 | 销售金额 |
| customer | 客户名称 | 客户名称 |
| region | 区域 | 销售区域 |
| province | 省份 | 省份 |
| city | 城市 | 城市 |
| dealer | 经销商 | 经销商 |
| sales_date | 销售日期 | 销售日期 |
| oem | 主机厂 | 主机厂 |
| service_level | 服务水平 | 服务水平 |

### 支持的文件格式

- Excel 文件（.xlsx、.xls）
- CSV 文件（.csv，支持 UTF-8、GBK 编码）

## 开发守则

### 1. 配置驱动，严禁硬编码

**禁止**：在代码里直接写 `df['子公司备件订单']`

**必须**：在 config.py 定义变量 `COL_ORDER_ID = '子公司备件订单'`，代码中引用 `df[COL_ORDER_ID]`

### 2. 缓存优先机制

必须使用 Streamlit 的 `@st.cache_data` 装饰器处理数据加载函数。

### 3. 防御性报错

如果文件夹里缺少某张表，系统不能报错退出，而应在界面上提示具体缺失信息。

## 阶段性路线图

### 第一阶段（已完成）

- [x] 建立项目目录结构
- [x] 实现 core/data_engine.py
- [x] 实现 config.py 配置中心

### 第二阶段

- [ ] 建立 app.py 主入口
- [ ] 开发销售看板第一页（满足率与客户排行）
- [ ] 引入地址表，开发区域销售热力图与主机厂分布

### 第三阶段

- [ ] 开发库存看板
- [ ] 实现三色预警逻辑（红/黄/绿）

### 第四阶段

- [ ] 集成采购看板
- [ ] 集成物流看板
- [ ] 完成全系统闭环

## 许可证

MIT License
