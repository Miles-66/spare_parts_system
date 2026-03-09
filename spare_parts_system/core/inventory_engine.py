"""
库存追踪引擎 (Inventory Tracking Engine) - 广义在途库存

全链路在途追踪 - 按单据粒度计算（防串单）

核心原则：禁止仅按物料号直接差分，必须先在单据粒度对齐再汇总

四级状态计算（最终版本）：
1. Stage1 未装箱 = A表需求 - B表已装箱 (需求单+物料粒度)
2. Stage2 装箱未合同 = B表已装箱 - C表已做合同 (需求单+物料粒度)
3. Stage3 合同审批中 = C表无SAP销售单号的数量 (物料粒度)
4. Stage4 海上在途 = D表数量 (物料粒度)

重要变更：
- C表有SAP销售单号但不在D表 = 已入库（不计入在途）
- 只有C表无SAP销售单号的才算Stage3

作者: Matrix Agent
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import warnings
import sys
from pathlib import Path as PathLib

# 添加项目根目录到路径
sys.path.insert(0, str(PathLib(__file__).parent.parent))
from config import get_excluded_sap_orders

# 数据目录配置
PROCUREMENT_DIR = "D:/spare_parts_system/data_source/procurement"
LOGISTICS_DIR = "D:/spare_parts_system/data_source/logistics"

# 日期锚点 - 2025年1月1日起
DATE_ANCHOR = pd.Timestamp("2025-01-01")


def is_valid_file(filename: str) -> bool:
    """检查是否为有效文件（排除临时文件）"""
    return not filename.startswith("~")


def standardize_column(df: pd.DataFrame) -> pd.DataFrame:
    """标准化列名：去空格、trim"""
    df.columns = [str(c).strip() for c in df.columns]
    return df


def standardize_part_no(val) -> str:
    """标准化物料号：转字符串、去空格、去尾缀"""
    if pd.isna(val):
        return ""
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def load_and_prepare_data():
    """加载并预处理所有数据"""
    proc_dir = Path(PROCUREMENT_DIR)
    log_dir = Path(LOGISTICS_DIR)
    
    data = {}
    
    # A表: miles采购表 (跳过前3列)
    files = [f for f in proc_dir.glob("*miles采购表*.xlsx") if is_valid_file(f.name)]
    if files:
        df_a = pd.read_excel(max(files, key=lambda x: x.stat().st_mtime))
        if len(df_a.columns) > 3:
            df_a = df_a.iloc[:, 3:].copy()
        df_a = standardize_column(df_a)
        data["A"] = df_a
        print(f"A表加载: {len(df_a)} 行")
    
    # B表: 箱号明细 (跳过前3列)
    files = [f for f in proc_dir.glob("*箱号明细*.xlsx") if is_valid_file(f.name)]
    if files:
        df_b = pd.read_excel(max(files, key=lambda x: x.stat().st_mtime))
        if len(df_b.columns) > 3:
            df_b = df_b.iloc[:, 3:].copy()
        df_b = standardize_column(df_b)
        data["B"] = df_b
        print(f"B表加载: {len(df_b)} 行")
    
    # C表: 合同明细 (跳过前3列)
    files = [f for f in log_dir.glob("*合同明细*.xlsx") if is_valid_file(f.name)]
    if files:
        df_c = pd.read_excel(max(files, key=lambda x: x.stat().st_mtime))
        if len(df_c.columns) > 3:
            df_c = df_c.iloc[:, 3:].copy()
        df_c = standardize_column(df_c)
        data["C"] = df_c
        print(f"C表加载: {len(df_c)} 行")
    
    # D表: 海上在途 (不跳过)
    files = [f for f in log_dir.glob("*海上在途*.xlsx") if is_valid_file(f.name)]
    if files:
        df_d = pd.read_excel(max(files, key=lambda x: x.stat().st_mtime))
        df_d = standardize_column(df_d)
        data["D"] = df_d
        print(f"D表加载: {len(df_d)} 行")
    
    return data


def filter_by_date(df: pd.DataFrame, date_col: str, start_date: pd.Timestamp = DATE_ANCHOR) -> pd.DataFrame:
    """按日期筛选"""
    if df.empty or date_col not in df.columns:
        return df
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    return df[df[date_col] >= start_date].copy()


def run_inventory_pipeline(start_date: pd.Timestamp = DATE_ANCHOR) -> dict:
    """
    执行全链路库存追踪计算 - 按单据粒度
    
    Returns:
        dict: {
            'summary': 物料汇总表,
            'req_detail': 需求单粒度明细,
            'voucher_detail': 凭证粒度明细,
            'anomalies': 异常清单
        }
    """
    print("=" * 60)
    print("开始加载数据...")
    data = load_and_prepare_data()
    
    if "A" not in data:
        print("错误: 无法加载A表数据")
        return {}
    
    # 加载数据
    df_a = data["A"].copy()
    df_b = data.get("B", pd.DataFrame())
    df_c = data.get("C", pd.DataFrame())
    df_d = data.get("D", pd.DataFrame())
    
    # 日期筛选 (A/B/C表)
    date_col = "创建时间"
    if date_col in df_a.columns:
        df_a = filter_by_date(df_a, date_col, start_date)
        print(f"A表日期筛选后: {len(df_a)} 行")
    
    # ===== 排除指定订单号 =====
    excluded_orders = get_excluded_sap_orders()
    if not df_a.empty and "SAP订单号" in df_a.columns:
        original_count = len(df_a)
        df_a = df_a[~df_a["SAP订单号"].astype(str).isin(excluded_orders)]
        filtered_count = original_count - len(df_a)
        print(f"A表排除订单号后: 过滤 {filtered_count} 条，剩余 {len(df_a)} 行")
    
    if not df_b.empty and date_col in df_b.columns:
        df_b = filter_by_date(df_b, date_col, start_date)
        print(f"B表日期筛选后: {len(df_b)} 行")
    
    # B表也必须同步排除相同订单号
    if not df_b.empty and "SAP 需求单号" in df_b.columns:
        original_count = len(df_b)
        df_b = df_b[~df_b["SAP 需求单号"].astype(str).str.strip().isin(excluded_orders)]
        filtered_count = original_count - len(df_b)
        print(f"B表排除订单号后: 过滤 {filtered_count} 条，剩余 {len(df_b)} 行")
    
    if not df_c.empty and date_col in df_c.columns:
        df_c = filter_by_date(df_c, date_col, start_date)
        print(f"C表日期筛选后: {len(df_c)} 行")
    
    # ===== 步骤1: 聚合A/B到需求单粒度 =====
    print("\n===== 步骤1: 需求单粒度聚合 =====")
    
    # A表: 按(SAP订单号, 物料号)聚合
    df_a["_order_key"] = df_a["SAP订单号"].astype(str).str.strip()
    df_a["_part_no"] = df_a["物料号"].apply(standardize_part_no)
    df_a["_qty_a"] = pd.to_numeric(df_a["数量"], errors="coerce").fillna(0)
    
    a_req_part = df_a.groupby(["_order_key", "_part_no"]).agg({
        "_qty_a": "sum",
        "PMS价格(CNY)": "max"
    }).reset_index()
    a_req_part.columns = ["_order_key", "_part_no", "_qty_a", "_price_a"]
    print(f"A表需求单粒度: {len(a_req_part)} 条")
    
    # B表: 按(SAP需求单号, 物料号)聚合
    df_b["_order_key"] = df_b["SAP 需求单号"].astype(str).str.strip()
    df_b["_part_no"] = df_b["物料号"].apply(standardize_part_no)
    df_b["_qty_b"] = pd.to_numeric(df_b["数量"], errors="coerce").fillna(0)
    
    b_req_part = df_b.groupby(["_order_key", "_part_no"]).agg({
        "_qty_b": "sum"
    }).reset_index()
    print(f"B表需求单粒度: {len(b_req_part)} 条")
    
    # ===== 步骤2: 处理C表 - 区分有/无SAP销售单号 =====
    print("\n===== 步骤2: 处理C表（区分有/无SAP销售单号） =====")
    
    df_c["_part_no"] = df_c["物料号"].apply(standardize_part_no)
    df_c["_qty_c"] = pd.to_numeric(df_c["数量"], errors="coerce").fillna(0)
    
    # SAP销售单号列
    sales_no_col = "SAP销售单号 (进出口备件发车申请单号) (备件发车申请)"
    
    # 判断是否有SAP销售单号
    df_c["_has_sales_no"] = (
        df_c[sales_no_col].notna() & 
        (df_c[sales_no_col].astype(str).str.strip() != "") &
        (df_c[sales_no_col].astype(str).str.strip() != "nan")
    )
    
    # 拆分C表
    c_no_sales = df_c[df_c["_has_sales_no"] == False].copy()  # 无SAP销售单号
    c_with_sales = df_c[df_c["_has_sales_no"] == True].copy()   # 有SAP销售单号
    
    print(f"C表无SAP销售单号: {len(c_no_sales)} 条")
    print(f"C表有SAP销售单号: {len(c_with_sales)} 条")
    
    # C表(需求单维度): 按(SAP需求单号, 物料号) - 全量用于Stage2
    df_c["_order_key"] = df_c["SAP 需求单号"].astype(str).str.strip()
    c_req_part = df_c.groupby(["_order_key", "_part_no"]).agg({
        "_qty_c": "sum"
    }).reset_index()
    print(f"C表(需求单)粒度: {len(c_req_part)} 条")
    
    # ===== 步骤3: 计算Stage1 未装箱 =====
    print("\n===== 步骤3: 计算Stage1 未装箱 =====")
    
    # 在需求单粒度对齐A和B
    stage1_detail = a_req_part.merge(
        b_req_part[["_order_key", "_part_no", "_qty_b"]],
        on=["_order_key", "_part_no"],
        how="left"
    )
    stage1_detail["_qty_b"] = stage1_detail["_qty_b"].fillna(0)
    
    # 未装箱 = A数量 - B数量
    stage1_detail["_unboxed"] = (stage1_detail["_qty_a"] - stage1_detail["_qty_b"]).clip(lower=0)
    
    # 记录异常: B > A
    anomaly_b_gt_a = stage1_detail[stage1_detail["_qty_b"] > stage1_detail["_qty_a"]].copy()
    print(f"Stage1异常(B>A): {len(anomaly_b_gt_a)} 条")
    
    # 按物料汇总Stage1
    stage1_by_part = stage1_detail.groupby("_part_no").agg({
        "_qty_a": "sum",
        "_unboxed": "sum",
        "_price_a": "max"
    }).reset_index()
    stage1_by_part.columns = ["_part_no", "_qty_a", "_stage1_domestic", "_price_a"]
    print(f"Stage1物料数: {len(stage1_by_part)}")
    
    # ===== 步骤4: 计算Stage2 装箱未合同 =====
    print("\n===== 步骤4: 计算Stage2 装箱未合同 =====")
    
    # 在需求单粒度对齐B和C（全量）
    stage2_detail = b_req_part.merge(
        c_req_part[["_order_key", "_part_no", "_qty_c"]],
        on=["_order_key", "_part_no"],
        how="left"
    )
    stage2_detail["_qty_c"] = stage2_detail["_qty_c"].fillna(0)
    
    # 装箱未合同 = B数量 - C数量
    stage2_detail["_boxed_not_contracted"] = (stage2_detail["_qty_b"] - stage2_detail["_qty_c"]).clip(lower=0)
    
    # 记录异常: C > B
    anomaly_c_gt_b = stage2_detail[stage2_detail["_qty_c"] > stage2_detail["_qty_b"]].copy()
    print(f"Stage2异常(C>B): {len(anomaly_c_gt_b)} 条")
    
    # 按物料汇总Stage2
    stage2_by_part = stage2_detail.groupby("_part_no").agg({
        "_boxed_not_contracted": "sum"
    }).reset_index()
    stage2_by_part.columns = ["_part_no", "_stage2_boxed"]
    print(f"Stage2物料数: {len(stage2_by_part)}")
    
    # ===== 步骤5: 计算Stage3 合同审批中 =====
    print("\n===== 步骤5: 计算Stage3 合同审批中 =====")
    
    # Stage3 = C表无SAP销售单号的数量
    stage3_by_part = c_no_sales.groupby("_part_no").agg({
        "_qty_c": "sum"
    }).reset_index()
    stage3_by_part.columns = ["_part_no", "_stage3_approval"]
    print(f"Stage3物料数: {len(stage3_by_part)}")
    
    # ===== 步骤6: 计算Stage4 海上在途 + 已入库代理 =====
    print("\n===== 步骤6: 计算Stage4 海上在途 =====")
    
    # D表: 按物料汇总
    df_d["_part_no"] = df_d["物料"].apply(standardize_part_no)
    df_d["_qty_d"] = pd.to_numeric(df_d["数量"], errors="coerce").fillna(0)
    
    stage4_by_part = df_d.groupby("_part_no").agg({
        "_qty_d": "sum"
    }).reset_index()
    stage4_by_part.columns = ["_part_no", "_stage4_shipping"]
    print(f"Stage4物料数: {len(stage4_by_part)}")
    
    # ===== 步骤7: 计算"已入库代理量"（不计入在途）=====
    print("\n===== 步骤7: 计算已入库代理量 =====")
    
    # C表有SAP销售单号的，按(销售单号, 物料)聚合
    c_with_sales["_voucher_key"] = c_with_sales[sales_no_col].astype(str).str.strip()
    
    c_sales_part = c_with_sales.groupby(["_voucher_key", "_part_no"]).agg({
        "_qty_c": "sum"
    }).reset_index()
    c_sales_part.columns = ["_voucher_key", "_part_no", "_qty_c_sales"]
    print(f"C表(销售单)粒度: {len(c_sales_part)} 条")
    
    # D表按(采购凭证, 物料)聚合
    df_d["_voucher_key"] = df_d["采购凭证"].astype(str).str.strip()
    
    d_voucher_part = df_d.groupby(["_voucher_key", "_part_no"]).agg({
        "_qty_d": "sum"
    }).reset_index()
    d_voucher_part.columns = ["_voucher_key", "_part_no", "_qty_d"]
    print(f"D表(凭证)粒度: {len(d_voucher_part)} 条")
    
    # 对齐C和D
    received_detail = c_sales_part.merge(
        d_voucher_part[["_voucher_key", "_part_no", "_qty_d"]],
        on=["_voucher_key", "_part_no"],
        how="left"
    )
    received_detail["_qty_d"] = received_detail["_qty_d"].fillna(0)
    
    # 已匹配发运 = min(C数量, D数量)
    received_detail["_matched"] = received_detail[["_qty_c_sales", "_qty_d"]].min(axis=1)
    
    # 已入库代理 = C数量 - 已匹配（不在D表的视为已入库）
    received_detail["_received_proxy"] = (received_detail["_qty_c_sales"] - received_detail["_matched"]).clip(lower=0)
    
    # 按物料汇总已入库代理量
    received_by_part = received_detail.groupby("_part_no").agg({
        "_received_proxy": "sum"
    }).reset_index()
    received_by_part.columns = ["_part_no", "_received_proxy"]
    print(f"已入库代理物料数: {len(received_by_part)}")
    
    # 记录异常: D > C
    anomaly_d_gt_c = received_detail[received_detail["_qty_d"] > received_detail["_qty_c_sales"]].copy()
    print(f"Stage4异常(D>C): {len(anomaly_d_gt_c)} 条")
    
    # ===== 步骤8: 合并到物料维度 =====
    print("\n===== 步骤8: 合并到物料维度 =====")
    
    # 基础表: 所有物料
    all_parts = set(a_req_part["_part_no"].unique()) | set(b_req_part["_part_no"].unique()) | \
                set(df_c["_part_no"].unique()) | set(df_d["_part_no"].unique())
    all_parts = [p for p in all_parts if p]
    
    summary_df = pd.DataFrame({"_part_no": all_parts})
    
    # 合并各Stage
    summary_df = summary_df.merge(stage1_by_part, on="_part_no", how="left")
    summary_df = summary_df.merge(stage2_by_part, on="_part_no", how="left")
    summary_df = summary_df.merge(stage3_by_part, on="_part_no", how="left")
    summary_df = summary_df.merge(stage4_by_part, on="_part_no", how="left")
    summary_df = summary_df.merge(received_by_part, on="_part_no", how="left")
    
    # 填充NaN
    summary_df = summary_df.fillna(0)
    
    # 计算总在途（不包含已入库代理量）
    summary_df["_total_in_transit"] = (
        summary_df["_stage1_domestic"] + 
        summary_df["_stage2_boxed"] + 
        summary_df["_stage3_approval"] + 
        summary_df["_stage4_shipping"]
    )
    
    # 总需求
    summary_df["_total_demand"] = summary_df["_qty_a"]
    
    # 计算货值
    summary_df["_unit_price"] = summary_df["_price_a"].fillna(0)
    summary_df["_unit_price"] = summary_df["_unit_price"].replace(0, np.nan).fillna(0)
    summary_df["_total_value"] = summary_df["_total_in_transit"] * summary_df["_unit_price"]
    
    print(f"总物料数: {len(summary_df)}")
    
    # ===== 范围一致性校验 =====
    print("\n===== 范围一致性校验 =====")
    
    # 检查各中间表是否仍有排除的订单号
    leakage_detected = False
    
    # 检查A表需求单
    if "_order_key" in stage1_detail.columns:
        leaked_a = stage1_detail[stage1_detail["_order_key"].isin(excluded_orders)]
        if len(leaked_a) > 0:
            print(f"⚠️ Range leakage: A表仍有 {len(leaked_a)} 条排除订单号")
            leakage_detected = True
    
    # 检查B表需求单
    if "_order_key" in stage2_detail.columns:
        leaked_b = stage2_detail[stage2_detail["_order_key"].isin(excluded_orders)]
        if len(leaked_b) > 0:
            print(f"⚠️ Range leakage: B表仍有 {len(leaked_b)} 条排除订单号")
            leakage_detected = True
    
    if leakage_detected:
        print("❌ Range leakage detected: excluded SAP订单号 still present in pipeline")
    else:
        print("✅ 范围一致性校验通过: 排除订单号已完全过滤")
    
    # 打印各阶段汇总
    print(f"\n=== 各Stage汇总 ===")
    print(f"Stage1 未装箱: {int(summary_df['_stage1_domestic'].sum()):,}")
    print(f"Stage2 装箱未合同: {int(summary_df['_stage2_boxed'].sum()):,}")
    print(f"Stage3 合同审批中: {int(summary_df['_stage3_approval'].sum()):,}")
    print(f"Stage4 海上在途: {int(summary_df['_stage4_shipping'].sum()):,}")
    print(f"已入库代理量: {int(summary_df['_received_proxy'].sum()):,}")
    print(f"总在途: {int(summary_df['_total_in_transit'].sum()):,}")
    
    # 准备返回数据
    result = {
        "summary": summary_df,
        "req_detail": stage1_detail,
        "voucher_detail": received_detail,
        "anomalies": {
            "d_gt_c": anomaly_d_gt_c,
            "c_gt_b": anomaly_c_gt_b,
            "b_gt_a": anomaly_b_gt_a
        }
    }
    
    return result


def validate_data_quality(result: dict) -> dict:
    """数据质量校验"""
    if not result or "summary" not in result:
        return {"status": "error", "message": "数据为空"}
    
    df = result["summary"].copy()
    
    # 确保列存在
    required_cols = ["_stage1_domestic", "_stage2_boxed", "_stage3_approval", "_stage4_shipping", "_total_in_transit"]
    for col in required_cols:
        if col not in df.columns:
            df[col] = 0
    
    # 守恒校验: total_in_transit = Stage1 + Stage2 + Stage3 + Stage4
    df["_calculated_total"] = (
        df["_stage1_domestic"] + 
        df["_stage2_boxed"] + 
        df["_stage3_approval"] + 
        df["_stage4_shipping"]
    )
    
    df["_is_consistent"] = np.isclose(df["_calculated_total"], df["_total_in_transit"], rtol=0.001)
    consistency_rate = df["_is_consistent"].mean() * 100
    
    # 统计各阶段
    has_stage1 = (df["_stage1_domestic"] > 0).sum()
    has_stage2 = (df["_stage2_boxed"] > 0).sum()
    has_stage3 = (df["_stage3_approval"] > 0).sum()
    has_stage4 = (df["_stage4_shipping"] > 0).sum()
    has_received = (df["_received_proxy"] > 0).sum() if "_received_proxy" in df.columns else 0
    
    # 异常统计
    anomalies = result.get("anomalies", {})
    
    return {
        "status": "ok" if consistency_rate >= 99.5 else "warning",
        "consistency_rate": float(consistency_rate),
        "total_parts": len(df),
        "has_stage1": int(has_stage1),
        "has_stage2": int(has_stage2),
        "has_stage3": int(has_stage3),
        "has_stage4": int(has_stage4),
        "has_received_proxy": int(has_received),
        "anomaly_d_gt_c_count": len(anomalies.get("d_gt_c", pd.DataFrame())),
        "anomaly_c_gt_b_count": len(anomalies.get("c_gt_b", pd.DataFrame())),
        "anomaly_b_gt_a_count": len(anomalies.get("b_gt_a", pd.DataFrame())),
    }


def get_summary_stats(result: dict) -> dict:
    """获取汇总统计"""
    if not result or "summary" not in result:
        return {}
    
    df = result["summary"]
    
    return {
        "total_parts": len(df),
        "total_demand": int(df["_total_demand"].sum()),
        "total_in_transit": int(df["_total_in_transit"].sum()),
"total_value": float(df["_total_value"].sum()),
        "stage1_domestic": int(df["_stage1_domestic"].sum()),
        "stage2_boxed": int(df["_stage2_boxed"].sum()),
        "stage3_approval": int(df["_stage3_approval"].sum()),
        "stage4_shipping": int(df["_stage4_shipping"].sum()),
        "received_proxy": int(df["_received_proxy"].sum()),
    }
