"""
需求预测引擎 (Demand Forecasting Engine)

核心特性：
1. 异步预处理 - 计算结果持久化到 .parquet 文件
2. 分级参数寻优 (ABC-XYZ)
   - A类物料 + 活跃件：执行 Grid Search 寻找最优参数
   - C类物料 + 长尾件：使用固定经验参数
3. 预测总额 = Σ(预测数量 × 单价)

作者：Matrix Agent
"""

import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import math
import warnings

from config import SALES_DATA_DIR, FORECAST_CACHE_DIR


def ensure_cache_dir():
    """确保缓存目录存在"""
    cache_dir = Path(FORECAST_CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def load_order_data():
    """加载订单数据"""
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
    """预处理订单数据"""
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
        if part_no_col is None and "物料号" in col_str and "描述" not in col_str:
            part_no_col = col
        if part_desc_col is None and "物料描述" in col_str:
            part_desc_col = col
        if qty_col is None and "数量" in col_str and "已发" not in col_str and "未发" not in col_str:
            qty_col = col
        if confirm_time_col is None and "确认时间" in col_str:
            confirm_time_col = col
        if price_col is None and ("单价" in col_str or ("价格" in col_str and "总价" not in col_str)):
            price_col = col
    
    if not all([part_no_col, qty_col, confirm_time_col]):
        return pd.DataFrame()
    
    # 创建副本并添加标准化列
    df = df.copy()
    df["_part_no"] = df[part_no_col].astype(str)
    
    # 转换日期
    df["_confirm_date"] = pd.to_datetime(df[confirm_time_col], errors="coerce")
    df = df[df["_confirm_date"].notna()].copy()
    
    # 提取年月
    df["_year_month"] = df["_confirm_date"].dt.to_period("M")
    
    # 转换数量为数值
    df["_qty"] = pd.to_numeric(df[qty_col], errors="coerce").fillna(0)
    
    # 转换单价
    if price_col:
        df["_unit_price"] = pd.to_numeric(df[price_col], errors="coerce").fillna(0)
    else:
        df["_unit_price"] = 0
    
    # 提取物料描述
    if part_desc_col:
        df["_part_desc"] = df[part_desc_col].astype(str)
    else:
        df["_part_desc"] = ""
    
    # 按月汇总
    monthly_df = df.groupby(["_part_no", "_part_desc", "_year_month"]).agg({
        "_qty": "sum",
        "_unit_price": "max",
    }).reset_index()
    
    # 重命名列
    monthly_df = monthly_df.rename(columns={"_qty": "_quantity"})
    
    # 转换年月为日期
    monthly_df["_year_month"] = monthly_df["_year_month"].dt.to_timestamp()
    
    # 添加字符串格式的年月（用于图表显示）
    monthly_df["_year_month_str"] = monthly_df["_year_month"].dt.strftime("%Y-%m")
    
    return monthly_df


def calculate_abc_class(results_df: pd.DataFrame) -> pd.DataFrame:
    """
    计算ABC分类（严格基于历史销售额）
    
    重要原则：
    - 严禁使用 _suggested_amount 或 _next_forecast 等预测值
    - 必须基于每个 SKU 的历史实际销售总额
    
    分类标准（帕累托法则 - 80/20法则）：
    - A类：累计销售额 <= 80% 的物料（约占总数15-20%）
    - B类：累计销售额 80%-95% 的物料
    - C类：累计销售额 > 95% 的物料
    
    Args:
        results_df: 包含历史销量和单价的DataFrame，必须包含：
                   - _quantity: 历史销量总和
                   - _unit_price: 单价
    
    Returns:
        pd.DataFrame: 添加了 _abc_class 列的DataFrame
    """
    if results_df.empty:
        return results_df
    
    # ========== 步骤1：确保使用历史销售额 ==========
    # 严格基于历史：_quantity * _unit_price（绝不使用预测值）
    if "_quantity" in results_df.columns and "_unit_price" in results_df.columns:
        results_df["_hist_amount"] = results_df["_quantity"] * results_df["_unit_price"]
    else:
        results_df["_hist_amount"] = 0
    
    # ========== 步骤2：按历史金额排序 ==========
    results_df = results_df.sort_values("_hist_amount", ascending=False).reset_index(drop=True)
    
    # ========== 步骤3：计算累计占比 ==========
    total_hist_amount = results_df["_hist_amount"].sum()
    if total_hist_amount > 0:
        results_df["_cumsum_amount"] = results_df["_hist_amount"].cumsum()
        results_df["_cumsum_pct"] = results_df["_cumsum_amount"] / total_hist_amount
    else:
        results_df["_cumsum_pct"] = 0
    
    # ========== 步骤4：ABC分类（帕累托标准：80/20法则） ==========
    # A类: 累计 <= 80% - 核心物料（约占15-20%数量）
    # B类: 累计 80%-95% - 次要物料
    # C类: 累计 > 95% - 普通物料
    def classify_abc_pareto(pct):
        if pct <= 0.80:  # 前80% -> A类
            return "A"
        elif pct <= 0.95:  # 80%-95% -> B类
            return "B"
        else:  # 后5% -> C类
            return "C"
    
    results_df["_abc_class"] = results_df["_cumsum_pct"].apply(classify_abc_pareto)
    
    # 清理临时列
    results_df = results_df.drop(columns=["_cumsum_amount", "_cumsum_pct"])
    
    return results_df


def calculate_xyz_class(monthly_df: pd.DataFrame) -> pd.DataFrame:
    """计算XYZ分类（基于需求波动性）"""
    if monthly_df.empty:
        return pd.DataFrame()
    
    # 按物料号分组计算统计量
    stats = monthly_df.groupby("_part_no").agg({
        "_quantity": ["mean", "std", "count"]
    }).reset_index()
    
    stats.columns = ["_part_no", "_mean", "_std", "_sales_count"]
    
    # 计算变异系数 (CV = std / mean)
    stats["_cv"] = stats["_std"] / stats["_mean"].replace(0, np.nan)
    
    # 分类: X (CV < 0.5 稳定), Y (0.5 <= CV < 1 一般), Z (CV >= 1 不稳定)
    def classify_xyz(cv):
        if pd.isna(cv) or cv == 0:
            return "Z"  # 销售次数太少，视为不稳定
        elif cv < 0.5:
            return "X"
        elif cv < 1.0:
            return "Y"
        else:
            return "Z"
    
    stats["_xyz_class"] = stats["_cv"].apply(classify_xyz)
    
    return stats[["_part_no", "_xyz_class", "_cv", "_sales_count"]]


def grid_search_ma(qty_series: pd.Series, backtest_months: int) -> dict:
    """
    MA模型的Grid Search寻优
    
    Returns:
        dict: 最佳窗口大小和对应MAE
    """
    if len(qty_series) < backtest_months + 3:
        return {"best_window": 3, "mae": float('inf')}
    
    results = []
    for window in range(2, min(7, len(qty_series) - backtest_months)):
        # 滑动窗口回测
        mae_list = []
        for i in range(backtest_months, len(qty_series)):
            # 使用前window个月预测第i个月
            history = qty_series.iloc[i - window:i].values
            actual = qty_series.iloc[i]
            if len(history) > 0:
                forecast = np.mean(history)
                mae_list.append(abs(actual - forecast))
        
        if mae_list:
            results.append({"window": window, "mae": np.mean(mae_list)})
    
    if not results:
        return {"best_window": 3, "mae": float('inf')}
    
    best = min(results, key=lambda x: x["mae"])
    return {"best_window": best["window"], "mae": best["mae"]}


def grid_search_wma(qty_series: pd.Series, backtest_months: int) -> dict:
    """
    WMA模型的Grid Search寻优
    
    Returns:
        dict: 最佳权重和对应MAE
    """
    if len(qty_series) < backtest_months + 3:
        return {"best_weight": 0.7, "mae": float('inf')}
    
    results = []
    for weight in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        mae_list = []
        for i in range(backtest_months, len(qty_series)):
            history = qty_series.iloc[i-3:i].values  # 使用最近3个月
            actual = qty_series.iloc[i]
            if len(history) > 0:
                # 加权平均：近期权重更高
                weights = np.array([1, 2, 3]) * weight
                weights = weights[:len(history)] / weights[:len(history)].sum()
                forecast = np.average(history, weights=weights)
                mae_list.append(abs(actual - forecast))
        
        if mae_list:
            results.append({"weight": weight, "mae": np.mean(mae_list)})
    
    if not results:
        return {"best_weight": 0.7, "mae": float('inf')}
    
    best = min(results, key=lambda x: x["mae"])
    return {"best_weight": best["weight"], "mae": best["mae"]}


def grid_search_es(qty_series: pd.Series, backtest_months: int) -> dict:
    """
    ES模型的Grid Search寻优（向量化优化版本）
    
    Returns:
        dict: 最佳alpha和对应MAE
    """
    if len(qty_series) < backtest_months + 3:
        return {"best_alpha": 0.3, "mae": float('inf')}
    
    results = []
    alpha_values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    
    for alpha in alpha_values:
        # 使用Pandas向量化方法计算指数平滑
        # ewm(alpha=alpha) 等价于: F(t) = alpha * X(t) + (1-alpha) * F(t-1)
        es_forecast = qty_series.ewm(alpha=alpha, adjust=False).mean()
        
        # 计算回测期的MAE
        # 回测期：最后backtest_months个月
        test_start_idx = len(qty_series) - backtest_months
        
        if test_start_idx > 0:
            actual_values = qty_series.iloc[test_start_idx:].values
            forecast_values = es_forecast.iloc[test_start_idx:].values
            
            mae = np.mean(np.abs(actual_values - forecast_values))
            results.append({"alpha": alpha, "mae": mae})
    
    if not results:
        return {"best_alpha": 0.3, "mae": float('inf')}
    
    best = min(results, key=lambda x: x["mae"])
    return {"best_alpha": best["alpha"], "mae": best["mae"]}


def run_forecast(
    monthly_df: pd.DataFrame,
    abc_xyz_data: pd.DataFrame,
    backtest_months: int = 6,
    progress_bar=None,
    status_text=None,
) -> pd.DataFrame:
    """
    执行需求预测（分级参数寻优）
    
    Args:
        monthly_df: 月度汇总数据
        abc_xyz_data: ABC-XYZ分类数据
        backtest_months: 回测月数
        progress_bar: Streamlit进度条
        status_text: 状态文本显示
    
    Returns:
        pd.DataFrame: 预测结果
    """
    # 获取所有活跃物料
    part_nos = monthly_df["_part_no"].unique()
    total_parts = len(part_nos)
    
    results = []
    
    for idx, part_no in enumerate(part_nos):
        # 更新进度
        if progress_bar:
            progress_bar.progress((idx + 1) / total_parts)
        if status_text:
            status_text.text(f"正在预测物料 {idx + 1}/{total_parts}: {part_no}")
        
        # 获取该物料的历史数据
        part_data = monthly_df[monthly_df["_part_no"] == part_no].sort_values("_year_month")
        
        # 获取销售次数
        part_xyz = abc_xyz_data[abc_xyz_data["_part_no"] == part_no]
        if not part_xyz.empty:
            sales_count = part_xyz["_sales_count"].iloc[0]
            xyz_class = part_xyz["_xyz_class"].iloc[0]
            abc_class = part_xyz.get("_abc_class", pd.Series(["C"] * len(part_xyz))).iloc[0] if "_abc_class" in part_xyz.columns else "C"
        else:
            sales_count = 0
            xyz_class = "Z"
            abc_class = "C"
        
        # 仅对活跃物料进行预测
        if sales_count <= 1:
            continue
        
        if len(part_data) < 3:
            continue
        
        # 获取销量序列
        qty_series = part_data["_quantity"]
        
        # ========== 分级参数寻优 ==========
        # A类物料 + X类(稳定)物料：执行Grid Search
        # C类物料 + Z类物料：使用固定参数
        if (abc_class == "A" or xyz_class == "X") and len(qty_series) >= backtest_months + 3:
            # 执行Grid Search
            ma_result = grid_search_ma(qty_series, backtest_months)
            wma_result = grid_search_wma(qty_series, backtest_months)
            es_result = grid_search_es(qty_series, backtest_months)
            
            best_ma_window = ma_result["best_window"]
            best_wma_weight = wma_result["best_weight"]
            best_es_alpha = es_result["best_alpha"]
            use_grid_search = True
        else:
            # 使用固定参数
            best_ma_window = 3
            best_wma_weight = 0.7
            best_es_alpha = 0.3
            use_grid_search = False
        
        # 使用最优参数进行最终预测
        # MA预测
        if len(qty_series) >= best_ma_window:
            ma_forecast = qty_series.iloc[-best_ma_window:].mean()
        else:
            ma_forecast = qty_series.mean()
        
        # WMA预测
        if len(qty_series) >= 3:
            weights = np.array([1, 2, 3]) * best_wma_weight
            weights = weights / weights.sum()
            wma_forecast = np.average(qty_series.iloc[-3:].values, weights=weights)
        else:
            wma_forecast = qty_series.mean()
        
        # ES预测
        es_forecast = qty_series.iloc[0]
        for i in range(1, len(qty_series)):
            es_forecast = best_es_alpha * qty_series.iloc[i] + (1 - best_es_alpha) * es_forecast
        
        # 计算各模型回测准确率
        mae_ma = float('inf')
        mae_wma = float('inf')
        mae_es = float('inf')
        
        # 记录回测期的实际销量（用于计算准确率）
        backtest_actuals = []
        
        if len(qty_series) >= backtest_months + 3:
            ma_mae_list = []
            wma_mae_list = []
            es_mae_list = []
            
            es_init = qty_series.iloc[0]
            for i in range(backtest_months, len(qty_series)):
                history = qty_series.iloc[i - best_ma_window:i].values
                actual = qty_series.iloc[i]
                
                # 记录回测期实际销量
                backtest_actuals.append(actual)
                
                # MA
                if len(history) > 0:
                    ma_pred = np.mean(history)
                    ma_mae_list.append(abs(actual - ma_pred))
                
                # WMA
                if len(qty_series.iloc[i-3:i].values) >= 3:
                    wma_hist = qty_series.iloc[i-3:i].values
                    wma_weights = np.array([1, 2, 3]) * best_wma_weight
                    wma_weights = wma_weights / wma_weights.sum()
                    wma_pred = np.average(wma_hist, weights=wma_weights)
                    wma_mae_list.append(abs(actual - wma_pred))
                
                # ES
                es_pred = es_init
                for j in range(i):
                    es_init = best_es_alpha * qty_series.iloc[j] + (1 - best_es_alpha) * es_init
                es_mae_list.append(abs(actual - es_init))
            
            if ma_mae_list:
                mae_ma = np.mean(ma_mae_list)
            if wma_mae_list:
                mae_wma = np.mean(wma_mae_list)
            if es_mae_list:
                mae_es = np.mean(es_mae_list)
        
        # 选择最优模型
        models = [("MA", mae_ma, ma_forecast), ("WMA", mae_wma, wma_forecast), ("ES", mae_es, es_forecast)]
        valid_models = [(name, mae, forecast) for name, mae, forecast in models if mae != float('inf')]
        
        if valid_models:
            best_model, best_mae, next_forecast = min(valid_models, key=lambda x: x[1])
            
            # ========== 修复准确率计算 ==========
            # 使用回测期实际销量均值作为分母
            # 但当回测期均值过小(<1)时，改用历史均值，避免准确率失真
            if backtest_actuals:
                backtest_mean = np.mean(backtest_actuals)
                # 回测期均值必须 >= 1 才使用，否则使用历史均值
                if backtest_mean >= 1:
                    accuracy = 1 - (best_mae / backtest_mean)
                else:
                    # 回测期销量过小，使用历史均值
                    hist_mean = qty_series.mean()
                    if hist_mean > 0:
                        accuracy = 1 - (best_mae / hist_mean)
                    else:
                        accuracy = 0
            else:
                # 如果没有回测数据，使用历史均值
                accuracy = 1 - (best_mae / qty_series.mean()) if qty_series.mean() > 0 else 0
            
            accuracy = max(0, min(1, accuracy))  # 限制在 0-100% 之间
        else:
            best_model = "MA"
            best_mae = 0
            next_forecast = ma_forecast
            accuracy = 0.5
        
        # 获取单价
        unit_price = part_data["_unit_price"].max()
        
        # 获取物料描述
        part_desc = ""
        if "_part_desc" in part_data.columns:
            part_desc = str(part_data["_part_desc"].iloc[0]) if pd.notna(part_data["_part_desc"].iloc[0]) else ""
        
        # 预测数量向上取整
        suggested_qty = math.ceil(next_forecast) if next_forecast else 0
        
        # 计算建议金额
        if unit_price > 0:
            suggested_amount = suggested_qty * unit_price
        else:
            suggested_amount = 0
        
        # 计算历史月均
        hist_avg = qty_series.mean()
        
        results.append({
            "_part_no": part_no,
            "_part_desc": part_desc,
            "_quantity": qty_series.sum(),
            "_sales_count": sales_count,
            "_unit_price": unit_price,
            "_hist_avg": hist_avg,
            "_next_forecast": next_forecast,
            "_suggested_qty": suggested_qty,
            "_suggested_amount": suggested_amount,
            "_best_model": best_model,
            "_model_params": {
                "ma_window": best_ma_window,
                "wma_weight": best_wma_weight,
                "es_alpha": best_es_alpha,
            },
            "_accuracy": accuracy,
            "_mae": best_mae,
            "_abc_class": abc_class,
            "_xyz_class": xyz_class,
            "_use_grid_search": use_grid_search,
        })
    
    return pd.DataFrame(results)


def save_forecast_cache(results_df: pd.DataFrame) -> Path:
    """保存预测结果到缓存"""
    cache_dir = ensure_cache_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    cache_file = cache_dir / f"forecast_cache_{timestamp}.parquet"
    
    results_df.to_parquet(cache_file, index=False)
    
    # 保存最新一份到 latest.parquet
    latest_file = cache_dir / "forecast_latest.parquet"
    results_df.to_parquet(latest_file, index=False)
    
    return cache_file


def load_forecast_cache() -> pd.DataFrame:
    """加载预测缓存"""
    cache_dir = ensure_cache_dir()
    latest_file = cache_dir / "forecast_latest.parquet"
    
    if latest_file.exists():
        return pd.read_parquet(latest_file)
    
    return pd.DataFrame()


def get_cache_info() -> dict:
    """获取缓存信息"""
    cache_dir = ensure_cache_dir()
    latest_file = cache_dir / "forecast_latest.parquet"
    
    if latest_file.exists():
        stat = latest_file.stat()
        return {
            "exists": True,
            "file": str(latest_file),
            "size_kb": stat.st_size / 1024,
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }
    
    return {"exists": False}


# ========== 独立计算函数 ==========
def calculate_ma(qty_series: pd.Series, window: int) -> float:
    """
    计算移动平均预测值
    
    Args:
        qty_series: 历史销量序列
        window: 移动窗口大小
    
    Returns:
        float: 预测值
    """
    if len(qty_series) == 0:
        return 0.0
    if len(qty_series) < window:
        window = len(qty_series)
    return qty_series.iloc[-window:].mean()


def calculate_wma(qty_series: pd.Series, weight: float = 0.7) -> float:
    """
    计算加权移动平均预测值
    
    Args:
        qty_series: 历史销量序列
        weight: 近期权重因子
    
    Returns:
        float: 预测值
    """
    if len(qty_series) == 0:
        return 0.0
    
    n = min(3, len(qty_series))
    recent_data = qty_series.iloc[-n:].values
    
    # 权重: [1, 2, 3] * weight，然后归一化
    weights = np.array([i + 1 for i in range(n)]) * weight
    weights = weights / weights.sum()
    
    return np.average(recent_data, weights=weights)


def calculate_es(qty_series: pd.Series, alpha: float = 0.3) -> float:
    """
    计算指数平滑预测值
    
    Args:
        qty_series: 历史销量序列
        alpha: 平滑系数
    
    Returns:
        float: 预测值
    """
    if len(qty_series) == 0:
        return 0.0
    
    # 使用Pandas ewm向量化计算
    es_result = qty_series.ewm(alpha=alpha, adjust=False).mean()
    return es_result.iloc[-1]
