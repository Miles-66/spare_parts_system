"""
库存健康诊断引擎 (Inventory Health Diagnostic Engine)

功能：
1. 安全库存计算 (Safety Stock)
2. 再订货点计算 (ROP - Reorder Point)
3. 库存健康评分
4. 库存预警与建议

计算公式：
- 安全库存: SS = Z × σ × √LT
- 再订货点: ROP = D × LT + SS
- 库存周转天数: DOS = Inventory / Daily Demand

Author: Matrix Agent
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.inventory_health_data import run_health_data_pipeline, SALES_CUTOFF_DATE, SHIPPING_OFFSET, load_forecast_data

# 常量配置
SALES_DATA_DIR = "D:/spare_parts_system/data_source/sales"
INVENTORY_DATA_DIR = "D:/spare_parts_system/data_source/inventory"

# 服务系数对应的Z值（使用近似值表）
SLA_TO_Z = {
    0.50: 0.00,
    0.60: 0.25,
    0.70: 0.52,
    0.80: 0.84,
    0.85: 1.04,
    0.90: 1.28,
    0.95: 1.65,
    0.97: 1.88,
    0.99: 2.33
}

# 扩展Z值表（用于插值）
EXTENDED_Z_TABLE = {
    0.50: 0.000, 0.55: 0.125, 0.60: 0.253, 0.65: 0.385, 0.70: 0.524,
    0.75: 0.674, 0.80: 0.842, 0.82: 0.915, 0.84: 0.994, 0.86: 1.080,
    0.88: 1.175, 0.90: 1.282, 0.91: 1.341, 0.92: 1.405, 0.93: 1.476,
    0.94: 1.555, 0.95: 1.645, 0.96: 1.751, 0.97: 1.880, 0.98: 2.054,
    0.99: 2.326, 0.995: 2.576, 0.999: 3.090
}


def get_z_value(sla: float) -> float:
    """
    根据服务系数获取Z值（使用查表+线性插值）
    
    Args:
        sla: 服务系数 (0-1)
    
    Returns:
        Z值
    """
    if sla <= 0:
        return 0
    
    # 精确匹配
    if sla in EXTENDED_Z_TABLE:
        return EXTENDED_Z_TABLE[sla]
    
    # 线性插值
    sla_keys = sorted(EXTENDED_Z_TABLE.keys())
    for i, key in enumerate(sla_keys):
        if key > sla and i > 0:
            prev_key = sla_keys[i - 1]
            # 线性插值
            ratio = (sla - prev_key) / (key - prev_key)
            return EXTENDED_Z_TABLE[prev_key] + ratio * (EXTENDED_Z_TABLE[key] - EXTENDED_Z_TABLE[prev_key])
    
    # 默认返回值
    return 1.28  # 90% 对应的Z值


def is_valid_file(filename: str) -> bool:
    """检查是否为有效文件"""
    return not filename.startswith("~")


def calculate_daily_demand(sales_df: pd.DataFrame, part_no: str, days: int = 90) -> float:
    """
    计算指定物料的平均日需求量
    
    Args:
        sales_df: 销售数据
        part_no: 物料号
        days: 计算天数（默认90天）
    
    Returns:
        平均日需求量
    """
    part_sales = sales_df[sales_df["_part_no"] == part_no]
    if len(part_sales) == 0:
        return 0
    
    # 按日期排序
    part_sales = part_sales.sort_values("date")
    
    # 获取最近N天的数据
    cutoff_date = part_sales["date"].max() - timedelta(days=days)
    recent_sales = part_sales[part_sales["date"] >= cutoff_date]
    
    if len(recent_sales) == 0:
        return 0
    
    # 计算日期范围
    date_range = (recent_sales["date"].max() - recent_sales["date"].min()).days + 1
    if date_range <= 0:
        date_range = 1
    
    total_qty = recent_sales["quantity"].sum()
    daily_demand = total_qty / max(date_range, 1)
    
    return daily_demand


def calculate_demand_std(sales_df: pd.DataFrame, part_no: str, days: int = 90) -> float:
    """
    计算需求标准差
    
    Args:
        sales_df: 销售数据
        part_no: 物料号
        days: 计算天数
    
    Returns:
        需求标准差
    """
    part_sales = sales_df[sales_df["_part_no"] == part_no]
    if len(part_sales) < 2:
        # 数据不足，返回默认值
        return calculate_daily_demand(sales_df, part_no, days) * 0.5
    
    # 按日期聚合
    part_sales = part_sales.sort_values("date")
    cutoff_date = part_sales["date"].max() - timedelta(days=days)
    recent_sales = part_sales[part_sales["date"] >= cutoff_date]
    
    if len(recent_sales) < 2:
        return calculate_daily_demand(sales_df, part_no, days) * 0.5
    
    # 计算日销量标准差
    daily_std = recent_sales.groupby("date")["quantity"].sum().std()
    
    if pd.isna(daily_std) or daily_std == 0:
        return calculate_daily_demand(sales_df, part_no, days) * 0.5
    
    return daily_std


def load_sales_for_demand_calc() -> pd.DataFrame:
    """
    加载销售数据用于需求计算
    
    Returns:
        DataFrame with _part_no, date, quantity
    """
    print("=== 加载销售数据用于需求计算 ===")
    
    files = [f for f in Path(SALES_DATA_DIR).glob("*订单明细*.xlsx") if is_valid_file(f.name)]
    if not files:
        print("警告: 未找到销售订单明细文件")
        return pd.DataFrame()
    
    df = pd.read_excel(max(files, key=lambda x: x.stat().st_mtime))
    print(f"原始记录: {len(df)} 条")
    
    # 跳过前3列元数据
    if len(df.columns) > 3:
        df = df.iloc[:, 3:].copy()
    
    # 标准化列名
    df.columns = [str(c).strip() for c in df.columns]
    
    # 查找日期列和数量列
    date_col = None
    qty_col = None
    part_col = None
    
    for col in df.columns:
        if "时间" in col or "日期" in col:
            date_col = col
        if "数量" in col or "Qty" in col or "qty" in col:
            qty_col = col
        if "物料号" in col or "备件号" in col or "Part" in col:
            part_col = col
    
    if not date_col or not qty_col or not part_col:
        print(f"错误: 缺少必要列 - date_col:{date_col}, qty_col:{qty_col}, part_col:{part_col}")
        return pd.DataFrame()
    
    # 转换类型
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df[qty_col] = pd.to_numeric(df[qty_col], errors="coerce").fillna(0)
    df[part_col] = df[part_col].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    
    # 重命名列
    df = df.rename(columns={
        date_col: "date",
        qty_col: "quantity",
        part_col: "_part_no"
    })
    
    # 过滤有效数据
    df = df[df["date"].notna() & (df["quantity"] > 0)]
    
    print(f"有效销售记录: {len(df)} 条")
    
    return df[["date", "_part_no", "quantity"]]


def load_inventory_position() -> pd.DataFrame:
    """
    加载当前库存数据
    
    Returns:
        DataFrame with _part_no, inventory_qty
    """
    print("=== 加载当前库存数据 ===")
    
    # 尝试从多个来源获取库存
    files = []
    
    # 搜索库存相关文件
    inventory_dir = Path(INVENTORY_DATA_DIR)
    if inventory_dir.exists():
        # 优先选择包含"库存"的文件
        stock_files = [f for f in inventory_dir.glob("*库存*.xlsx") if is_valid_file(f.name)]
        if stock_files:
            files = stock_files
        else:
            files = [f for f in inventory_dir.glob("*.xlsx") if is_valid_file(f.name)]
    
    if not files:
        print("警告: 未找到库存数据文件")
        return pd.DataFrame()
    
    # 优先选择包含"库存"的文件，否则选最新的
    preferred_files = [f for f in files if "库存" in f.name]
    if preferred_files:
        target_file = preferred_files[0]
    else:
        target_file = max(files, key=lambda x: x.stat().st_mtime)
    
    df = pd.read_excel(target_file)
    print(f"读取文件: {target_file.name}")
    print(f"原始记录: {len(df)} 条")
    
    # 库存数据文件不需要跳过前3列，只有订单明细才需要
    # 检查是否有元数据列（通常前几列是空的或者有特殊格式）
    # 对于库存数据，直接使用原始列
    
    # 标准化列名
    df.columns = [str(c).strip() for c in df.columns]
    
    # 查找物料号和库存数量列
    part_col = None
    qty_col = None
    
    # 优先匹配"库存数量"，避免匹配到"冻结库存中的值"等
    for col in df.columns:
        if "物料号" in col or "备件号" in col or "Part" in col or "件号" in col:
            part_col = col
    
    # 优先使用"库存数量"列
    if "库存数量" in df.columns:
        qty_col = "库存数量"
    else:
        # 备选方案：匹配包含"库存"或"数量"的列
        for col in df.columns:
            if col == "库存数量":
                qty_col = col
            elif qty_col is None and ("库存" in col or "Stock" in col or "Inventory" in col or "Qty" in col):
                # 排除"冻结"相关列
                if "冻结" not in col:
                    qty_col = col
    
    if not part_col:
        print("错误: 未找到物料号列")
        return pd.DataFrame()
    
    if not qty_col:
        # 尝试数值列
        for col in df.columns:
            if df[col].dtype in ['int64', 'float64']:
                qty_col = col
                break
    
    if not qty_col:
        print("警告: 未找到库存数量列")
        return pd.DataFrame()
    
    # 标准化
    df[part_col] = df[part_col].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df[qty_col] = pd.to_numeric(df[qty_col], errors="coerce").fillna(0)
    
    # 获取物料描述和价格（总价列已包含数量，直接求和）
    desc_col = None
    price_col = None
    for col in df.columns:
        # 优先使用"物料描述"，避免匹配到"存储地点描述"等
        if desc_col is None and col == "物料描述":
            desc_col = col
        elif desc_col is None and "物料描述" in str(col):
            desc_col = col
        if "总价" in col or "价格" in col or "Price" in col:
            price_col = col
    
    # 调试：显示找到的描述列
    print(f"  物料描述列: {desc_col}")
    print(f"  价格列: {price_col}")
    
    # 注意：总价列已经是每行的总价值（包含数量），直接求和即可
    if desc_col and price_col:
        # 按物料号聚合：数量求和，描述取第一个，总价直接求和
        result = df.groupby(part_col).agg({
            qty_col: 'sum',
            desc_col: 'first',
            price_col: 'sum'  # 总价列直接求和
        }).reset_index()
        result.columns = ["_part_no", "inventory_qty", "part_name", "_total_value"]
        # 计算单价（仅用于显示）
        result["_unit_price"] = result["_total_value"] / result["inventory_qty"]
        result["_unit_price"] = result["_unit_price"].replace([float('inf'), float('-inf')], 0).fillna(0)
    elif desc_col:
        result = df.groupby(part_col).agg({
            qty_col: 'sum',
            desc_col: 'first'
        }).reset_index()
        result.columns = ["_part_no", "inventory_qty", "part_name"]
        result["_total_value"] = 0
        result["_unit_price"] = 0
    elif price_col:
        result = df.groupby(part_col).agg({
            qty_col: 'sum',
            price_col: 'sum'
        }).reset_index()
        result.columns = ["_part_no", "inventory_qty", "_total_value"]
        result["part_name"] = ""
        result["_unit_price"] = result["_total_value"] / result["inventory_qty"]
        result["_unit_price"] = result["_unit_price"].replace([float('inf'), float('-inf')], 0).fillna(0)
    else:
        result = df.groupby(part_col)[qty_col].sum().reset_index()
        result.columns = ["_part_no", "inventory_qty"]
        result["part_name"] = ""
        result["_unit_price"] = 0
    
    print(f"库存物料数: {len(result)}")
    
    return result


def calculate_safety_stock(row: pd.Series) -> float:
    """
    计算安全库存（使用交期波动率）
    
    公式: SS = Z × 平均日需求 × 交期标准差
    
    业务说明：
    - 备件出货量小，需求波动干扰大
    - 改用交期波动率驱动安全库存，更具实战意义
    
    Args:
        row: 包含以下字段的Series:
            - sla: 服务系数
            - daily_demand: 平均日需求
            - lt_std: 交期标准差
    
    Returns:
        安全库存数量
    """
    sla = row.get("sla", 0.9)
    daily_demand = row.get("daily_demand", 0)
    lt_std = row.get("lt_std", 30)  # 交期标准差，默认30天
    
    if sla <= 0 or daily_demand <= 0:
        return 0
    
    z = get_z_value(sla)
    # 新公式：SS = Z × D × σ_LT
    ss = z * daily_demand * lt_std
    
    return max(0, round(ss, 2))


def calculate_rop(row: pd.Series) -> float:
    """
    计算再订货点
    
    公式: ROP = D × LT + SS
    
    Args:
        row: 包含以下字段的Series:
            - daily_demand: 平均日需求
            - final_lt: 最终交期（天）
            - safety_stock: 安全库存
    
    Returns:
        再订货点
    """
    daily_demand = row.get("daily_demand", 0)
    lead_time = row.get("final_lt", 70 + SHIPPING_OFFSET)
    safety_stock = row.get("safety_stock", 0)
    
    rop = daily_demand * lead_time + safety_stock
    
    return max(0, round(rop, 2))


def calculate_days_of_supply(row: pd.Series) -> float:
    """
    计算库存周转天数 (Days of Supply)
    
    公式: DOS = Inventory / Daily Demand
    
    Args:
        row: 包含以下字段的Series:
            - inventory_qty: 当前库存
            - daily_demand: 平均日需求
    
    Returns:
        库存周转天数
    """
    inventory = row.get("inventory_qty", 0)
    daily_demand = row.get("daily_demand", 0)
    
    if daily_demand <= 0:
        return float('inf') if inventory > 0 else 0
    
    return round(inventory / daily_demand, 1)


def calculate_health_classification(row: pd.Series) -> tuple:
    """
    计算库存健康分类（简化为三类）
    
    分类逻辑：
    1. 积压：(当前库存 + 全链路在途) > ROP × 1.25
    2. 缺货预警：(当前库存 + 全链路在途) < 安全库存
    3. 正常：其他情况
    
    核心概念：
    - Max_Inv = ROP × 1.25 (最大库存水位)
    - 全链路在途 = Stage1 + Stage2 + Stage3 + Stage4
    
    Returns:
        (level: str, reason: str, overstock_qty: float, stockout_qty: float)
    """
    inventory = row.get("inventory_qty", 0)
    safety_stock = row.get("safety_stock", 0)
    rop = row.get("rop", 0)
    total_in_transit = row.get("total_in_transit", 0)
    
    overstock_qty = 0.0
    stockout_qty = 0.0
    
    # 计算有效库存 = 当前库存 + 全链路在途（用于判断是否缺货）
    effective_inventory = inventory + total_in_transit
    
    # 计算最大库存水位
    max_inventory = rop * 1.25
    
    # 计算积压数量 = 当前仓库库存 - 最大库存（仅使用在库库存，不含在途）
    # 在途库存是"即将到货"的物资，不应该算作积压
    overstock_qty = inventory - max_inventory
    
    # 判断分类（优先判断积压）
    # 积压：总库存 > 最大库存
    if overstock_qty > 0:
        level = "积压"
        reason = f"超过最大水位({max_inventory:.0f})，积压{overstock_qty:.0f}"
    # 缺货预警：总库存 < 安全库存
    elif safety_stock > 0 and effective_inventory < safety_stock:
        level = "缺货预警"
        stockout_qty = safety_stock - effective_inventory
        reason = f"低于安全库存({safety_stock:.0f})，缺{stockout_qty:.0f}"
    # 正常
    else:
        level = "正常"
        if effective_inventory == 0:
            reason = "无库存"
        elif safety_stock == 0 and effective_inventory > 0:
            reason = f"无销售记录，库存{effective_inventory:.0f}"
        else:
            reason = f"库存正常(Max:{max_inventory:.0f}, Current:{effective_inventory:.0f})"
    
    return level, reason, max(0, overstock_qty), max(0, safety_stock - effective_inventory)


def calculate_health_score(row: pd.Series) -> tuple:
    """
    计算库存健康评分（保留用于排序）
    
    评分维度:
    1. 库存充足度 (40%): 实际库存 vs 安全库存
    2. 库存周转 (30%): DOS是否在合理范围
    3. 销售活跃度 (20%): 是否有近期销售
    4. 在途合理性 (10%): 在途是否充足
    
    Returns:
        (score: float, level: str, reason: str)
    """
    # 使用新的分类函数
    level, reason, _, _ = calculate_health_classification(row)
    
    # 计算分数（用于排序）
    score = 50  # 默认分数
    if level == "正常":
        score = 80
    elif level == "缺货预警":
        score = 30
    elif level == "积压":
        score = 20
    
    return score, level, reason


def generate_recommendations(df: pd.DataFrame) -> pd.DataFrame:
    """
    生成库存优化建议
    
    Returns:
        DataFrame: 包含建议
    """
    recommendations = []
    
    for _, row in df.iterrows():
        part_no = row["_part_no"]
        inventory = row.get("inventory_qty", 0)
        safety_stock = row.get("safety_stock", 0)
        daily_demand = row.get("daily_demand", 0)
        rop = row.get("rop", 0)
        total_in_transit = row.get("total_in_transit", 0)
        is_active = row.get("is_active", False)
        level = row.get("health_level", "")
        
        recs = []
        
        # 库存不足建议
        if inventory < safety_stock * 0.5:
            recs.append("紧急补货：库存低于安全库存50%")
        elif inventory < safety_stock:
            if not is_active:
                recs.append("建议补货：库存低于安全库存（非活跃物料）")
            else:
                recs.append("建议补货：库存低于安全库存")
        
        # 缺货风险
        if daily_demand > 0 and inventory < daily_demand * 7:
            days_left = inventory / daily_demand if daily_demand > 0 else 0
            recs.append(f"缺货风险：库存仅够{days_left:.0f}天")
        
        # 在途不足
        if daily_demand > 0 and total_in_transit < rop * 0.5:
            recs.append("在途不足：建议加快采购")
        
        # 滞销建议
        if not is_active and inventory > 0:
            recs.append("滞销物料：考虑促销或清理库存")
        
        # 过量库存
        if daily_demand > 0:
            dos = inventory / daily_demand
            if dos > 180:
                recs.append(f"过量库存：周转{dos:.0f}天，建议促销")
        
        if recs:
            recommendations.append({
                "_part_no": part_no,
                "level": level,
                "recommendation": "; ".join(recs)
            })
    
    return pd.DataFrame(recommendations)


def run_health_diagnostic(include_demand: bool = True) -> dict:
    """
    执行库存健康诊断
    
    Args:
        include_demand: 是否计算需求相关指标
    
    Returns:
        dict: 包含健康诊断数据
    """
    print("=" * 60)
    print("开始库存健康诊断分析")
    print("=" * 60)
    
    # 1. 获取数据底座
    print("\n[1/4] 加载数据底座...")
    master_df = run_health_data_pipeline()
    
    if master_df.empty:
        print("错误: 数据底座为空")
        return {"error": "数据底座为空"}
    
    print(f"物料总数: {len(master_df)}")
    
    # 2. 加载库存数据
    print("\n[2/4] 加载库存数据...")
    inventory_df = load_inventory_position()
    
    if not inventory_df.empty:
        master_df = master_df.merge(inventory_df, on="_part_no", how="left")
        master_df["inventory_qty"] = master_df["inventory_qty"].fillna(0)
        # 确保part_name存在
        if "part_name" not in master_df.columns:
            master_df["part_name"] = ""
        else:
            master_df["part_name"] = master_df["part_name"].fillna("")
        # 确保_unit_price存在
        if "_unit_price" not in master_df.columns:
            master_df["_unit_price"] = 0
        else:
            master_df["_unit_price"] = master_df["_unit_price"].fillna(0)
    else:
        master_df["inventory_qty"] = 0
        master_df["part_name"] = ""
        master_df["_unit_price"] = 0
    
    # 3. 加载需求指标（优先使用预测数据，回退到销售历史计算）
    if include_demand:
        print("\n[3/4] 计算需求指标...")
        
        # 3.1 首先尝试加载预测数据
        forecast_df = load_forecast_data()
        
        if not forecast_df.empty:
            print(f"预测数据物料数: {len(forecast_df)}")
            # 预测数据包含 next_forecast (日需求)
            forecast_df = forecast_df[["_part_no", "next_forecast", "forecast_monthly"]].copy()
            master_df = master_df.merge(forecast_df, on="_part_no", how="left")
        
        # 3.2 对于没有预测数据的物料，使用销售历史计算
        sales_df = load_sales_for_demand_calc()
        
        if not sales_df.empty:
            # 批量计算需求指标（仅对没有预测数据的物料）
            part_list = master_df["_part_no"].unique()
            
            # 使用向量化方法加速
            demand_data = []
            for part in part_list[:5000]:  # 限制处理数量
                # 跳过已有预测数据的物料
                if not forecast_df.empty and part in forecast_df["_part_no"].values:
                    continue
                
                part_sales = sales_df[sales_df["_part_no"] == part]
                if len(part_sales) > 0:
                    # 最近90天
                    cutoff = part_sales["date"].max() - timedelta(days=90)
                    recent = part_sales[part_sales["date"] >= cutoff]
                    
                    if len(recent) > 0:
                        total_qty = recent["quantity"].sum()
                        
                        # 正确的计算逻辑：
                        # 1. 先算月均需求 = 90天总销量 / 3
                        # 2. 再算日均需求 = 月均需求 / 30 = 90天总销量 / 90
                        monthly_demand = total_qty / 3  # 90天 = 3个月
                        daily_demand = monthly_demand / 30  # 日均需求
                        
                        # 标准差：使用日均需求的50%作为默认值
                        demand_std = daily_demand * 0.5
                        
                        demand_data.append({
                            "_part_no": part,
                            "daily_demand_fallback": daily_demand,
                            "demand_std": demand_std
                        })
            
            demand_df = pd.DataFrame(demand_data)
            if not demand_df.empty:
                master_df = master_df.merge(demand_df, on="_part_no", how="left")
        
        # 3.3 合并需求数据
        # 优先使用预测数据，否则使用销售历史计算
        if "next_forecast" in master_df.columns:
            master_df["daily_demand"] = master_df["next_forecast"].fillna(0)
            # 如果预测数据为空，使用回退计算
            master_df.loc[master_df["daily_demand"] == 0, "daily_demand"] = master_df.loc[master_df["daily_demand"] == 0, "daily_demand_fallback"].fillna(0)
        elif "daily_demand_fallback" in master_df.columns:
            master_df["daily_demand"] = master_df["daily_demand_fallback"].fillna(0)
        else:
            master_df["daily_demand"] = 0
        
        if "demand_std" not in master_df.columns:
            master_df["demand_std"] = master_df["daily_demand"] * 0.5
        else:
            master_df["demand_std"] = master_df["demand_std"].fillna(master_df["daily_demand"] * 0.5)
        
        # 清理临时列
        if "next_forecast" in master_df.columns:
            master_df = master_df.drop(columns=["next_forecast", "forecast_monthly"], errors="ignore")
        if "daily_demand_fallback" in master_df.columns:
            master_df = master_df.drop(columns=["daily_demand_fallback"], errors="ignore")
    else:
        master_df["daily_demand"] = 0
        master_df["demand_std"] = 0
    
    # 填充需求默认值
    master_df["daily_demand"] = master_df["daily_demand"].fillna(0)
    master_df["demand_std"] = master_df["demand_std"].fillna(0)
    
    # 4. 计算健康诊断指标
    print("\n[4/4] 计算健康诊断指标...")
    
    # 安全库存
    master_df["safety_stock"] = master_df.apply(calculate_safety_stock, axis=1)
    
    # 再订货点
    master_df["rop"] = master_df.apply(calculate_rop, axis=1)
    
    # 库存周转天数
    master_df["days_of_supply"] = master_df.apply(calculate_days_of_supply, axis=1)
    
    # 健康评分（使用新的三类分类）
    health_results = master_df.apply(calculate_health_classification, axis=1)
    master_df["health_level"] = [r[0] for r in health_results]
    master_df["health_reason"] = [r[1] for r in health_results]
    master_df["overstock_qty"] = [r[2] for r in health_results]
    master_df["stockout_qty"] = [r[3] for r in health_results]
    
    # 保留分数用于排序
    master_df["health_score"] = master_df.apply(
        lambda x: 80 if x["health_level"] == "正常" else (30 if x["health_level"] == "缺货预警" else 20),
        axis=1
    )
    
    # ===== 添加完整计算字段 =====
    
    # 1. 总库存 = 在库库存 + 在途库存
    if "total_in_transit" in master_df.columns:
        master_df["total_inventory"] = master_df["inventory_qty"] + master_df["total_in_transit"]
    else:
        master_df["total_inventory"] = master_df["inventory_qty"]
    
    # 2. 最大库存 = ROP × 1.25
    master_df["max_inventory"] = master_df["rop"] * 1.25
    
    # 3. 建议补货量 = 缺货数量（需要补到安全库存）
    master_df["suggested_reorder_qty"] = master_df["stockout_qty"]
    
    # 4. 建议处理量 = 积压数量（需要促销或清理）
    master_df["suggested_process_qty"] = master_df["overstock_qty"]
    
    # 5. 月需求 = 日需求 × 30
    master_df["monthly_demand"] = master_df["daily_demand"] * 30
    
    # 6. 服务系数转换为百分比显示
    if "sla" in master_df.columns:
        master_df["sla_pct"] = (master_df["sla"] * 100).round(1)
    
    # ===== 数量字段四舍五入取整数（除了日均需求）=====
    qty_columns = [
        "safety_stock", "rop", "max_inventory",
        "suggested_reorder_qty", "suggested_process_qty",
        "overstock_qty", "stockout_qty",
        "total_inventory", "inventory_qty", "total_in_transit"
    ]
    for col in qty_columns:
        if col in master_df.columns:
            master_df[col] = master_df[col].round().astype(int)
    
    # 生成建议
    recommendations_df = generate_recommendations(master_df)
    
    # 合并建议
    if not recommendations_df.empty:
        master_df = master_df.merge(recommendations_df, on="_part_no", how="left")
    master_df["recommendation"] = master_df["recommendation"].fillna("")
    
    # ===== 清理重复列 =====
    # 处理 part_name 重复列
    if "part_name_x" in master_df.columns and "part_name_y" in master_df.columns:
        # 优先使用 part_name_x，如果没有则用 part_name_y
        master_df["part_name"] = master_df["part_name_x"].fillna(master_df["part_name_y"])
        master_df = master_df.drop(columns=["part_name_x", "part_name_y"], errors="ignore")
    elif "part_name_x" in master_df.columns:
        master_df["part_name"] = master_df["part_name_x"]
        master_df = master_df.drop(columns=["part_name_x"], errors="ignore")
    elif "part_name_y" in master_df.columns:
        master_df["part_name"] = master_df["part_name_y"]
        master_df = master_df.drop(columns=["part_name_y"], errors="ignore")
    
    # 处理 _unit_price 重复列
    # 优先使用 _unit_price_y（来自 load_inventory_position 的正确计算：总价/数量）
    # _unit_price_x 来自 run_health_data_pipeline 的错误计算（已被移除）
    if "_unit_price_y" in master_df.columns:
        master_df["_unit_price"] = master_df["_unit_price_y"].fillna(0)
        master_df = master_df.drop(columns=["_unit_price_x", "_unit_price_y"], errors="ignore")
    elif "_unit_price_x" in master_df.columns:
        master_df["_unit_price"] = master_df["_unit_price_x"].fillna(0)
        master_df = master_df.drop(columns=["_unit_price_x"], errors="ignore")
    
    # 处理 next_forecast 和 forecast_monthly 重复列
    for prefix in ["next_forecast", "forecast_monthly"]:
        x_col = f"{prefix}_x"
        y_col = f"{prefix}_y"
        if x_col in master_df.columns and y_col in master_df.columns:
            master_df[prefix] = master_df[x_col].fillna(master_df[y_col])
            master_df = master_df.drop(columns=[x_col, y_col], errors="ignore")
        elif x_col in master_df.columns:
            master_df[prefix] = master_df[x_col]
            master_df = master_df.drop(columns=[x_col], errors="ignore")
        elif y_col in master_df.columns:
            master_df[prefix] = master_df[y_col]
            master_df = master_df.drop(columns=[y_col], errors="ignore")
    
    # 确保 part_name 和 _unit_price 存在
    if "part_name" not in master_df.columns:
        master_df["part_name"] = ""
    if "_unit_price" not in master_df.columns:
        master_df["_unit_price"] = 0.0
    
    # ===== 数量字段四舍五入取整数（除了日均需求）=====
    qty_columns = [
        "safety_stock", "rop", "max_inventory",
        "suggested_reorder_qty", "suggested_process_qty",
        "overstock_qty", "stockout_qty",
        "total_inventory", "inventory_qty", "total_in_transit"
    ]
    for col in qty_columns:
        if col in master_df.columns:
            master_df[col] = master_df[col].round().astype('Int64')
    
    # ===== 计算积压和缺货总价 =====
    # 计算单价 = 总价 / 库存数量
    # 直接使用已有的_total_value列（已经从load_inventory_position正确计算）
    if "_total_value" in master_df.columns:
        total_value = master_df["_total_value"].sum()
        
        # 计算积压物料的处理成本 = 多余的库存 × 单价
        # overstock_qty = 当前库存 - 最大库存（超过最大库存的数量）
        if "_unit_price" in master_df.columns and "overstock_qty" in master_df.columns:
            # 处理成本 = overstock_qty × 单价
            master_df["_process_cost"] = master_df["overstock_qty"] * master_df["_unit_price"]
            master_df["_process_cost"] = master_df["_process_cost"].fillna(0)
            overstock_mask = master_df["health_level"] == "积压"
            overstock_value = master_df.loc[overstock_mask, "_process_cost"].sum()
        else:
            # 如果没有单价，则用当前库存价值
            overstock_mask = master_df["health_level"] == "积压"
            overstock_value = master_df.loc[overstock_mask, "_total_value"].sum()
        
        # 计算缺货预警的补货成本 = 需要补货的数量 × 单价
        # stockout_qty = 安全库存 - 当前库存（需要补到安全库存的数量）
        if "_unit_price" in master_df.columns and "stockout_qty" in master_df.columns:
            # 补货成本 = stockout_qty × 单价
            master_df["_reorder_cost"] = master_df["stockout_qty"] * master_df["_unit_price"]
            master_df["_reorder_cost"] = master_df["_reorder_cost"].fillna(0)
            stockout_mask = master_df["health_level"] == "缺货预警"
            stockout_value = master_df.loc[stockout_mask, "_reorder_cost"].sum()
        else:
            # 如果没有单价，则用当前库存价值
            stockout_mask = master_df["health_level"] == "缺货预警"
            stockout_value = master_df.loc[stockout_mask, "_total_value"].sum()
        
        # 计算正常物料的库存价值
        normal_mask = master_df["health_level"] == "正常"
        normal_value = master_df.loc[normal_mask, "_total_value"].sum()
    elif "_unit_price" in master_df.columns and "inventory_qty" in master_df.columns:
        # 备用：如果没有_total_value列，则重新计算
        master_df["_calc_unit_price"] = master_df.apply(
            lambda row: row["_unit_price"] / row["inventory_qty"] 
            if pd.notna(row["_unit_price"]) and pd.notna(row["inventory_qty"]) and row["inventory_qty"] > 0 
            else 0, axis=1
        )
        master_df["_total_value"] = master_df["inventory_qty"] * master_df["_calc_unit_price"]
        total_value = master_df["_total_value"].sum()
        
        overstock_mask = master_df["health_level"] == "积压"
        overstock_value = master_df.loc[overstock_mask, "_total_value"].sum()
        
        stockout_mask = master_df["health_level"] == "缺货预警"
        stockout_value = master_df.loc[stockout_mask, "_total_value"].sum()
        
        normal_mask = master_df["health_level"] == "正常"
        normal_value = master_df.loc[normal_mask, "_total_value"].sum()
    else:
        total_value = 0
        overstock_value = 0
        stockout_value = 0
        normal_value = 0
    
    # 统计汇总（使用新的三类分类）
    stats = {
        "total_parts": len(master_df),
        "overstock_parts": len(master_df[master_df["health_level"] == "积压"]),
        "stockout_parts": len(master_df[master_df["health_level"] == "缺货预警"]),
        "normal_parts": len(master_df[master_df["health_level"] == "正常"]),
        "parts_need_reorder": len(master_df[master_df["health_level"] == "缺货预警"]),
        "parts_overstock": len(master_df[master_df["health_level"] == "积压"]),
        "overstock_value": overstock_value,
        "stockout_value": stockout_value,
        "normal_value": normal_value,
        "total_value": total_value,
    }
    
    print("\n" + "=" * 60)
    print("库存健康诊断完成")
    print("=" * 60)
    print(f"总物料数: {stats['total_parts']}")
    print(f"正常: {stats['normal_parts']} | 缺货预警: {stats['stockout_parts']} | 积压: {stats['overstock_parts']}")
    
    return {
        "data": master_df,
        "stats": stats
    }


if __name__ == "__main__":
    result = run_health_diagnostic()
    
    if "error" not in result:
        print("\n=== 健康诊断结果示例 ===")
        print(result["data"][["_part_no", "inventory_qty", "daily_demand", "safety_stock", "rop", 
                              "days_of_supply", "health_score", "health_level"]].head(20))
