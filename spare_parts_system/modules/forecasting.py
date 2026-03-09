# -*- coding: utf-8 -*-
"""
需求预测模块 (Demand Forecasting)

基于历史销售数据，利用经典统计模型预测未来需求：
1. MA (移动平均)
2. WMA (加权移动平均)
3. ES (指数平滑)

提供回测准确性分析，帮助进行主动补货决策。
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from datetime import datetime
import math

# 从forecast_engine导入计算函数
from core.forecast_engine import calculate_ma, calculate_wma, calculate_es

from core.i18n import get_text, get_text_safe
from config import SALES_DATA_DIR


# ========== 多维时间窗口聚合函数 ==========
def aggregate_by_time_dimension(df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """
    按时间维度聚合数据（月度/季度/年度）
    
    Args:
        df: 包含 _year_month 列的DataFrame
        dimension: '月度', '季度', '年度'
    
    Returns:
        pd.DataFrame: 聚合后的DataFrame
    """
    if df.empty or "_year_month" not in df.columns:
        return df
    
    df = df.copy()
    
    # 转换为Period以便聚合
    df["_period"] = pd.to_datetime(df["_year_month"].astype(str))
    
    if dimension == "月度":
        # 不聚合
        df["_time_label"] = df["_year_month"].astype(str)
        return df
    
    elif dimension == "季度":
        # 按季度聚合
        df["_quarter"] = df["_period"].dt.to_period("Q").astype(str)
        agg_df = df.groupby("_quarter").agg({
            "_quantity": "sum",
            "_unit_price": "max",
        }).reset_index()
        agg_df["_time_label"] = agg_df["_quarter"].str.replace("-", "Q").replace({
            "Q1": "-Q1", "Q2": "-Q2", "Q3": "-Q3", "Q4": "-Q4"
        }, regex=True)
        # 简化季度标签
        agg_df["_time_label"] = agg_df["_quarter"].apply(lambda x: f"{x[:4]}-{x[5]}")
        return agg_df
    
    elif dimension == "年度":
        # 按年度聚合
        df["_year"] = df["_period"].dt.year
        agg_df = df.groupby("_year").agg({
            "_quantity": "sum",
            "_unit_price": "max",
        }).reset_index()
        agg_df["_time_label"] = agg_df["_year"].astype(str)
        return agg_df
    
    return df


def calculate_time_weighted_accuracy(df: pd.DataFrame, dimension: str) -> float:
    """
    计算时间维度加权准确率
    
    Args:
        df: 包含预测和实际值的DataFrame
        dimension: '月度', '季度', '年度'
    
    Returns:
        float: 准确率 (0-1)
    """
    if df.empty or "_quantity" not in df.columns:
        return 0.0
    
    # 如果是月度，直接返回平均准确率
    if dimension == "月度":
        if "_accuracy" in df.columns:
            return df["_accuracy"].mean()
        return 0.0
    
    # 季度/年度：计算货值加权准确率
    if "_suggested_amount" in df.columns and "_hist_avg" in df.columns:
        # 预测金额 vs 历史金额
        total_forecast = df["_suggested_amount"].sum()
        total_hist = (df["_hist_avg"] * df["_unit_price"]).sum()
        
        if total_hist > 0:
            # 货值加权准确率
            accuracy = 1 - abs(total_forecast - total_hist) / total_hist
            return max(0, min(1, accuracy))
    
    return 0.0


def load_order_data():
    """
    加载订单数据
    
    Returns:
        pd.DataFrame: 订单数据
    """
    from core.data_engine import DataEngine
    
    engine = DataEngine()
    sales_dir = Path(SALES_DATA_DIR)
    
    # 查找miles订单明细文件
    order_files = engine.get_files_by_keyword(sales_dir, "miles新可用的子公司备件订单明细")
    
    if not order_files:
        return pd.DataFrame()
    
    df = engine.read_data_file(order_files[0])
    # 跳过前3列元数据
    if len(df.columns) > 3:
        df = df.iloc[:, 3:].copy()
    
    return df


def preprocess_order_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    预处理订单数据，提取关键列并按月份汇总
    
    Args:
        df: 原始订单数据
    
    Returns:
        pd.DataFrame: 处理后的月度汇总数据
    """
    if df.empty:
        return pd.DataFrame()
    
    # 查找关键列
    part_no_col = None
    part_desc_col = None
    qty_col = None
    confirm_time_col = None
    price_col = None
    
    for col in df.columns:
        col_str = str(col)
        # 物料号
        if part_no_col is None and "物料号" in col_str and "描述" not in col_str:
            part_no_col = col
        # 物料描述
        if part_desc_col is None and "物料描述" in col_str:
            part_desc_col = col
        # 数量
        if qty_col is None and "数量" in col_str and "已发" not in col_str and "未发" not in col_str:
            qty_col = col
        # 确认时间（兼容复杂列名）
        if confirm_time_col is None and "确认时间" in col_str:
            confirm_time_col = col
        # 价格（单价）- 兼容"单价"和"价格"列名
        if price_col is None and ("单价" in col_str or ("价格" in col_str and "总价" not in col_str)):
            price_col = col
    
    if not all([part_no_col, qty_col, confirm_time_col]):
        return pd.DataFrame()
    
    # 转换日期
    df["_confirm_date"] = pd.to_datetime(df[confirm_time_col], errors="coerce")
    df = df[df["_confirm_date"].notna()].copy()
    
    # 提取年月
    df["_year_month"] = df["_confirm_date"].dt.to_period("M")
    
    # 转换数量为数值
    df["_qty"] = pd.to_numeric(df[qty_col], errors="coerce").fillna(0)
    
    # 转换单价（如果有）
    if price_col:
        df["_price"] = pd.to_numeric(df[price_col], errors="coerce").fillna(0)
    else:
        df["_price"] = 0
    
    # 按物料号和月份汇总
    agg_dict = {
        "_qty": "sum",
        "_price": "max"  # 取最高单价作为参考
    }
    if part_desc_col:
        agg_dict[part_desc_col] = "first"  # 取第一个物料描述
    
    monthly_df = df.groupby([part_no_col, "_year_month"]).agg(agg_dict).reset_index()
    
    # 重命名列
    rename_dict = {
        part_no_col: "_part_no",
        "_qty": "_quantity",
        "_price": "_unit_price"
    }
    if part_desc_col:
        rename_dict[part_desc_col] = "_part_desc"
    
    monthly_df = monthly_df.rename(columns=rename_dict)
    
    # 转换为金额
    monthly_df["_amount"] = monthly_df["_quantity"] * monthly_df["_unit_price"]
    
    # 转换为字符串格式的年月
    monthly_df["_year_month_str"] = monthly_df["_year_month"].astype(str)
    
    return monthly_df


