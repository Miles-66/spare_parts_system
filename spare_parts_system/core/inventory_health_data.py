"""
库存健康诊断数据底座 (Inventory Health Data Foundation)

功能：
1. 交期数据（Lead Time）清洗与聚合
2. 服务系数（SLA）数据加载
3. 销售活跃度修正
4. 动态运行数据集成

数据源：
- 交期表.xlsx
- 备件服务系数分类050812 (1).xlsx
- miles新可用的子公司备件订单明细
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import sys
import os

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent.parent))

# 数据目录 - 支持 OSS 和本地模式
USE_OSS = os.environ.get("USE_OSS", "false").lower() == "true"

# 本地路径（备用）
LOCAL_INVENTORY_DIR = Path("D:/spare_parts_system/data_source/inventory")
LOCAL_SALES_DIR = Path("D:/spare_parts_system/data_source/sales")

# 常量配置
DEFAULT_BASE_LT = 70  # 默认基础交期（天）
DEFAULT_LT_STD = 30   # 默认标准差
SHIPPING_OFFSET = 50  # 海运固定周期
DEFAULT_SLA = 0.90    # 默认服务系数 (Z=1.28)
SALES_CUTOFF_DATE = pd.Timestamp("2024-10-01")  # 销售活跃度截止日期


def is_valid_file(filename: str) -> bool:
    """检查是否为有效文件"""
    return not filename.startswith("~")


def read_excel_oss(file_key: str) -> pd.DataFrame:
    """从OSS读取Excel文件"""
    from config import read_excel_from_oss
    return read_excel_from_oss(file_key)


def load_lead_time_data() -> pd.DataFrame:
    """
    加载交期数据
    
    异常值过滤：剔除交货周期 > 400 的记录
    聚合计算：按物料号计算平均交期和标准差
    兜底规则：若物料不存在或无效，Base_LT=70天，标准差=30天
    
    Returns:
        DataFrame: 包含 part_no, base_lt, lt_std, final_lt
    """
    print("=== 加载交期数据 ===")
    
    files = [f for f in Path(INVENTORY_DATA_DIR).glob("*交期*.xlsx") if is_valid_file(f.name)]
    if not files:
        print("警告: 未找到交期表文件")
        return pd.DataFrame()
    
    df = pd.read_excel(max(files, key=lambda x: x.stat().st_mtime))
    print(f"原始记录: {len(df)} 条")
    
    # 转换日期
    df["下单日期"] = pd.to_datetime(df["下单日期"], errors="coerce")
    df["装箱日期"] = pd.to_datetime(df["装箱日期"], errors="coerce")
    
    # 计算交货周期（天）
    df["lead_time"] = (df["装箱日期"] - df["下单日期"]).dt.days
    
    # 过滤异常值：剔除交期 > 400 或 < 0 的记录
    df = df[(df["lead_time"] > 0) & (df["lead_time"] <= 400)]
    print(f"过滤异常值后: {len(df)} 条")
    
    # 标准化物料号
    df["_part_no"] = df["物料号"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    
    # 按物料号聚合
    lt_summary = df.groupby("_part_no").agg({
        "lead_time": ["mean", "std", "count"]
    }).reset_index()
    lt_summary.columns = ["_part_no", "base_lt", "lt_std", "count"]
    
    # 填充无效标准差
    lt_summary["lt_std"] = lt_summary["lt_std"].fillna(DEFAULT_LT_STD)
    
    # 应用兜底规则
    lt_summary["base_lt"] = lt_summary["base_lt"].fillna(DEFAULT_BASE_LT)
    lt_summary["lt_std"] = lt_summary["lt_std"].fillna(DEFAULT_LT_STD)
    
    # 计算最终交期（Base_LT + 海运偏移）
    lt_summary["final_lt"] = lt_summary["base_lt"] + SHIPPING_OFFSET
    
    print(f"交期数据物料数: {len(lt_summary)}")
    
    return lt_summary[["_part_no", "base_lt", "lt_std", "final_lt"]]


def load_sla_data() -> pd.DataFrame:
    """
    加载服务系数数据
    
    字段：PartNumber (物料号), Alt Part # (原物料号), 服务系数
    默认服务系数: 90% (Z=1.28)
    
    Returns:
        DataFrame: 包含 part_no, sla
    """
    print("=== 加载服务系数数据 ===")
    
    files = [f for f in Path(INVENTORY_DATA_DIR).glob("*服务系数*.xlsx") if is_valid_file(f.name)]
    if not files:
        print("警告: 未找到服务系数表文件")
        return pd.DataFrame()
    
    df = pd.read_excel(max(files, key=lambda x: x.stat().st_mtime), sheet_name=0)
    print(f"原始记录: {len(df)} 条")
    
    # 标准化物料号
    df["_part_no"] = df["PartNumber"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    
    # 处理服务系数
    df["sla"] = pd.to_numeric(df["服务系数"], errors="coerce")
    df["sla"] = df["sla"].fillna(DEFAULT_SLA)
    
    # 去重（保留第一条）
    sla_df = df.drop_duplicates(subset=["_part_no"], keep="first")
    
    print(f"服务系数物料数: {len(sla_df)}")
    
    return sla_df[["_part_no", "sla"]]


def load_sales_activity() -> pd.DataFrame:
    """
    加载销售活跃度数据
    
    检查2024-10-01之后是否有销售记录
    无销售记录 -> is_active = False
    
    Returns:
        DataFrame: 包含 part_no, is_active
    """
    print("=== 加载销售活跃度数据 ===")
    
    files = [f for f in Path(SALES_DATA_DIR).glob("*订单明细*.xlsx") if is_valid_file(f.name)]
    if not files:
        print("警告: 未找到销售订单明细文件")
        return pd.DataFrame()
    
    # 获取最新的文件
    latest_file = max(files, key=lambda x: x.stat().st_mtime)
    df = pd.read_excel(latest_file)
    print(f"原始记录: {len(df)} 条")
    
    # 跳过前3列元数据
    if len(df.columns) > 3:
        df = df.iloc[:, 3:].copy()
    
    # 标准化列名
    df.columns = [str(c).strip() for c in df.columns]
    
    # 查找日期列
    date_col = None
    for col in df.columns:
        if "时间" in col or "日期" in col:
            date_col = col
            break
    
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        # 筛选2024-10-01之后的记录
        df = df[df[date_col] >= SALES_CUTOFF_DATE]
        print(f"2024-10-01之后记录: {len(df)} 条")
    
    # 标准化物料号
    part_col = None
    for col in df.columns:
        if "物料号" in col or "备件号" in col:
            part_col = col
            break
    
    if not part_col:
        print("错误: 未找到物料号列")
        return pd.DataFrame()
    
    df["_part_no"] = df[part_col].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    
    # 获取有销售记录的物料
    active_parts = df["_part_no"].unique()
    
    # 创建完整物料列表（从其他表获取）
    result = pd.DataFrame({"_part_no": active_parts})
    result["is_active"] = True
    
    print(f"活跃物料数: {len(result)}")
    
    return result


def load_inventory_tracking_data() -> pd.DataFrame:
    """
    加载广义在途库存数据
    
    从库存追踪引擎获取 Stage 1-4 的汇总值
    
    Returns:
        DataFrame: 包含 part_no, total_in_transit
    """
    print("=== 加载在途库存数据 ===")
    
    # 尝试从引擎获取
    try:
        from core.inventory_engine import run_inventory_pipeline
        result = run_inventory_pipeline()
        if result and "summary" in result:
            df = result["summary"]
            df = df[["_part_no", "_total_in_transit"]].copy()
            df.columns = ["_part_no", "total_in_transit"]
            print(f"在途库存物料数: {len(df)}")
            return df
    except Exception as e:
        print(f"警告: 无法从引擎加载在途数据: {e}")
    
    return pd.DataFrame()


def load_inventory_master_data() -> pd.DataFrame:
    """
    加载库存主数据（物料描述和价格）
    
    从库存数据文件中提取物料号、物料描述、单价信息
    
    Returns:
        DataFrame: 包含 _part_no, part_name, _unit_price
    """
    print("=== 加载库存主数据 ===")
    
    # 搜索库存相关文件
    inventory_dir = Path(INVENTORY_DATA_DIR)
    if not inventory_dir.exists():
        print("警告: 库存目录不存在")
        return pd.DataFrame()
    
    # 优先选择包含"库存"的文件
    stock_files = [f for f in inventory_dir.glob("*库存*.xlsx") if is_valid_file(f.name)]
    
    if not stock_files:
        print("警告: 未找到库存数据文件")
        return pd.DataFrame()
    
    try:
        df = pd.read_excel(max(stock_files, key=lambda x: x.stat().st_mtime))
        print(f"原始记录: {len(df)} 条")
        
        # 查找列
        part_col = None
        desc_col = None
        price_col = None
        
        for col in df.columns:
            col_str = str(col)
            if "物料号" in col_str or "备件号" in col_str or "Part" in col_str:
                part_col = col
            # 优先使用"物料描述"，避免匹配到"存储地点描述"等
            if desc_col is None and col == "物料描述":
                desc_col = col
            elif desc_col is None and "物料描述" in col_str:
                desc_col = col
            if "总价" in col_str or "价格" in col_str or "Price" in col_str:
                price_col = col
        
        print(f"  物料描述列: {desc_col}")
        print(f"  价格列: {price_col}")
        
        if not part_col:
            print("警告: 未找到物料号列")
            return pd.DataFrame()
        
        # 标准化物料号
        part_no_col = df[part_col].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
        
        # 构建结果DataFrame - 只保留物料号和描述
        # 注意：单价计算应该由 load_inventory_position 处理
        # 因为单价 = 总价 / 数量，需要在有库存数量的情况下才能正确计算
        result_data = {"_part_no": part_no_col}
        
        if desc_col:
            result_data["part_name"] = df[desc_col]
        
        result_df = pd.DataFrame(result_data)
        
        # 按物料号聚合：描述取第一个
        agg_dict = {}
        if "part_name" in result_df.columns:
            agg_dict["part_name"] = "first"
        
        # 只有当有描述列时才聚合
        if agg_dict:
            result_df = result_df.groupby("_part_no").agg(agg_dict).reset_index()
        
        # 填充默认值
        if "part_name" not in result_df.columns:
            result_df["part_name"] = ""
        else:
            result_df["part_name"] = result_df["part_name"].fillna("")
        
        # 去重
        result_df = result_df.drop_duplicates(subset=["_part_no"], keep="first")
        
        print(f"库存主数据物料数: {len(result_df)}")
        
        # 只返回物料号和描述，不返回单价
        # 单价由 load_inventory_position 正确计算
        return result_df[["_part_no", "part_name"]]
    
    except Exception as e:
        print(f"警告: 无法加载库存主数据: {e}")
        return pd.DataFrame()


def load_forecast_data() -> pd.DataFrame:
    """
    加载预测数据
    
    从预测引擎缓存获取最优预测值 _next_forecast
    
    Returns:
        DataFrame: 包含 _part_no, next_forecast (月度预测值)
    """
    print("=== 加载预测数据 ===")
    
    # 预测缓存目录
    forecast_dir = Path("D:/spare_parts_system/cache/forecast")
    
    if not forecast_dir.exists():
        print("警告: 预测缓存目录不存在")
        return pd.DataFrame()
    
    # 查找最新的预测缓存文件
    parquet_files = list(forecast_dir.glob("forecast_latest.parquet"))
    
    if not parquet_files:
        print("警告: 未找到预测缓存文件")
        return pd.DataFrame()
    
    try:
        df = pd.read_parquet(parquet_files[0])
        print(f"预测数据记录: {len(df)} 条")
        
        # 检查是否有 _next_forecast 字段
        if "_next_forecast" not in df.columns:
            print("警告: 预测数据中没有 _next_forecast 字段")
            return pd.DataFrame()
        
        # 标准化物料号
        df["_part_no"] = df["_part_no"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
        
        # 提取需要的字段
        forecast_df = df[["_part_no", "_next_forecast"]].copy()
        forecast_df = forecast_df.rename(columns={"_next_forecast": "forecast_monthly"})
        
        # 将月度预测转换为日需求
        forecast_df["next_forecast"] = forecast_df["forecast_monthly"] / 30
        
        # 去重（保留第一个）
        forecast_df = forecast_df.drop_duplicates(subset=["_part_no"], keep="first")
        
        print(f"预测数据物料数: {len(forecast_df)}")
        
        return forecast_df[["_part_no", "next_forecast", "forecast_monthly"]]
    
    except Exception as e:
        print(f"警告: 无法加载预测数据: {e}")
        return pd.DataFrame()


def build_inventory_master(
    lead_time_df: pd.DataFrame = None,
    sla_df: pd.DataFrame = None,
    sales_activity_df: pd.DataFrame = None,
    in_transit_df: pd.DataFrame = None,
    forecast_df: pd.DataFrame = None,
    inventory_master_df: pd.DataFrame = None
) -> pd.DataFrame:
    """
    构建库存主表 - 整合所有数据源
    
    Args:
        lead_time_df: 交期数据
        sla_df: 服务系数数据
        sales_activity_df: 销售活跃度数据
        in_transit_df: 在途库存数据
        forecast_df: 预测数据
        inventory_master_df: 库存主数据（物料描述、价格）
    
    Returns:
        DataFrame: 库存主表
    """
    print("=== 构建库存主表 ===")
    
    # 获取所有物料号的并集
    all_parts = set()
    for df in [lead_time_df, sla_df, sales_activity_df, in_transit_df, forecast_df, inventory_master_df]:
        if df is not None and not df.empty:
            all_parts.update(df["_part_no"].unique())
    
    master_df = pd.DataFrame({"_part_no": list(all_parts)})
    print(f"总物料数: {len(master_df)}")
    
    # 合并各数据源
    if lead_time_df is not None and not lead_time_df.empty:
        master_df = master_df.merge(lead_time_df, on="_part_no", how="left")
    
    if sla_df is not None and not sla_df.empty:
        master_df = master_df.merge(sla_df, on="_part_no", how="left")
    
    if sales_activity_df is not None and not sales_activity_df.empty:
        master_df = master_df.merge(sales_activity_df, on="_part_no", how="left")
    
    if in_transit_df is not None and not in_transit_df.empty:
        master_df = master_df.merge(in_transit_df, on="_part_no", how="left")
    
    if forecast_df is not None and not forecast_df.empty:
        master_df = master_df.merge(forecast_df, on="_part_no", how="left")
    
    # 合并库存主数据（物料描述、价格）
    if inventory_master_df is not None and not inventory_master_df.empty:
        master_df = master_df.merge(inventory_master_df, on="_part_no", how="left")
    
    # 添加预测列（如果不存在）
    if "next_forecast" not in master_df.columns:
        master_df["next_forecast"] = 0.0
    if "forecast_monthly" not in master_df.columns:
        master_df["forecast_monthly"] = 0.0
    
    # 添加库存主数据列（如果不存在）
    if "part_name" not in master_df.columns:
        master_df["part_name"] = ""
    if "_unit_price" not in master_df.columns:
        master_df["_unit_price"] = 0.0
    
    # 应用兜底值
    master_df["base_lt"] = master_df["base_lt"].fillna(DEFAULT_BASE_LT)
    master_df["lt_std"] = master_df["lt_std"].fillna(DEFAULT_LT_STD)
    master_df["final_lt"] = master_df["final_lt"].fillna(DEFAULT_BASE_LT + SHIPPING_OFFSET)
    master_df["sla"] = master_df["sla"].fillna(DEFAULT_SLA)
    master_df["is_active"] = master_df["is_active"].fillna(False)
    master_df["total_in_transit"] = master_df["total_in_transit"].fillna(0)
    master_df["next_forecast"] = master_df["next_forecast"].fillna(0)
    
    # 应用销售活跃度惩罚：无销售记录 -> SLA = 0
    master_df.loc[master_df["is_active"] == False, "sla"] = 0
    
    print(f"库存主表构建完成: {len(master_df)} 条")
    
    return master_df


def run_health_data_pipeline():
    """
    执行完整的数据底座流水线
    
    Returns:
        DataFrame: 库存主表
    """
    print("=" * 60)
    print("开始构建库存健康诊断数据底座")
    print("=" * 60)
    
    # 1. 加载交期数据
    lead_time_df = load_lead_time_data()
    
    # 2. 加载服务系数
    sla_df = load_sla_data()
    
    # 3. 加载销售活跃度
    sales_activity_df = load_sales_activity()
    
    # 4. 加载在途库存（可选）
    in_transit_df = load_inventory_tracking_data()
    
    # 5. 加载预测数据（可选）
    forecast_df = load_forecast_data()
    
    # 6. 加载库存主数据（物料描述、价格）
    inventory_master_df = load_inventory_master_data()
    
    # 7. 构建主表
    master_df = build_inventory_master(
        lead_time_df=lead_time_df,
        sla_df=sla_df,
        sales_activity_df=sales_activity_df,
        in_transit_df=in_transit_df,
        forecast_df=forecast_df,
        inventory_master_df=inventory_master_df
    )
    
    return master_df


if __name__ == "__main__":
    # 测试运行
    df = run_health_data_pipeline()
    print("\n=== 库存主表示例 ===")
    print(df.head(10))
    print(f"\n总记录数: {len(df)}")