def backtest_model(historical_series: pd.Series, window: int, 
                   wma_weight: float = 0.7, es_alpha: float = 0.3,
                   backtest_months: int = 3) -> dict:
    """
    回测模型，计算MAE和准确率
    
    Args:
        historical_series: 历史数据序列
        window: MA窗口大小
        wma_weight: WMA近期权重
        es_alpha: ES平滑系数
        backtest_months: 回测月数
    
    Returns:
        dict: 包含MAE和准确率的字典
    """
    if len(historical_series) < backtest_months + 2:
        return {
            "mae_ma": None,
            "mae_wma": None,
            "mae_es": None,
            "accuracy_ma": None,
            "accuracy_wma": None,
            "accuracy_es": None,
            "forecast_ma": None,
            "forecast_wma": None,
            "forecast_es": None,
        }
    
    # 分割训练集和测试集
    train = historical_series.iloc[:-backtest_months]
    test = historical_series.iloc[-backtest_months:]
    
    if len(train) < 2:
        return {
            "mae_ma": None,
            "mae_wma": None,
            "mae_es": None,
            "accuracy_ma": None,
            "accuracy_wma": None,
            "accuracy_es": None,
            "forecast_ma": None,
            "forecast_wma": None,
            "forecast_es": None,
        }
    
    # 计算MA预测
    ma_forecast = calculate_ma(train, window)
    
    # 计算WMA预测
    wma_forecast = calculate_wma(train, wma_weight)
    
    # 计算ES预测
    es_forecast = calculate_es(train, es_alpha)
    
    # 计算MAE
    mean_actual = test.mean()
    
    if mean_actual > 0:
        mae_ma = np.abs(test - ma_forecast).mean()
        mae_wma = np.abs(test - wma_forecast).mean()
        mae_es = np.abs(test - es_forecast).mean()
        
        accuracy_ma = max(0, 1 - mae_ma / mean_actual)
        accuracy_wma = max(0, 1 - mae_wma / mean_actual)
        accuracy_es = max(0, 1 - mae_es / mean_actual)
    else:
        mae_ma = mae_wma = mae_es = None
        accuracy_ma = accuracy_wma = accuracy_es = None
    
    # 计算下月预测（使用全部历史数据）
    forecast_ma = calculate_ma(historical_series, window)
    forecast_wma = calculate_wma(historical_series, wma_weight)
    forecast_es = calculate_es(historical_series, es_alpha)
    
    return {
        "mae_ma": mae_ma,
        "mae_wma": mae_wma,
        "mae_es": mae_es,
        "accuracy_ma": accuracy_ma,
        "accuracy_wma": accuracy_wma,
        "accuracy_es": accuracy_es,
        "forecast_ma": forecast_ma,
        "forecast_wma": forecast_wma,
        "forecast_es": forecast_es,
    }


def get_best_model(result: dict) -> tuple:
    """
    获取最优模型
    
    Args:
        result: 回测结果字典
    
    Returns:
        tuple: (模型名称, 准确率, 预测值)
    """
    models = [
        ("MA", result.get("accuracy_ma"), result.get("forecast_ma")),
        ("WMA", result.get("accuracy_wma"), result.get("forecast_wma")),
        ("ES", result.get("accuracy_es"), result.get("forecast_es")),
    ]
    
    # 过滤掉None值
    valid_models = [(name, acc, fcst) for name, acc, fcst in models if acc is not None]
    
    if not valid_models:
        return ("N/A", 0, 0)
    
    # 找最大值
    best = max(valid_models, key=lambda x: x[1])
    return best


def get_model_type(best_model: str) -> str:
    """
    判断模型类型
    
    Args:
        best_model: 最优模型名称
    
    Returns:
        str: "Stable" 或 "Trend"
    """
    if best_model == "MA":
        return "Stable"
    else:
        return "Trend"


def calculate_abc_class(results_df: pd.DataFrame) -> pd.DataFrame:
    """
    计算ABC分类（严格基于历史销售额）
    
    重要原则：
    - 严禁使用 _suggested_amount 或 _next_forecast 等预测值
    - 必须基于每个 SKU 的历史实际销售总额
    
    分类标准（帕累托法则 - 80/20法则）：
    - A类：累计销售额 <= 80% 的物料（约占总数15-20%类：累计销售额）
    - B 80%-95% 的物料
    - C类：累计销售额 > 95% 的物料
    
    Args:
        results_df: 包含物料历史数据的DataFrame
    
    Returns:
        pd.DataFrame: 添加了ABC分类的DataFrame
    """
    if results_df.empty:
        return results_df
    
    # ========== 关键修复：必须使用历史销售额 ==========
    # 严禁使用 _suggested_amount（预测值）
    # 使用 _quantity * _unit_price（历史销售额）
    if "_quantity" in results_df.columns and "_unit_price" in results_df.columns:
        results_df["_hist_amount"] = results_df["_quantity"] * results_df["_unit_price"]
    else:
        results_df["_hist_amount"] = 0
    
    # 按历史金额排序
    results_df = results_df.sort_values("_hist_amount", ascending=False).reset_index(drop=True)
    
    # 计算累计金额
    total_amount = results_df["_hist_amount"].sum()
    if total_amount == 0:
        results_df["_abc_class"] = "C"
        return results_df
    
    # 计算累计百分比
    results_df["_cumsum_amount"] = results_df["_hist_amount"].cumsum()
    results_df["_cumsum_pct"] = results_df["_cumsum_amount"] / total_amount
    
    # 分类（帕累托标准）
    def classify_abc(pct):
        if pct <= 0.80:  # 前80% -> A类
            return "A"
        elif pct <= 0.95:  # 80%-95% -> B类
            return "B"
        else:  # 后5% -> C类
            return "C"
    
    results_df["_abc_class"] = results_df["_cumsum_pct"].apply(classify_abc)
    
    # 删除临时列
    results_df = results_df.drop(columns=["_cumsum_amount", "_cumsum_pct", "_hist_amount"])
    
    return results_df


def calculate_xyz_class(monthly_df: pd.DataFrame) -> pd.DataFrame:
    """
    计算XYZ分类
    基于月销量波动率（标准差/均值）
    X类：波动率低（<0.3）- 稳定需求
    Y类：波动率中等（0.3-0.6）- 正常波动
    Z类：波动率高（>0.6）- 高波动
    
    Args:
        monthly_df: 月度汇总数据
    
    Returns:
        pd.DataFrame: 包含XYZ分类的DataFrame
    """
    if monthly_df.empty:
        return monthly_df
    
    # 按物料号计算波动率
    volatility_stats = monthly_df.groupby("_part_no").agg({
        "_quantity": ["mean", "std", "count"]
    }).reset_index()
    
    # 展平列名
    volatility_stats.columns = ["_part_no", "_mean_qty", "_std_qty", "_sales_count"]
    
    # 计算波动率（标准差/均值）
    volatility_stats["_volatility"] = volatility_stats["_std_qty"] / volatility_stats["_mean_qty"]
    volatility_stats["_volatility"] = volatility_stats["_volatility"].fillna(0)
    
    # 分类
    def classify_xyz(vol):
        if pd.isna(vol) or vol == 0:
            return "Z"  # 无销售记录或无波动视为Z
        elif vol < 0.3:
            return "X"
        elif vol < 0.6:
            return "Y"
        else:
            return "Z"
    
    volatility_stats["_xyz_class"] = volatility_stats["_volatility"].apply(classify_xyz)
    
    return volatility_stats[["_part_no", "_xyz_class", "_volatility", "_sales_count"]]


def render_forecasting():
    """
    渲染需求预测页面（异步预处理模式）
    
    核心特性：
    1. 后台计算 -> 前台读取快照
    2. 分级参数寻优 (A类+活跃件: Grid Search, C类+长尾件: 固定参数)
    3. 预测结果持久化到 .parquet
    """
    from core.forecast_engine import (
        load_forecast_cache, 
        save_forecast_cache, 
        get_cache_info,
        run_forecast,
        load_order_data,
        preprocess_order_data,
        calculate_abc_class,
        calculate_xyz_class,
    )
    
    st.title(get_text("forecasting.page_title"))
    st.markdown("---")
    
    # 获取语言
    curr_lang = st.session_state.get("lang", "ZH")
    
    # ========== 方法论文档（折叠展开） ==========
    with st.expander("📖 方法论说明 | Methodology", expanded=False):
        if curr_lang == "ZH":
            st.markdown("""
            ## 🔮 预测算法说明
            
            本模块使用三种经典统计预测模型：
            
            ### 1. 移动平均 (MA - Moving Average)
            **公式**: 
            $$MA_t = \\frac{1}{n} \\sum_{i=t-n+1}^{t} x_i$$
            - 使用最近 n 个月的平均值作为下期预测
            - 默认窗口 n = 3
            
            ### 2. 加权移动平均 (WMA - Weighted Moving Average)
            **公式**:
            $$WMA_t = \\frac{\\sum_{i=1}^{n} w_i \\cdot x_{t-i+1}}{\\sum_{i=1}^{n} w_i}$$
            - 近期数据权重更高: $w_1 < w_2 < ... < w_n$
            - 默认权重因子 = 0.7
            
            ### 3. 指数平滑 (ES - Exponential Smoothing)
            **公式**:
            $$F_{t+1} = \\alpha \\cdot x_t + (1-\\alpha) \\cdot F_t$$
            - $\\alpha$ 为平滑系数 (0 < $\\alpha$ < 1)
            - 默认 $\\alpha$ = 0.3
            
            ---
            
            ## 📊 ABC 分类 (基于历史销售额)
            
            **原理**: 帕累托法则 (80/20 法则)
            
            **公式**:
            - 按历史销售额降序排列
            - 累计占比 ≤ 80% → **A类** (核心物料，约15-20%数量)
            - 累计占比 80%-95% → **B类** (次要物料)
            - 累计占比 > 95% → **C类** (普通物料)
            
            **计算基准**: 严格基于历史实际销售额 (数量 × 单价)，**禁止使用预测值**
            
            ---
            
            ## 📈 XYZ 分类 (基于需求稳定性)
            
            **公式**:
            $$CV = \\frac{\\sigma}{\\mu}$$
            - $\\sigma$ = 月销量标准差
            - $\\mu$ = 月销量均值
            
            **分类标准**:
            - CV < 0.3 → **X类** (稳定需求)
            - 0.3 ≤ CV < 0.6 → **Y类** (正常波动)
            - CV ≥ 0.6 → **Z类** (高波动/偶发)
            
            ---
            
            ## 🎯 准确率计算
            
            **月度准确率**:
            $$Accuracy = 1 - \\frac{MAE}{\\bar{x}_{backtest}}$$
            - $MAE$ = 回测期平均绝对误差
            - $\\bar{x}_{backtest}$ = 回测期实际销量均值
            
            **季度/年度货值加权准确率**:
            $$Accuracy = 1 - \\frac{|\\sum Forecast - \\sum Actual|}{\\sum Actual}$$
            - 按货值 (数量 × 单价) 聚合后计算
            - 正负偏差会相互抵消，因此通常高于月度准确率
            
            ---
            
            ## ⚙️ 参数寻优策略
            
            **分级寻优规则**:
            | 物料类别 | 策略 | 说明 |
            |---------|------|------|
            | A类 + X类 | Grid Search | 执行参数网格搜索寻优 |
            | B/C类 + Y/Z类 | 固定参数 | 使用经验参数 (MA=3, WMA=0.7, ES=0.3) |
            
            **目的**: 让核心物料获得更精准的预测参数
            
            ---
            
            ## 📉 BIAS 预测偏差
            
            **公式**:
            $$Bias\\% = \\frac{Forecast - \\bar{x}_{hist}}{\\bar{x}_{hist}} \\times 100\\%$$
            
            - **正值 (Over)**: 预测偏高 🔶
            - **负值 (Under)**: 预测偏低 🔷
            
            ---
            
            ## 📅 多维时间窗口
            
            | 维度 | 说明 | 业务意义 |
            |------|------|----------|
            | 月度 | 原始数据 | 短期波动，干扰较多 |
            | 季度 | 按季度聚合 | 反映中长期趋势 |
            | 年度 | 按年度聚合 | 反映长期稳健性 |
            
            **注意**: 季度/年度视图可平滑随机波动，展示补货计划的整体稳健性
            """)
        else:
            st.markdown("""
            ## 🔮 Forecasting Algorithms
            
            Three classic statistical models are used in this module:
            
            ### 1. Moving Average (MA)
            **Formula**: 
$$MA_t = \\frac{1}{n} \\sum_{i=t-n+1}^{t} x_i$$
            - Uses average of last n months as next period forecast
            - Default window n = 3
            
            ### 2. Weighted Moving Average (WMA)
            **Formula**:
            $$WMA_t = \\frac{\\sum_{i=1}^{n} w_i \\cdot x_{t-i+1}}{\\sum_{i=1}^{n} w_i}$$
            - Recent data has higher weight: $w_1 < w_2 < ... < w_n$
            - Default weight factor = 0.7
            
            ### 3. Exponential Smoothing (ES)
            **Formula**:
            $$F_{t+1} = \\alpha \\cdot x_t + (1-\\alpha) \\cdot F_t$$
            - $\\alpha$ is smoothing coefficient (0 < $\\alpha$ < 1)
            - Default $\\alpha$ = 0.3
            
            ---
            
            ## 📊 ABC Classification (Based on Historical Sales)
            
            **Principle**: Pareto Principle (80/20 Rule)
            
            **Formula**:
            - Sort by historical sales amount in descending order
            - Cumulative ≤ 80% → **Class A** (Core items, ~15-20% of SKUs)
            - Cumulative 80%-95% → **Class B** (Secondary items)
            - Cumulative > 95% → **Class C** (Regular items)
            
            **Calculation Base**: Strictly based on historical actual sales (Qty × Unit Price), **forecast values are prohibited**
            
            ---
            
            ## 📈 XYZ Classification (Based on Demand Stability)
            
            **Formula**:
            $$CV = \\frac{\\sigma}{\\mu}$$
            - $\\sigma$ = Monthly sales standard deviation
            - $\\mu$ = Monthly sales mean
            
            **Classification**:
            - CV < 0.3 → **Class X** (Stable demand)
            - 0.3 ≤ CV < 0.6 → **Class Y** (Normal fluctuation)
            - CV ≥ 0.6 → **Class Z** (High fluctuation/sporadic)
            
            ---
            
            ## 🎯 Accuracy Calculation
            
            **Monthly Accuracy**:
            $$Accuracy = 1 - \\frac{MAE}{\\bar{x}_{backtest}}$$
            - $MAE$ = Mean Absolute Error during backtest period
            - $\\bar{x}_{backtest}$ = Mean actual sales during backtest
            
            **Quarterly/Annual Value-Weighted Accuracy**:
            $$Accuracy = 1 - \\frac{|\\sum Forecast - \\sum Actual|}{\\sum Actual}$$
            - Aggregated by value (Qty × Unit Price)
            - Positive/negative errors offset each other, typically higher than monthly
            
            ---
            
            ## ⚙️ Parameter Optimization Strategy
            
            **Classification-based Strategy**:
            | Category | Strategy | Description |
            |----------|----------|-------------|
            | A + X Class | Grid Search | Execute parameter grid search |
            | B/C + Y/Z Class | Fixed Params | Use经验 parameters (MA=3, WMA=0.7, ES=0.3) |
            
            **Purpose**: Give core items more precise forecasting parameters
            
            ---
            
            ## 📉 BIAS (Forecast Bias)
            
            **Formula**:
            $$Bias\\% = \\frac{Forecast - \\bar{x}_{hist}}{\\bar{x}_{hist}} \\times 100\\%$$
            
            - **Positive (Over)**: Forecast too high 🔶
            - **Negative (Under)**: Forecast too low 🔷
            
            ---
            
            ## 📅 Multi-Dimension Time Window
            
            | Dimension | Description | Business Meaning |
            |-----------|-------------|------------------|
            | Monthly | Raw data | Short-term fluctuation, more noise |
            | Quarterly | Aggregated by quarter | Mid-long term trend |
            | Annual | Aggregated by year | Long-term stability |
            
            **Note**: Quarterly/Annual views smooth random fluctuations, showing overall replenishment plan stability
            """)
    
    # ========== 侧边栏：刷新预测 ==========
    st.sidebar.markdown("### 🔄 预测刷新")
    
    # 显示缓存信息
    cache_info = get_cache_info()
    if cache_info["exists"]:
        cache_msg = f"✅ 已缓存 ({cache_info['modified']})" if curr_lang == "ZH" else f"✅ Cached ({cache_info['modified']})"
        st.sidebar.success(cache_msg)
    else:
        no_cache_msg = "⚠️ 无缓存数据" if curr_lang == "ZH" else "⚠️ No cached data"
        st.sidebar.warning(no_cache_msg)
    
    # 回测周期参数（用于新计算）
    backtest_months = st.sidebar.slider(
        get_text("forecasting.backtest_period"),
        min_value=3,
        max_value=12,
        value=6,
        step=1,
        key="forecast_backtest_months"
    )
    
    # 刷新按钮
    refresh_label = "🔄 " + ("刷新预测" if curr_lang == "ZH" else "Refresh Forecast")
    refresh_forecast = st.sidebar.button(
        refresh_label,
        key="refresh_forecast_btn"
    )
    
    # ========== 加载预测结果 ==========
    if refresh_forecast:
        # 执行重新计算
        loading_msg = "🔄 正在执行大规模参数寻优，请稍候..." if curr_lang == "ZH" else "🔄 Running large-scale parameter optimization, please wait..."
        with st.spinner(loading_msg):
            # 显示进度条
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 加载数据
            raw_df = load_order_data()
            if raw_df.empty:
                st.warning(get_text("forecasting.no_data"))
                return
            
            monthly_df = preprocess_order_data(raw_df)
            if monthly_df.empty:
                st.warning(get_text("forecasting.no_data"))
                return
            
            # 计算ABC和XYZ分类
            xyz_data = calculate_xyz_class(monthly_df)
            
            # ========== 关键修复：ABC分类必须基于全量历史数据 ==========
            # 先计算每个SKU的历史总金额（不过滤任何物料）
            temp_results = []
            for part_no in monthly_df["_part_no"].unique():
                part_data = monthly_df[monthly_df["_part_no"] == part_no]
                sales_count = len(part_data)
                qty = part_data["_quantity"].sum()
                unit_price = part_data["_unit_price"].max()
                temp_results.append({
                    "_part_no": part_no,
                    "_quantity": qty,
                    "_sales_count": sales_count,
                    "_unit_price": unit_price,
                })
            
            temp_df = pd.DataFrame(temp_results)
            if not temp_df.empty:
                # 基于历史销售额计算ABC分类（不使用预测值）
                abc_data = calculate_abc_class(temp_df)
                xyz_data = xyz_data.merge(abc_data[["_part_no", "_abc_class"]], on="_part_no", how="left")
                xyz_data["_abc_class"] = xyz_data["_abc_class"].fillna("C")
            else:
                xyz_data["_abc_class"] = "C"
            
            # 执行预测
            results_df = run_forecast(
                monthly_df, 
                xyz_data, 
                backtest_months,
                progress_bar,
                status_text,
            )
            
            # 保存缓存
            if not results_df.empty:
                save_forecast_cache(results_df)
                st.success("✅ 预测完成并已缓存！")
            else:
                st.error("❌ 预测计算失败")
                return
    else:
        # 读取缓存
        results_df = load_forecast_cache()
        
        if results_df.empty:
            st.info("📊 首次使用，点击侧边栏「刷新预测」开始计算")
            return
        
        # 在缓存模式下也需要加载历史数据用于交互式分析
        with st.spinner("加载历史数据..."):
            raw_df = load_order_data()
            if not raw_df.empty:
                monthly_df = preprocess_order_data(raw_df)
            else:
                monthly_df = pd.DataFrame()
    
    if results_df.empty:
        st.warning(get_text("forecasting.no_data"))
        return
    
    # ========== KPI展示 ==========
    st.markdown(f"### {get_text('forecasting.kpi_title')}")
    
    # 使用suggested_amount替代forecast_amount
    total_suggested_amount = results_df["_suggested_amount"].sum()
    total_skus = len(results_df)
    
    # 计算三段式指标
    # 1. A类（核心件）准确率
    a_class_df = results_df[results_df["_abc_class"] == "A"]
    a_accuracy = a_class_df["_accuracy"].mean() if len(a_class_df) > 0 else None
    
    # 2. X类（稳定件）准确率
    x_class_df = results_df[results_df["_xyz_class"] == "X"]
    x_accuracy = x_class_df["_accuracy"].mean() if len(x_class_df) > 0 else None
    
    # 3. BIAS (预测偏差) - 行业标准公式: Bias % = (预测值 - 历史均值) / 历史均值
    # 正值(>0)表示Over-forecast(预测多了)，负值(<0)表示Under-forecast(预测少了)
    results_df["_bias"] = (results_df["_next_forecast"] - results_df["_hist_avg"]) / results_df["_hist_avg"].replace(0, np.nan)
    avg_bias_pct = results_df["_bias"].mean()
    
    # 判断是 Over 还是 Under
    is_over = avg_bias_pct > 0 if pd.notna(avg_bias_pct) else False
    bias_label = "Over-forecast" if is_over else "Under-forecast" if pd.notna(avg_bias_pct) else "N/A"
    bias_display = f"{avg_bias_pct*100:+.1f}%" if pd.notna(avg_bias_pct) else "N/A"
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        a_label = "A类(核心件)准确率" if st.session_state.get("lang") == "ZH" else "Class A Accuracy"
        st.metric(
            label=a_label,
            value=f"{a_accuracy*100:.1f}%" if a_accuracy else "N/A",
            delta=f"{len(a_class_df)} SKUs" if len(a_class_df) > 0 else None,
        )
    
    with col2:
        x_label = "X类(稳定件)准确率" if st.session_state.get("lang") == "ZH" else "Class X Accuracy"
        st.metric(
            label=x_label,
            value=f"{x_accuracy*100:.1f}%" if x_accuracy else "N/A",
            delta=f"{len(x_class_df)} SKUs" if len(x_class_df) > 0 else None,
        )
    
    with col3:
        bias_metric_label = "预测偏差(BIAS)" if st.session_state.get("lang") == "ZH" else "Forecast Bias"
        # 颜色标注: 橙色表示Over-forecast，蓝色表示Under-forecast
        if pd.notna(avg_bias_pct):
            if avg_bias_pct > 0:
                bias_color = "🔶"  # 橙色表示预测偏高
                bias_display_colored = f"{bias_color} {avg_bias_pct*100:+.1f}% (Over)"
            else:
                bias_color = "🔷"  # 蓝色表示预测偏低
                bias_display_colored = f"{bias_color} {avg_bias_pct*100:+.1f}% (Under)"
        else:
            bias_display_colored = "N/A"
        
        st.metric(
            label=bias_metric_label,
            value=bias_display_colored,
        )
    
    st.markdown("---")
    
    # ========== 多维时间窗口准确率分析 ==========
    st.markdown("### 📈 多维时间窗口准确率分析")
    
    # 时间维度选择器
    curr_lang = st.session_state.get("lang", "ZH")
    time_dim_options = ["月度", "季度", "年度"] if curr_lang == "ZH" else ["Monthly", "Quarterly", "Annual"]
    time_dimension = st.radio(
        "选择时间维度" if curr_lang == "ZH" else "Select Time Dimension",
        options=time_dim_options,
        horizontal=True,
        index=0,
        key="time_dimension_select"
    )
    
    # 业务提示
    if time_dimension != "月度" and time_dimension != "Monthly":
        st.info("💡 当前视图数据已平滑，重点反映补货计划的长期稳健性与总量偏差" if curr_lang == "ZH" else 
                "💡 Data is smoothed, reflecting the long-term stability of replenishment plans")
    
    # 计算对应维度的加权准确率
    if time_dimension in ["季度", "Quarterly"]:
        weighted_accuracy = calculate_time_weighted_accuracy(results_df, "季度")
        acc_label = "季度货值加权准确率" if curr_lang == "ZH" else "Quarterly Value-Weighted Accuracy"
    elif time_dimension in ["年度", "Annual"]:
        weighted_accuracy = calculate_time_weighted_accuracy(results_df, "年度")
        acc_label = "年度货值加权准确率" if curr_lang == "ZH" else "Annual Value-Weighted Accuracy"
    else:
        weighted_accuracy = results_df["_accuracy"].mean()
        acc_label = "加权准确率" if curr_lang == "ZH" else "Weighted Accuracy"
    
    # 显示加权准确率
    col_acc1, col_acc2 = st.columns(2)
    with col_acc1:
        st.metric(
            label=acc_label,
            value=f"{weighted_accuracy*100:.1f}%" if weighted_accuracy else "N/A",
        )
    with col_acc2:
        # 显示物料总数
        total_label = "总物料数" if curr_lang == "ZH" else "Total SKUs"
        st.metric(label=total_label, value=f"{len(results_df)}")
    
    # 如果选择了季度或年度，显示聚合后的趋势
    if time_dimension in ["季度", "年度", "Quarterly", "Annual"]:
        # 聚合历史数据
        agg_dimension = "季度" if time_dimension in ["季度", "Quarterly"] else "年度"
        if not monthly_df.empty:
            agg_data = aggregate_by_time_dimension(monthly_df, agg_dimension)
            
            if not agg_data.empty and "_time_label" in agg_data.columns:
                # 创建聚合趋势图
                fig_agg = go.Figure()
                
                fig_agg.add_trace(go.Bar(
                    x=agg_data["_time_label"],
                    y=agg_data["_quantity"],
                    name="销量" if curr_lang == "ZH" else "Quantity",
                    marker_color="#3498db"
                ))
                
                # 添加趋势线
                if len(agg_data) > 1:
                    z = np.polyfit(range(len(agg_data)), agg_data["_quantity"], 1)
                    p = np.poly1d(z)
                    fig_agg.add_trace(go.Scatter(
                        x=agg_data["_time_label"],
                        y=p(range(len(agg_data))),
                        mode="lines",
                        name="趋势" if curr_lang == "ZH" else "Trend",
                        line=dict(color="#e74c3c", width=2, dash="dash")
                    ))
                
                fig_agg.update_layout(
                    title=f"{agg_dimension}销量趋势" if curr_lang == "ZH" else f"{agg_dimension} Quantity Trend",
                    xaxis_title="时间" if curr_lang == "ZH" else "Time",
                    yaxis_title="销量" if curr_lang == "ZH" else "Quantity",
                    hovermode="x unified"
                )
                
                st.plotly_chart(fig_agg, use_container_width=True)
    
    st.markdown("---")
    
    # ========== 交互式物料预测分析器 ==========
    st.markdown("### 🔍 交互式物料预测分析器")
    
    # 翻译函数（简化版）
    def ft(key, default=None):
        try:
            return get_text(key)
        except:
            return default or key
    
    # 搜索组件：物料号选择
    all_parts = sorted(results_df["_part_no"].unique().tolist())
    
    # 创建物料号选项列表（包含物料描述）
    part_options = []
    for part_no in all_parts:
        part_row = results_df[results_df["_part_no"] == part_no]
        if "_part_desc" in part_row.columns and pd.notna(part_row["_part_desc"].iloc[0]):
            part_desc = str(part_row["_part_desc"].iloc[0])[:30]
            part_options.append(f"{part_no} - {part_desc}")
        else:
            part_options.append(part_no)
    
    # 用户选择物料
    selected_option = st.selectbox(
        "选择物料号" if st.session_state.get("lang") == "ZH" else "Select Part No",
        options=part_options,
        index=0
    )
    
    # 提取物料号
    selected_part_no = selected_option.split(" - ")[0] if " - " in selected_option else selected_option
    
    # 获取该物料的历史数据
    part_monthly_data = monthly_df[monthly_df["_part_no"] == selected_part_no].sort_values("_year_month")
    
    if len(part_monthly_data) < 3:
        st.warning("⚠️ 数据不足以生成趋势预测，建议参考安全库存逻辑" if st.session_state.get("lang") == "ZH" else "⚠️ Insufficient data for trend forecast")
    else:
        # 获取物料描述
        part_desc = ""
        if "_part_desc" in part_monthly_data.columns:
            part_desc = str(part_monthly_data["_part_desc"].iloc[0]) if pd.notna(part_monthly_data["_part_desc"].iloc[0]) else ""
        
        st.markdown(f"**物料描述:** {part_desc}")
        
        # 获取预测参数
        ma_window = st.session_state.get("ma_window", 3)
        wma_weight = st.session_state.get("wma_weight", 0.7)
        es_alpha = st.session_state.get("es_alpha", 0.3)
        
        # 计算三种模型的预测值
        qty_series = part_monthly_data["_quantity"]
        
        # MA预测
        ma_forecast = calculate_ma(qty_series, ma_window)
        # WMA预测
        wma_forecast = calculate_wma(qty_series, wma_weight)
        # ES预测
        es_forecast = calculate_es(qty_series, es_alpha)
        
        # 计算历史预测偏差（MAE）
        if len(qty_series) >= 4:
            # 取最后3个月作为测试集
            test_series = qty_series.iloc[-3:]
            train_series = qty_series.iloc[:-3]
            
            if len(train_series) >= 2:
                # 用训练集计算预测值
                ma_pred = calculate_ma(train_series, ma_window)
                wma_pred = calculate_wma(train_series, wma_weight)
                es_pred = calculate_es(train_series, es_alpha)
                
                # 计算MAE
                mae_ma = np.abs(test_series - ma_pred).mean()
                mae_wma = np.abs(test_series - wma_pred).mean()
                mae_es = np.abs(test_series - es_pred).mean()
                
                # 显示MAE指标
                mae_label = "预测偏差" if st.session_state.get("lang") == "ZH" else "MAE"
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric(f"MA ({mae_label})", f"{mae_ma:.2f}")
                with col2:
                    st.metric(f"WMA ({mae_label})", f"{mae_wma:.2f}")
                with col3:
                    st.metric(f"ES ({mae_label})", f"{mae_es:.2f}")
        
        # 创建图表数据
        chart_data = part_monthly_data[["_year_month_str", "_quantity"]].copy()
        chart_data = chart_data.rename(columns={"_year_month_str": get_text("sales.month"), "_quantity": get_text("sales.quantity")})
        
        # 添加预测线
        chart_data["MA"] = ma_forecast
        chart_data["WMA"] = wma_forecast
        chart_data["ES"] = es_forecast
        
        # 绘制图表
        fig = go.Figure()
        
        # 实际销量
        actual_label = "实际销量" if st.session_state.get("lang") == "ZH" else "Actual"
        ma_label = "MA"
        wma_label = "WMA"  
        es_label = "ES"
        
        fig.add_trace(go.Scatter(
            x=chart_data[get_text("sales.month")],
            y=chart_data[get_text("sales.quantity")],
            mode="lines+markers",
            name=actual_label,
            line=dict(color="#2ecc71", width=2)
        ))
        
        # MA预测线
        fig.add_trace(go.Scatter(
            x=chart_data[get_text("sales.month")],
            y=[ma_forecast] * len(chart_data),
            mode="lines",
            name="MA",
            line=dict(color="#3498db", width=2, dash="dash")
        ))
        
        # WMA预测线
        fig.add_trace(go.Scatter(
            x=chart_data[get_text("sales.month")],
            y=[wma_forecast] * len(chart_data),
            mode="lines",
            name="WMA",
            line=dict(color="#e74c3c", width=2, dash="dot")
        ))
        
        # ES预测线
        fig.add_trace(go.Scatter(
            x=chart_data[get_text("sales.month")],
            y=[es_forecast] * len(chart_data),
            mode="lines",
            name="ES",
            line=dict(color="#9b59b6", width=2, dash="dashdot")
        ))
        
        forecast_title = "预测趋势" if st.session_state.get("lang") == "ZH" else "Forecast Trend"
        fig.update_layout(
            title=f"{forecast_title}: {selected_part_no}",
            xaxis_title=get_text("sales.month"),
            yaxis_title=get_text("sales.quantity"),
            hovermode="x unified"
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # 显示预测结果
        pred_title = "预测结果" if st.session_state.get("lang") == "ZH" else "Prediction Result"
        st.markdown(f"### 📊 {pred_title}")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("MA", f"{math.ceil(ma_forecast)}")
        with col2:
            st.metric("WMA", f"{math.ceil(wma_forecast)}")
        with col3:
            st.metric("ES", f"{math.ceil(es_forecast)}")
    
    st.markdown("---")
    
    # ========== ABC类别筛选 ==========
    st.markdown(f"### {get_text('forecasting.detail_table')}")
    
    # ABC类别筛选器
    abc_filter = st.selectbox(
        get_text("forecasting.filter_by_abc"),
        options=[get_text("forecasting.all_classes"), "A", "B", "C"]
    )
    
    # 应用筛选
    if abc_filter != get_text("forecasting.all_classes"):
        filtered_df = results_df[results_df["_abc_class"] == abc_filter].copy()
    else:
        filtered_df = results_df.copy()
    
    # 准备显示数据
    display_cols = ["_part_no", "_abc_class", "_xyz_class", "_hist_avg", 
        "_suggested_qty", "_suggested_amount", "_unit_price",
        "_best_model", "_accuracy", "_sales_count"]
    
    # 如果有物料描述，添加到显示列
    if "_part_desc" in results_df.columns:
        display_cols.insert(1, "_part_desc")
    
    display_df = filtered_df[display_cols].copy()
    
    # 重命名列
    rename_dict = {
        "_part_no": get_text("procurement.part_no"),
        "_abc_class": get_text("forecasting.abc_class"),
        "_xyz_class": get_text("forecasting.xyz_class"),
        "_hist_avg": get_text("forecasting.historical_avg"),
        "_suggested_qty": get_text("forecasting.suggested_qty"),
        "_suggested_amount": get_text("forecasting.suggested_amount"),
        "_best_model": get_text("forecasting.best_model"),
        "_accuracy": get_text("forecasting.model_accuracy"),
        "_sales_count": get_text("forecasting.sales_count"),
    }
    if "_part_desc" in results_df.columns:
        rename_dict["_part_desc"] = "物料描述"
    
    display_df = display_df.rename(columns=rename_dict)
    
    # 格式化显示
    display_df[get_text("forecasting.historical_avg")] = display_df[get_text("forecasting.historical_avg")].apply(
        lambda x: f"{x:.1f}"
    )
    display_df[get_text("forecasting.suggested_qty")] = display_df[get_text("forecasting.suggested_qty")].apply(
        lambda x: f"{x}"
    )
    display_df[get_text("forecasting.suggested_amount")] = display_df[get_text("forecasting.suggested_amount")].apply(
        lambda x: f"${x:,.0f}" if x > 0 else get_text("forecasting.price_missing")
    )
    display_df[get_text("forecasting.model_accuracy")] = display_df[get_text("forecasting.model_accuracy")].apply(
        lambda x: f"{x*100:.1f}%" if pd.notna(x) else "N/A"
    )
    display_df[get_text("forecasting.sales_count")] = display_df[get_text("forecasting.sales_count")].apply(
        lambda x: f"{int(x)}"
    )
    
    # 排序
    display_df = display_df.sort_values(get_text("forecasting.suggested_amount"), ascending=False)
    
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )
    
    # ========== 模型准确率对比 ==========
    st.markdown("---")
    st.markdown("### 🎯 模型准确率对比")
    
    # 计算各模型的整体表现
    ma_accuracy = results_df["_accuracy"][results_df["_best_model"] == "MA"].mean()
    wma_accuracy = results_df["_accuracy"][results_df["_best_model"] == "WMA"].mean()
    es_accuracy = results_df["_accuracy"][results_df["_best_model"] == "ES"].mean()
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        stable_count = len(results_df[results_df["_best_model"] == "MA"])
        st.metric(
            label=f"MA ({get_text('forecasting.stable_model')})",
            value=f"{ma_accuracy*100:.1f}%" if pd.notna(ma_accuracy) else "N/A",
            delta=f"{stable_count} SKUs" if curr_lang == "EN" else f"{stable_count} 个SKU",
        )
    
    with col2:
        trend_wma_count = len(results_df[(results_df["_best_model"] == "WMA")])
        st.metric(
            label=f"WMA ({get_text('forecasting.trend_model')})",
            value=f"{wma_accuracy*100:.1f}%" if pd.notna(wma_accuracy) else "N/A",
            delta=f"{trend_wma_count} SKUs" if curr_lang == "EN" else f"{trend_wma_count} 个SKU",
        )
    
    with col3:
        trend_es_count = len(results_df[(results_df["_best_model"] == "ES")])
        st.metric(
            label=f"ES ({get_text('forecasting.trend_model')})",
            value=f"{es_accuracy*100:.1f}%" if pd.notna(es_accuracy) else "N/A",
            delta=f"{trend_es_count} SKUs" if curr_lang == "EN" else f"{trend_es_count} 个SKU",
        )
    
    # ========== 销售异常检测 ==========
    st.markdown("---")
    st.markdown("### 🔍 销售异常检测（可能是促销月份）")
    
    # 加载原始月度数据用于异常检测
    try:
        from core.forecast_engine import calculate_xyz_class
        raw_df = load_order_data()
        if not raw_df.empty:
            # 预处理
            processed = preprocess_order_data(raw_df)
            if not processed.empty:
                # 计算每个物料的月度统计
                anomaly_data = []
                
                for part_no in processed["_part_no"].unique():
                    part_data = processed[processed["_part_no"] == part_no].sort_values("_year_month")
                    
                    if len(part_data) < 4:  # 至少需要4个月数据
                        continue
                    
                    # 计算月均销量和标准差
                    qty_series = part_data["_quantity"]
                    mean_qty = qty_series.mean()
                    std_qty = qty_series.std()
                    
                    if pd.isna(std_qty) or std_qty == 0:
                        continue
                    
                    # 检测异常月份：超过均值+1.5倍标准差（降低阈值以捕获更多异常）
                    threshold = mean_qty + 1.5 * std_qty
                    
                    for _, row in part_data.iterrows():
                        if row["_quantity"] > threshold:
                            anomaly_data.append({
                                "物料号": row["_part_no"],
                                "物料描述": row.get("_part_desc", ""),
                                "年月": str(row["_year_month"]),
                                "销量": row["_quantity"],
                                "月均销量": round(mean_qty, 2),
                                "标准差": round(std_qty, 2),
                                "异常阈值": round(threshold, 2),
                                "异常程度": round(row["_quantity"] / mean_qty, 2)
                            })
                
                if anomaly_data:
                    anomaly_df = pd.DataFrame(anomaly_data)
                    anomaly_df = anomaly_df.sort_values("异常程度", ascending=False)
                    
                    col_anomaly1, col_anomaly2 = st.columns([3, 1])
                    
                    with col_anomaly1:
                        st.markdown(f"发现 **{len(anomaly_df)}** 条异常销售记录（可能是促销）")
                    
                    with col_anomaly2:
                        # 导出按钮
                        csv = anomaly_df.to_csv(index=False, encoding="utf-8-sig")
                        st.download_button(
                            label="📥 导出异常数据" if curr_lang == "ZH" else "📥 Export Anomalies",
                            data=csv,
                            file_name="sales_anomaly_export.csv",
                            mime="text/csv",
                            key="download_anomaly"
                        )
                    
                    # 显示异常数据表格
                    st.dataframe(
                        anomaly_df.head(50),
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    if len(anomaly_df) > 50:
                        st.info(f"显示前50条，共{len(anomaly_df)}条异常记录" if curr_lang == "ZH" else f"Showing first 50 of {len(anomaly_df)} anomaly records")
                else:
                    st.success("未发现明显异常销售月份" if curr_lang == "ZH" else "No abnormal sales months detected")
    except Exception as e:
        st.warning(f"异常检测功能暂时不可用: {e}" if curr_lang == "ZH" else f"Anomaly detection unavailable: {e}")


def main():
    """模块入口"""
    render_forecasting()


if __name__ == "__main__":
    main()
