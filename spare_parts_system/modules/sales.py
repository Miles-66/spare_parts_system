# -*- coding: utf-8 -*-
"""
销售看板模块（Sales Dashboard）

按照架构师要求：
1. 将数据处理逻辑和UI展示代码分开
2. 先写process_sales_data函数处理所有数据
3. 然后把处理好的结果交给图表函数

视觉布局：
- 第一行：指标卡（总销售额、订单总数、平均现货满足率）
- 第二行：趋势分析（左侧需求满足率按月份柱状图，右侧现货满足率按月份柱状图）
- 第三行：明细排名（客户名称、总销售额、现货满足率、需求满足率，按总销售额排序）
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from core.data_engine import load_orders_data_with_cache, load_shipping_data_with_cache
from core.calculator import (
    process_sales_data,
    calculate_monthly_metrics,
    calculate_customer_metrics,
)
from core.i18n import get_text, get_text_safe
from modules.regional_sales import render_regional_sales


def render_kpi_cards(total_amount: float, total_orders: int, fulfillment_rate: float) -> None:
    """
    渲染第一行：KPI指标卡

    Args:
        total_amount: 总销售额（USD）
        total_orders: 订单总数
        fulfillment_rate: 现货满足率
    """
    st.markdown(f"### {get_text('sales.kpi_title')}")

    # 使用Streamlit的columns布局创建三个指标卡
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            label=get_text("sales.total_sales"),
            value=f"${total_amount:,.2f}",
            delta=None,
        )

    with col2:
        st.metric(
            label=get_text("sales.total_orders"),
            value=f"{total_orders:,}",
            delta=None,
        )

    with col3:
        st.metric(
            label=get_text("sales.avg_fulfillment"),
            value=f"{fulfillment_rate:.2%}",
            delta=None,
        )


def render_monthly_charts(monthly_metrics: dict, curr_lang: str = None) -> None:
    """
    渲染第二行：月度趋势分析图表（销售额趋势 + 现货满足率）

    Args:
        monthly_metrics: 包含月度指标的字典
        curr_lang: 当前语言（可选，默认从session_state获取）
    """
    # 获取当前语言
    if curr_lang is None:
        curr_lang = st.session_state.get("lang", "ZH")
    
    st.markdown(f"### {get_text('sales.monthly_trend')}")

    monthly_fulfillment = monthly_metrics.get("monthly_fulfillment", pd.DataFrame())
    monthly_sales = monthly_metrics.get("monthly_sales", pd.DataFrame())

    # ========== 销售额趋势图（线图） ==========
    if not monthly_sales.empty and "销售额" in monthly_sales.columns:
        trend_title = "💰 " + ("销售额月度趋势" if curr_lang == "ZH" else "Monthly Sales Trend")
        st.markdown(f"#### {trend_title}")
        
        # 创建线图
        fig_sales = px.line(
            monthly_sales,
            x="确认月份",
            y="销售额",
            title=("销售额趋势" if curr_lang == "ZH" else "Sales Trend"),
            markers=True,
        )
        
        # 添加数据标签
        fig_sales.update_traces(
            textposition="top center",
            texttemplate="%{y:$,.2f}",
        )
        
        fig_sales.update_layout(
            hovermode="x unified",
            yaxis_tickformat="$,.2f",
        )
        
        st.plotly_chart(fig_sales, use_container_width=True)
    else:
        no_data_text = "暂无销售额数据" if curr_lang == "ZH" else "No sales data"
        st.info(no_data_text)

    st.markdown("---")

    # ========== 现货满足率趋势图（柱状图带标签） ==========
    if not monthly_fulfillment.empty and "现货满足率" in monthly_fulfillment.columns:
        fulfill_trend_title = "📦 " + ("现货满足率月度趋势" if curr_lang == "ZH" else "Monthly Fulfillment Rate")
        st.markdown(f"#### {fulfill_trend_title}")
        
        fig_fulfill = px.bar(
            monthly_fulfillment,
            x="确认月份",
            y="现货满足率",
            title=("现货满足率趋势" if curr_lang == "ZH" else "Fulfillment Rate Trend"),
            labels={
                "确认月份": get_text("sales.month"),
                "现货满足率": "现货满足率" if curr_lang == "ZH" else "Fulfillment Rate",
            },
            color="现货满足率",
            color_continuous_scale="Greens",
        )

        # 添加数据标签 - 显示百分比，2位小数
        fig_fulfill.update_traces(
            textposition="outside",
            texttemplate="%{y:.2%}",
        )

        fig_fulfill.update_layout(
            yaxis_tickformat=".2%",
            hovermode="x unified",
        )

        st.plotly_chart(fig_fulfill, use_container_width=True)
    else:
        st.info(get_text("sales.no_fulfillment_data"))


def render_customer_table(customer_metrics: pd.DataFrame) -> None:
    """
    渲染第三行：客户明细排名表（只显示现货满足率）

    Args:
        customer_metrics: 按客户汇总的指标表
    """
    st.markdown(f"### {get_text('sales.customer_ranking')}")

    if customer_metrics.empty:
        st.info(get_text("sales.no_customer_data"))
        return

    # 期望的列顺序：客户名称、总销售额(USD)、现货满足率
    expected_columns = ["客户名称", "总销售额(USD)", "现货满足率"]

    # 检查列是否存在
    available_columns = [col for col in expected_columns if col in customer_metrics.columns]

    if not available_columns:
        st.warning(get_text("sales.missing_columns"))
        return

    # 格式化百分比列
    df_display = customer_metrics[available_columns].copy()

    # 格式化百分比
    if "现货满足率" in df_display.columns:
        df_display["现货满足率"] = df_display["现货满足率"].apply(
            lambda x: f"{x:.2%}" if pd.notna(x) and x <= 1 else f"{min(x, 1):.2%}"
        )

    # 格式化金额（USD）
    if "总销售额(USD)" in df_display.columns:
        df_display["总销售额(USD)"] = df_display["总销售额(USD)"].apply(
            lambda x: f"${x:,.2f}" if pd.notna(x) else "$0.00"
        )

    # 使用Streamlit的数据框组件显示
    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
    )

    # 显示客户数参考
    st.caption(get_text_safe("sales.total_customers", count=len(customer_metrics)))


def render_anomaly_samples(processed_df: pd.DataFrame) -> None:
    """
    渲染异常样本明细表

    显示确认时间不为空但判定为不满足的订单明细

    Args:
        processed_df: 处理后的销售数据
    """
    st.markdown("---")
    st.markdown(f"### {get_text('sales.anomaly_analysis')}")

    # 筛选确认时间不为空但判定为不满足的订单
    unsatisfied_df = processed_df[
        (processed_df["确认时间"].notna()) &
        (processed_df["现货满足判定"] == "否")
    ].copy()

    if unsatisfied_df.empty:
        st.success(get_text("sales.all_satisfied"))
        return

    # 按原因分类统计
    no_shipping = unsatisfied_df[unsatisfied_df["shipping_time"].isna()]
    late_shipping = unsatisfied_df[
        (unsatisfied_df["shipping_time"].notna()) &
        (unsatisfied_df["DaysDiff"] < 0)
    ]
    too_slow = unsatisfied_df[
        (unsatisfied_df["shipping_time"].notna()) &
        (unsatisfied_df["DaysDiff"] > 3)
    ]

    # 显示统计信息
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            label=get_text("sales.no_shipping"),
            value=f"{len(no_shipping)}",
            delta=get_text("sales.no_shipping"),
        )
    with col2:
        st.metric(
            label=get_text("sales.late_shipping"),
            value=f"{len(late_shipping)}",
            delta="Time anomaly",
        )
    with col3:
        st.metric(
            label="🐢 >3 days",
            value=f"{len(too_slow)}",
            delta=get_text("sales.slow_response"),
        )

    # 显示10条异常样本
    st.markdown(f"#### {get_text('sales.anomaly_detail')}")

    sample_columns = ["order_id", "确认时间", "shipping_time", "DaysDiff", "现货满足判定"]
    available_columns = [col for col in sample_columns if col in unsatisfied_df.columns]

    if available_columns:
        sample_df = unsatisfied_df[available_columns].head(10).copy()

        # 格式化列
        if "确认时间" in sample_df.columns:
            sample_df["确认时间"] = sample_df["确认时间"].dt.strftime("%Y-%m-%d")
        if "shipping_time" in sample_df.columns:
            sample_df["shipping_time"] = sample_df["shipping_time"].apply(
                lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else "N/A"
            )
        if "DaysDiff" in sample_df.columns:
            sample_df["DaysDiff"] = sample_df["DaysDiff"].apply(
                lambda x: f"{x:.0f}" if pd.notna(x) else "N/A"
            )

        # 重命名列
        column_names = {
            "order_id": "订单号",
            "确认时间": "确认时间",
            "shipping_time": "发货时间",
            "DaysDiff": "天数差",
            "现货满足判定": "判定"
        }
        sample_df = sample_df.rename(columns=column_names)

        st.dataframe(
            sample_df,
            use_container_width=True,
            hide_index=True,
        )

        st.caption(f"共 {len(unsatisfied_df)} 条异常订单（已过滤确认时间为空的订单）")


def render_sales_dashboard() -> None:
    """
    销售看板主函数

    按照架构师要求：
    1. 先调用数据加载函数
    2. 调用process_sales_data处理数据
    3. 将处理结果传递给图表函数
    """
    # 获取当前语言
    curr_lang = st.session_state.get("lang", "ZH")
    
    st.title(get_text("sales.page_title"))
    st.markdown("---")

    # 获取选中的年份（从session_state中获取）
    selected_years = st.session_state.get("selected_years", None)

    # 显示当前筛选条件
    if selected_years:
        years_str = ", ".join([str(y) for y in sorted(selected_years)])
        st.info(get_text_safe("sales.filter_selected_years", years=years_str))
    else:
        st.info(get_text("sales.filter_all_years"))

    # Step 1: 加载数据
    with st.spinner(get_text("sales.loading_sales")):
        orders_df, orders_info = load_orders_data_with_cache()
        shipping_df, shipping_info = load_shipping_data_with_cache()

    # 显示数据加载状态
    if orders_info["status"] != "success":
        st.warning(f"⚠️ {orders_info['message']}")
        return

    if shipping_info["status"] != "success":
        st.warning(f"⚠️ {shipping_info['message']}")
        # 继续使用空的发货表

    # 显示数据源信息
    with st.expander(get_text("common.data_source"), expanded=False):
        st.write(f"{get_text('sales.order_table')}：{orders_info['message']}")
        if shipping_info["status"] == "success":
            st.write(f"{get_text('sales.shipping_table')}：{shipping_info['message']}")
        else:
            st.write(f"{get_text('sales.shipping_table')}：{shipping_info['message']}")

    # Step 2: 处理数据（传递选中的年份）
    with st.spinner(get_text("sales.processing_data")):
        processed_df = process_sales_data(orders_df, shipping_df)

    if processed_df.empty:
        st.error(get_text("sales.data_processing_failed"))
        return

    # Step 3: 计算KPI指标（按选中的年份过滤）
    # 先按年份过滤数据
    if selected_years and len(selected_years) > 0:
        filtered_df = processed_df[
            processed_df["确认时间"].dt.year.isin(selected_years)
        ].copy()
    else:
        filtered_df = processed_df

    # 计算总销售额（USD）- 使用订单表中的amount列
    if "amount" in filtered_df.columns:
        total_amount = pd.to_numeric(
            filtered_df["amount"], errors="coerce"
        ).sum()
        if pd.isna(total_amount):
            total_amount = 0
    else:
        total_amount = 0

    # 计算订单总数
    total_orders = len(filtered_df)

    # 计算平均现货满足率
    if "现货满足判定" in filtered_df.columns:
        fulfillment_rate = (filtered_df["现货满足判定"] == "是").mean()
    else:
        fulfillment_rate = 0

    # Step 4: 计算月度指标
    monthly_metrics = calculate_monthly_metrics(processed_df, selected_years)

    # Step 5: 计算客户指标（传递选中的年份）
    customer_metrics = calculate_customer_metrics(processed_df, selected_years)

    # Step 6: 渲染UI（按照架构师要求的布局）
    render_kpi_cards(total_amount, total_orders, fulfillment_rate)

    st.markdown("---")

    render_monthly_charts(monthly_metrics, curr_lang)

    st.markdown("---")

    render_customer_table(customer_metrics)

    # ==================== Step 7: 区域销售热力图 ====================
    render_regional_sales(processed_df)

    # Step 8: 显示异常样本分析
    render_anomaly_samples(processed_df)


def load_backorder_data_with_cache():
    """
    加载缺货清单数据（带缓存）

    Returns:
        tuple: (DataFrame, info_dict)
    """
    from core.data_engine import DataEngine
    from pathlib import Path
    from config import SALES_DATA_DIR

    engine = DataEngine()
    sales_dir = Path(SALES_DATA_DIR)

    # 读取包含"miles订单未发货清单"关键词的文件
    backorder_files = engine.get_files_by_keyword(sales_dir, "miles订单未发货清单")

    if not backorder_files:
        return pd.DataFrame(), {
            "file_count": 0,
            "files": [],
            "status": "warning",
            "message": "未找到缺货清单文件",
        }

    # 读取并处理文件
    dataframes = []
    file_info_list = []

    for file_path in backorder_files:
        try:
            df = engine.read_data_file(file_path)
            if not df.empty:
                dataframes.append(df)
                file_info_list.append(engine.get_file_info(file_path))
        except Exception as e:
            import warnings
            warnings.warn(f"读取文件 {file_path.name} 失败：{str(e)}")

    if not dataframes:
        return pd.DataFrame(), {
            "file_count": len(backorder_files),
            "files": file_info_list,
            "status": "warning",
            "message": "无法读取缺货清单文件",
        }

    # 合并数据
    backorder_df = engine.merge_dataframes(dataframes, file_info_list)

    # 跳过前3列系统元数据
    def skip_system_columns(df):
        if df.empty or len(df.columns) <= 3:
            return df
        return df.iloc[:, 3:].copy()

    backorder_clean = skip_system_columns(backorder_df)

    return backorder_clean, {
        "file_count": len(backorder_files),
        "files": [info["name"] for info in file_info_list],
        "total_records": len(backorder_clean),
        "status": "success",
        "message": f"成功读取 {len(file_info_list)} 个缺货清单文件，共 {len(backorder_clean)} 条记录",
    }



def render_backorder_analysis():
    """
    缺货分析页面（基于DAX逻辑）

    核心逻辑：
    1. 使用复合主键（订单号+物料号）关联订单明细表和发货明细表
    2. 预处理发货表：只筛选"已发货"状态，按订单号+物料号分组取MAX(发货时间)
    3. 缺货判定：满足任一条件即为缺货（已发货数量<数量、最晚发货时间为空、天数差>3天）
    4. 缺货天数：仅针对缺货订单，计算 最晚发货时间-确认时间
    """
    from core.data_engine import DataEngine
    from pathlib import Path
    from config import SALES_DATA_DIR

    st.title(get_text("backorder_analysis.page_title"))
    st.markdown("---")

    engine = DataEngine()
    sales_dir = Path(SALES_DATA_DIR)

    # ==================== Step 1: 加载数据 ====================
    with st.spinner(get_text("common.loading")):
        # 1.1 加载订单明细表
        order_files = engine.get_files_by_keyword(sales_dir, "miles新可用的子公司备件订单明细")
        if not order_files:
            st.warning(get_text("backorder_analysis.order_file_not_found"))
            return

        order_df = engine.read_data_file(order_files[0])
        order_df = order_df.iloc[:, 3:].copy()  # 跳过前3列系统元数据

        # 1.2 加载发货明细表
        shipping_files = engine.get_files_by_keyword(sales_dir, "miles可用的子公司备件发车明细")
        if not shipping_files:
            st.warning(get_text("backorder_analysis.shipping_file_not_found"))
            return

        shipping_df = engine.read_data_file(shipping_files[0])
        shipping_df = shipping_df.iloc[:, 3:].copy()  # 跳过前3列系统元数据

    # ==================== Step 2: 查找关键列 ====================
    # 订单表列
    order_id_col = None
    part_no_col = None
    qty_col = None
    confirm_time_col = None
    part_desc_col = None
    customer_name_col = None

    for col in order_df.columns:
        # 订单号：可能是"子公司备件订单"或包含"订单"的列
        if order_id_col is None and ("子公司备件订单" in col or "订单" in col):
            if "物料" not in col and "数量" not in col:
                order_id_col = col
        # 物料号
        if part_no_col is None and "物料号" in col:
            if "描述" not in col:
                part_no_col = col
        # 物料描述
        if part_desc_col is None and "物料描述" in col:
            part_desc_col = col
        # 数量
        if qty_col is None and "数量" in col:
            if "已发" not in col and "未发" not in col and "发车" not in col:
                qty_col = col
        # 确认时间
        if confirm_time_col is None and "确认时间" in col:
            confirm_time_col = col
        # 客户名称
        if customer_name_col is None and col == "客户 (子公司备件订单) (子公司备件订单)":
            customer_name_col = col

    # 发货表列
    ship_order_id_col = None
    ship_part_no_col = None
    shipped_qty_col = None
    sap_status_col = None
    ship_time_col = None

    for col in shipping_df.columns:
        # 订单号
        if ship_order_id_col is None and ("子公司备件订单" in col or "订单" in col):
            if "物料" not in col and "数量" not in col:
                ship_order_id_col = col
        # 物料号
        if ship_part_no_col is None and "物料号" in col:
            if "描述" not in col:
                ship_part_no_col = col
        # 发货数量（使用"数量"列）
        if shipped_qty_col is None and col == "数量":
            shipped_qty_col = col
        # SAP发货状态
        if sap_status_col is None and ("SAP发货状态" in col or "状态" in col):
            sap_status_col = col
        # 发货时间
        if ship_time_col is None and "SAP发货时间" in col:
            ship_time_col = col

    if not all([order_id_col, part_no_col, qty_col, confirm_time_col]):
        st.warning(get_text("backorder_analysis.missing_key_columns_order"))
        return

    if not all([ship_order_id_col, ship_part_no_col, sap_status_col, ship_time_col]):
        st.warning(get_text("backorder_analysis.missing_key_columns_shipping"))
        return

    # ==================== Step 3: 复合主键类型统一 ====================
    # 【防御性编程】强制转换为字符串并去除空格
    order_df["_order_id"] = order_df[order_id_col].astype(str).str.strip()
    order_df["_part_no"] = order_df[part_no_col].astype(str).str.strip()

    # 保存客户名称（用于后续过滤）
    if customer_name_col:
        order_df["_customer_name"] = order_df[customer_name_col].astype(str).str.strip()

    shipping_df["_order_id"] = shipping_df[ship_order_id_col].astype(str).str.strip()
    shipping_df["_part_no"] = shipping_df[ship_part_no_col].astype(str).str.strip()

    # ==================== Step 4: 发货表预处理 ====================
    # 4.1 只筛选"SAP发货状态"为"已发货"的行
    if sap_status_col in shipping_df.columns:
        shipping_shipped = shipping_df[shipping_df[sap_status_col] == "已发货"].copy()
    else:
        shipping_shipped = shipping_df.copy()

    if shipping_shipped.empty:
        st.warning(get_text("backorder_analysis.no_shipped_records"))
        return

    # 4.2 按订单号+物料号分组，取SAP发货时间的MAX值
    # 【DAX对齐】使用groupby+agg
    shipping_agg = shipping_shipped.groupby(["_order_id", "_part_no"], as_index=False).agg({
        ship_time_col: 'max',
        shipped_qty_col: 'max' if shipped_qty_col else 'first'
    })

    # 重命名列
    shipping_agg = shipping_agg.rename(columns={
        ship_time_col: "_ship_time",
        shipped_qty_col: "_shipped_qty"
    })

    # ==================== Step 5: 复合主键左连接 ====================
    # 【DAX对齐】使用 ['订单号', '物料号'] 作为复合键进行 Left Join
    merged_df = order_df.merge(
        shipping_agg,
        left_on=["_order_id", "_part_no"],
        right_on=["_order_id", "_part_no"],
        how="left"
    )

    # ==================== Step 6: 日期处理 ====================
    # 6.1 转换并归一化确认时间
    merged_df[confirm_time_col] = pd.to_datetime(merged_df[confirm_time_col], errors="coerce")
    merged_df["_confirm_time"] = merged_df[confirm_time_col].dt.normalize()

    # 6.2 转换发货时间
    merged_df["_ship_time"] = pd.to_datetime(merged_df["_ship_time"], errors="coerce")

    # ==================== Step 7: 缺货判定 ====================
    # 【修正】缺货判定逻辑 - 严格按顺序检查
    # 数据类型强制转换：确保数量和天数差为整数类型
    merged_df["_qty"] = pd.to_numeric(merged_df[qty_col], errors="coerce").fillna(0).astype(int)
    merged_df["_shipped_qty"] = pd.to_numeric(merged_df["_shipped_qty"], errors="coerce").fillna(0).astype(int)

    # 计算天数差（发货时间 - 确认时间），并强制转换为整数
    merged_df["_days_diff"] = ((merged_df["_ship_time"] - merged_df["_confirm_time"]).dt.days).astype("Int64")

    # 按顺序执行判定逻辑
    is_backordered = []

    for idx, row in merged_df.iterrows():
        ship_time = row["_ship_time"]
        shipped_qty = row["_shipped_qty"]
        qty = row["_qty"]
        days_diff = row["_days_diff"]

        # 第一步：如果最晚发货时间为空，判定为"是"
        if pd.isna(ship_time):
            is_backordered.append("是")
            continue

        # 第二步：如果已发货数量 < 数量，判定为"是"
        if shipped_qty < qty:
            is_backordered.append("是")
            continue

        # 第三步：如果天数差 > 3，判定为"是"
        if pd.notna(days_diff) and days_diff > 3:
            is_backordered.append("是")
            continue

        # 第四步：0-3天范围内且数量已发全，判定为"否"
        if pd.notna(days_diff) and 0 <= days_diff <= 3:
            is_backordered.append("否")
            continue

        # 其他情况（安全默认值）
        is_backordered.append("否")

    merged_df["是否缺货"] = is_backordered

    # 【调试】打印"1-3天内但判定为缺货"的记录，分析原因
    debug_df = merged_df[
        (merged_df["是否缺货"] == "是") &
        (merged_df["_days_diff"].notna()) &
        (merged_df["_days_diff"] >= 0) &
        (merged_df["_days_diff"] <= 3)
    ][["_order_id", "_part_no", "_qty", "_shipped_qty", "_days_diff", "是否缺货"]]

    if len(debug_df) > 0:
        print("=" * 60)
        print(f"【调试】发现 {len(debug_df)} 条 0-3 天内但判定为缺货的记录：")
        print("=" * 60)
        for idx, row in debug_df.head(20).iterrows():
            print(f"订单号: {row['_order_id']}, 物料号: {row['_part_no']}")
            print(f"  订单数量: {row['_qty']}, 已发货数量: {row['_shipped_qty']}, 天数差: {row['_days_diff']}")
        print("=" * 60)

    # ==================== Step 8: 缺货天数计算 ====================
    # 【DAX对齐】仅针对"是否缺货=是"的订单，计算天数差
    merged_df["缺货天数"] = merged_df.apply(
        lambda row: row["_days_diff"] if row["是否缺货"] == "是" and pd.notna(row["_days_diff"]) else None,
        axis=1
    )

    # ==================== Step 9: 过滤有效数据 ====================
    # 过滤缺货状态为"是"的记录
    backorder_df = merged_df[merged_df["是否缺货"] == "是"].copy()

    # 过滤掉"NAN Inc"客户（测试数据）
    if "_customer_name" in backorder_df.columns:
        backorder_df = backorder_df[backorder_df["_customer_name"] != "NAN Inc"]

    # 【需求1】过滤确认时间为空的行（没确认的发货需求不计入缺货统计）
    if "_confirm_time" in backorder_df.columns:
        backorder_df = backorder_df[backorder_df["_confirm_time"].notna()]

    # 【需求2】过滤2024年8月以前的数据
    if "_confirm_time" in backorder_df.columns:
        cutoff_date = pd.Timestamp("2024-08-01")
        backorder_df = backorder_df[backorder_df["_confirm_time"] >= cutoff_date]

    # 检查是否还有数据
    if backorder_df.empty:
        st.success(get_text("backorder_analysis.all_orders_shipped"))
        return

    st.info(get_text_safe("backorder_analysis.filtered_records_remaining", count=len(backorder_df)))

    # 【需求3】计算物料累计缺货次数（仅针对缺货记录）
    # 按物料号统计出现次数
    backorder_df["_backorder_count"] = backorder_df.groupby("_part_no")["_part_no"].transform("count")

    # ==================== Step 10: 计算KPI ====================
    total_backorders = len(backorder_df)
    avg_backorder_days = backorder_df["缺货天数"].mean()

    # ==================== Step 11: UI展示 ====================
    st.markdown(f"### {get_text('backorder_analysis.backorder_overview')}")

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            label=get_text("backorder_analysis.backorder_orders"),
            value=f"{total_backorders:,}",
            delta=None,
        )

    with col2:
        st.metric(
            label=get_text("backorder_analysis.avg_backorder_days"),
            value=f"{avg_backorder_days:.1f} 天" if pd.notna(avg_backorder_days) else "N/A",
            delta=None,
        )

    st.markdown("---")

    # ==================== Step 12: 月度趋势图 ====================
    st.markdown(f"### {get_text('backorder_analysis.monthly_backorder_trend')}")

    # 按月份统计缺货订单数
    if "_confirm_time" in backorder_df.columns:
        backorder_df["月份"] = backorder_df["_confirm_time"].dt.strftime("%Y-%m")

        monthly_stats = backorder_df.groupby("月份").agg({
            "是否缺货": "count",
            "缺货天数": "mean"
        }).reset_index()
        monthly_stats.columns = ["月份", "缺货订单数", "平均缺货天数"]
        monthly_stats = monthly_stats.sort_values("月份")

        # 柱状图：按月份统计缺货订单数
        fig = px.bar(
            monthly_stats,
            x="月份",
            y="缺货订单数",
            title=get_text("backorder_analysis.monthly_backorder_orders"),
            labels={"月份": get_text("sales.month"), "缺货订单数": "订单数"},
            color="缺货订单数",
            color_continuous_scale="Reds",
        )
        fig.update_layout(
yaxis_tickformat=",.0f",
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # ==================== Step 13: 明细表格 ====================
    st.markdown(f"### {get_text('backorder_analysis.backorder_detail')}")

    # 选择显示的列
    display_columns = ["_order_id", "_part_no", part_desc_col if part_desc_col else "_part_no"]

    # 添加客户名称列（如果存在）
    if "_customer_name" in backorder_df.columns:
        display_columns.insert(1, "_customer_name")

    # 【需求3】添加物料累计缺货次数列
    if "_backorder_count" in backorder_df.columns:
        display_columns.append("_backorder_count")

    # 【调试列】添加原始数量和已发货数量，方便对账
    if "_qty" in backorder_df.columns:
        display_columns.append("_qty")
    if "_shipped_qty" in backorder_df.columns:
        display_columns.append("_shipped_qty")

    # 添加时间相关列
    for col in backorder_df.columns:
        if "_confirm_time" in col:
            display_columns.append("_confirm_time")
        if "_ship_time" in col:
            display_columns.append("_ship_time")

    display_columns.append("缺货天数")

    # 过滤存在的列
    available_columns = [col for col in display_columns if col in backorder_df.columns]

    if not available_columns:
        st.warning(get_text("backorder_analysis.cannot_display_detail"))
        return

    # 按缺货天数从高到低排序（最严重的在上面）
    df_display = backorder_df.sort_values("缺货天数", ascending=False)[available_columns].copy()

    # 重命名列为中文
    rename_map = {
        "_customer_name": "客户名称",
        "_order_id": "订单号",
        "_part_no": "物料号",
        part_desc_col: "物料描述" if part_desc_col else "物料号",
        "_backorder_count": "物料累计缺货次数",
        "_qty": "订单数量",
        "_shipped_qty": "已发货数量",
        "_confirm_time": "确认时间",
        "_ship_time": "最晚发货时间",
        "缺货天数": "缺货天数"
    }

    df_display = df_display.rename(columns=rename_map)

    # 格式化时间列
    if "确认时间" in df_display.columns:
        df_display["确认时间"] = df_display["确认时间"].apply(
            lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else "N/A"
        )
    if "最晚发货时间" in df_display.columns:
        df_display["最晚发货时间"] = df_display["最晚发货时间"].apply(
            lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else "未发货"
        )

    # 格式化缺货天数
    if "缺货天数" in df_display.columns:
        df_display["缺货天数"] = df_display["缺货天数"].apply(
            lambda x: f"{int(x)} 天" if pd.notna(x) else "N/A"
        )

    # 格式化物料累计缺货次数
    if "物料累计缺货次数" in df_display.columns:
        df_display["物料累计缺货次数"] = df_display["物料累计缺货次数"].apply(
            lambda x: f"{int(x)} 次" if pd.notna(x) else "N/A"
        )

    # 使用Streamlit的数据框组件显示
    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
    )

    # 显示统计信息
    st.caption(get_text_safe("backorder_analysis.total_backorder_records", count=total_backorders))

    # ==================== 客户缺货价值指标 ====================
    st.markdown("---")
    st.markdown("### 📊 客户缺货价值指标")
    
    with st.spinner("加载客户缺货价值数据..."):
        # 加载缺货报表
        backorder_report_files = engine.get_files_by_keyword(sales_dir, "缺货报表")
        if not backorder_report_files:
            st.warning("未找到缺货报表文件")
        else:
            backorder_report_df = engine.read_data_file(backorder_report_files[0])
            # 缺货报表不跳过前3列
            
            # 加载物料未发货清单获取单价
            pending_files = engine.get_files_by_keyword(sales_dir, "miles订单未发货清单")
            if not pending_files:
                st.warning("未找到物料未发货清单文件")
            else:
                pending_df = engine.read_data_file(pending_files[0])
                pending_df = pending_df.iloc[:, 3:].copy()
                
                # 识别关键列
                # 缺货报表列
                bo_customer_col = None
                bo_part_no_col = None
                bo_qty_col = None
                
                for col in backorder_report_df.columns:
                    col_str = str(col).strip()
                    # 客户列：精确匹配"客户"（第二列），排除"客户订单号"
                    if bo_customer_col is None and col_str == "客户":
                        bo_customer_col = col
                    if bo_part_no_col is None and "物料号" in col_str and "描述" not in col_str:
                        bo_part_no_col = col
                    if bo_qty_col is None and "未发数量" in col_str:
                        bo_qty_col = col
                
                # 未发货清单列
                pd_part_no_col = None
                pd_price_col = None
                
                for col in pending_df.columns:
                    if pd_part_no_col is None and col == "物料号":
                        pd_part_no_col = col
                    if pd_price_col is None and col == "单价":
                        pd_price_col = col
                
                if bo_customer_col and bo_part_no_col and bo_qty_col and pd_part_no_col and pd_price_col:
                    # 数据清洗
                    backorder_report_df["_part_no"] = backorder_report_df[bo_part_no_col].astype(str).str.strip()
                    backorder_report_df["_backorder_qty"] = pd.to_numeric(backorder_report_df[bo_qty_col], errors="coerce").fillna(0)
                    
                    pending_df["_part_no"] = pending_df[pd_part_no_col].astype(str).str.strip()
                    pending_df["_unit_price"] = pd.to_numeric(pending_df[pd_price_col], errors="coerce").fillna(0)
                    
                    # 按物料号去重，取单价
                    price_df = pending_df[["_part_no", "_unit_price"]].drop_duplicates(subset=["_part_no"])
                    
                    # 关联单价
                    backorder_report_df = backorder_report_df.merge(
                        price_df,
                        on="_part_no",
                        how="left"
                    )
                    backorder_report_df["_unit_price"] = backorder_report_df["_unit_price"].fillna(0)
                    
                    # 记录异常
                    missing_price = backorder_report_df[backorder_report_df["_unit_price"] == 0]
                    if len(missing_price) > 0:
                        print(f"⚠️ 缺货报表中有 {len(missing_price)} 条记录无法匹配到单价")
                    
                    # 计算缺货金额
                    backorder_report_df["_backorder_amount"] = backorder_report_df["_backorder_qty"] * backorder_report_df["_unit_price"]
                    
                    # 按客户汇总
                    customer_stats = backorder_report_df.groupby(bo_customer_col).agg({
                        "_backorder_qty": "sum",
                        "_backorder_amount": "sum"
                    }).reset_index()
                    
                    customer_stats = customer_stats.sort_values("_backorder_amount", ascending=False)
                    
                    # 重命名列
                    customer_stats = customer_stats.rename(columns={
                        bo_customer_col: "客户名称",
                        "_backorder_qty": "总缺货数量",
                        "_backorder_amount": "总缺货货值"
                    })
                    
                    # 格式化显示
                    customer_stats["总缺货货值"] = customer_stats["总缺货货值"].apply(lambda x: f"${x:,.2f}")
                    customer_stats["总缺货数量"] = customer_stats["总缺货数量"].apply(lambda x: f"{int(x):,}")
                    
                    st.dataframe(
                        customer_stats,
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    # 显示调试信息
                    st.warning(f"列识别失败: 缺货报表列={backorder_report_df.columns.tolist()}")
                    st.warning(f"列识别失败: 未发货清单列={pending_df.columns.tolist()}")


def render_pending_shipment():
    """
    待发货清单页面

    核心功能：
    1. 展示未发货订单明细
    2. 统计待发货总额和订单数
    3. 分析月度未发货金额趋势

    数据源：miles订单未发货清单文件
    """
    from core.data_engine import DataEngine
    from pathlib import Path
    from config import SALES_DATA_DIR
    from datetime import datetime

    st.title(get_text("pending_shipment.page_title"))
    st.markdown("---")

    engine = DataEngine()
    sales_dir = Path(SALES_DATA_DIR)

    # ==================== Step 1: 数据加载 ====================
    with st.spinner(get_text("common.loading")):
        # 加载待发货清单文件
        pending_files = engine.get_files_by_keyword(sales_dir, "miles订单未发货清单")
        if not pending_files:
            st.warning(get_text("pending_shipment.pending_file_not_found"))
            return

        df = engine.read_data_file(pending_files[0])
        df = df.iloc[:, 3:].copy()  # 跳过前3列系统元数据

    # ==================== Step 2: 列名映射 ====================
    col_mapping = {}
    for col in df.columns:
        if "订单号" in col:
            col_mapping["订单号"] = col
        elif "物料号" in col and "描述" not in col:
            col_mapping["物料号"] = col
        elif "物料描述" in col:
            col_mapping["物料描述"] = col
        elif "未发" in col and "数量" in col:
            col_mapping["未发数量"] = col
        elif col == "单价":
            col_mapping["单价"] = col
        elif "创建时间" in col:
            col_mapping["创建时间"] = col
        elif "客户" in col:
            col_mapping["客户"] = col

    # 检查必要列是否存在
    required_cols = ["订单号", "物料号", "物料描述", "未发数量", "单价", "创建时间"]
    for key in required_cols:
        if key not in col_mapping:
            st.warning(f"缺少必要列: {key}")
            return

    # ==================== Step 3: 数据清洗与转换 ====================
    # 强制统一订单号为字符串
    df["_order_id"] = df[col_mapping["订单号"]].astype(str).str.strip()

    # 创建时间转换并归一化
    df["_create_time"] = pd.to_datetime(df[col_mapping["创建时间"]], errors="coerce")
    df["_create_date"] = df["_create_time"].dt.normalize()

    # 提取月份
    df["_month"] = df["_create_date"].dt.strftime("%Y-%m")

    # 总金额计算：未发数量 * 单价
    df["_qty"] = pd.to_numeric(df[col_mapping["未发数量"]], errors="coerce").fillna(0)
    df["_price"] = pd.to_numeric(df[col_mapping["单价"]], errors="coerce").fillna(0)
    df["_total_amount"] = df["_qty"] * df["_price"]

    # 缺货天数：当前日期 - 创建时间
    today = datetime.now().date()
    df["_backorder_days"] = df["_create_time"].apply(
        lambda x: (today - x.date()).days if pd.notna(x) else None
    )

    # 过滤有效数据
    df_valid = df[df["_qty"] > 0].copy()

    if df_valid.empty:
        st.success("✅ 所有订单都已发货，没有待发货记录！")
        return

    # ==================== Step 4: KPI 指标卡 ====================
    total_amount = df_valid["_total_amount"].sum()
    total_orders = len(df_valid)

    st.markdown("### 📊 待发货概况")

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            label="💰 当前待发货总额 ($)",
            value=f"${total_amount:,.2f}",
            delta=None,
        )

    with col2:
        st.metric(
            label="📦 当前待发货订单数",
            value=f"{total_orders:,}",
            delta=None,
        )

    st.markdown("---")

    # ==================== Step 5: 月度趋势图 ====================
    st.markdown("### 📈 月度待发货金额趋势")

    # 按月份统计
    monthly_stats = df_valid.groupby("_month").agg({
        "_total_amount": "sum",
        "_order_id": "count"
    }).reset_index()
    monthly_stats.columns = ["月份", "待发金额", "订单数"]
    monthly_stats = monthly_stats.sort_values("月份")

    if not monthly_stats.empty:
        # 柱状图
        fig = px.bar(
            monthly_stats,
            x="月份",
            y="待发金额",
            title="📊 每月待发货金额",
            labels={"月份": "月份", "待发金额": "金额 ($)"},
            color="待发金额",
            color_continuous_scale="Oranges",
        )

        fig.update_layout(
            yaxis_tickformat="$,.0f",
            hovermode="x unified",
        )

        # 添加数据标签
        fig.update_traces(
            texttemplate="$%{y:,.0f}",
            textposition="outside"
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("暂无月度数据")

    st.markdown("---")

    # ==================== Step 6: 明细表格 ====================
    st.markdown("### 📋 待发货订单明细")

    # 选择显示的列
    display_df = df_valid[[
        "_order_id",
        col_mapping["物料描述"],
        col_mapping["未发数量"],
        "_month",
        "_total_amount",
        "_backorder_days"
    ]].copy()

    # 重命名列
    display_df = display_df.rename(columns={
        "_order_id": "订单号",
        col_mapping["物料描述"]: "物料描述",
        col_mapping["未发数量"]: "未发数量",
        "_month": "月份",
        "_total_amount": "总金额",
        "_backorder_days": "缺货天数"
    })

    # 格式化金额
    display_df["总金额"] = display_df["总金额"].apply(
        lambda x: f"${x:,.2f}" if pd.notna(x) else "$0.00"
    )

    # 格式化缺货天数
    display_df["缺货天数"] = display_df["缺货天数"].apply(
        lambda x: f"{int(x)} 天" if pd.notna(x) else "N/A"
    )

    # 按总金额从高到低排序
    display_df = display_df.sort_values(
        by="总金额",
        key=lambda x: x.str.replace("[$,]", "", regex=True).astype(float),
        ascending=False
    )

    # 使用Streamlit的数据框组件显示
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )

    # 显示统计信息
    st.caption(f"共 {total_orders} 条待发货记录")


@st.cache_data(ttl=3600)  # 缓存1小时，确保数据新鲜度与性能的平衡
def load_chain_data_v2():
    """
    加载缺货全链路追踪数据 V2 (新架构)
    
    数据源:
    1. 缺货报表 (sales目录): 缺货报表 20260219
    2. 采购表 (procurement目录): miles采购表
    3. 箱号明细 (procurement目录): 温新宇可用的箱号明细表
    4. 合同明细 (logistics目录): dayu可用的进出口备件合同明细
    5. 发车申请 - 在合同明细表的同一文件里
    
    Returns:
        tuple: (数据源字典, info_dict)
    """
    from core.data_engine import DataEngine
    from pathlib import Path
    from config import SALES_DATA_DIR, PROCUREMENT_DATA_DIR, LOGISTICS_DATA_DIR
    import warnings
    
    engine = DataEngine()
    
    result = {
        "缺货报表": {"df": pd.DataFrame(), "status": "pending"},
        "采购表": {"df": pd.DataFrame(), "status": "pending"},
        "箱号明细": {"df": pd.DataFrame(), "status": "pending"},
        "合同明细": {"df": pd.DataFrame(), "status": "pending"},
        "发车申请": {"df": pd.DataFrame(), "status": "pending"},
    }
    
    # 1. 加载缺货报表 (目录: sales, 文件名: 缺货报表 20260219)
    # 注意：缺货报表不需要跳过前三列
    try:
        sales_dir = Path(SALES_DATA_DIR)
        backorder_files = engine.get_files_by_keyword(sales_dir, "缺货报表")
        if backorder_files:
            df = engine.read_data_file(backorder_files[0])
            if not df.empty:
                result["缺货报表"]["df"] = df
                result["缺货报表"]["status"] = "success"
    except Exception as e:
        warnings.warn(f"加载缺货报表失败: {e}")
    
    # 2. 加载采购表 (目录: procurement, 文件名: miles采购表)
    try:
        proc_dir = Path(PROCUREMENT_DATA_DIR)
        proc_files = engine.get_files_by_keyword(proc_dir, "miles采购表")
        if proc_files:
            df = engine.read_data_file(proc_files[0])
            if not df.empty and len(df.columns) > 3:
                df = df.iloc[:, 3:].copy()
                result["采购表"]["df"] = df
                result["采购表"]["status"] = "success"
    except Exception as e:
        warnings.warn(f"加载采购表失败: {e}")
    
    # 3. 加载箱号明细 (目录: procurement, 文件名: 温新宇可用的箱号明细表)
    try:
        proc_dir = Path(PROCUREMENT_DATA_DIR)
        box_files = engine.get_files_by_keyword(proc_dir, "温新宇可用的箱号明细表")
        if not box_files:
            box_files = engine.get_files_by_keyword(proc_dir, "箱号明细")
        if box_files:
            df = engine.read_data_file(box_files[0])
            if not df.empty and len(df.columns) > 3:
                df = df.iloc[:, 3:].copy()
                result["箱号明细"]["df"] = df
                result["箱号明细"]["status"] = "success"
    except Exception as e:
        warnings.warn(f"加载箱号明细失败: {e}")
    
    # 4. 加载合同明细和发车申请 (目录: logistics, 文件名: dayu可用的进出口备件合同明细)
    try:
        log_dir = Path(LOGISTICS_DATA_DIR)
        contract_files = engine.get_files_by_keyword(log_dir, "dayu可用的进出口备件合同明细")
        if contract_files:
            df = engine.read_data_file(contract_files[0])
            if not df.empty and len(df.columns) > 3:
                df = df.iloc[:, 3:].copy()
                result["合同明细"]["df"] = df
                result["合同明细"]["status"] = "success"
                # 发车申请也在同一个文件里
                result["发车申请"]["df"] = df
                result["发车申请"]["status"] = "success"
    except Exception as e:
        warnings.warn(f"加载合同明细/发车申请失败: {e}")
    
    return result, {"status": "success", "message": "数据加载完成"}


def find_column_by_keywords(df, keywords):
    """
    根据关键词列表查找列
    
    匹配策略:
    1. 先尝试精确匹配（列名 == 关键词）
    2. 再尝试子字符串匹配（关键词 in 列名），但排除"原物料号"包含"物料号"的情况
    
    Args:
        df: DataFrame
        keywords: 关键词列表
        
    Returns:
        str: 找到的列名，未找到返回None
    """
    if df.empty:
        return None
    
    # 第一轮：精确匹配
    for col in df.columns:
        col_str = str(col).strip()
        for kw in keywords:
            if col_str == kw:
                return col
    
    # 第二轮：子字符串匹配（但避免"原物料号"匹配到"物料号"）
    for col in df.columns:
        col_str = str(col).strip()
        for kw in keywords:
            # 排除错误匹配：原物料号不应该匹配"物料号"
            if col_str == "原物料号" and kw == "物料号":
                continue
            if kw in col_str:
                return col
    return None


def clean_join_key(series):
    """
    清洗关联键: 转字符串 -> 去空格 -> 去前导零
    
    Args:
        series: Pandas Series
        
    Returns:
        Series: 清洗后的Series
    """
    return series.astype(str).str.strip().str.lstrip('0')


def preprocess_procurement_table(df):
    """
    预处理采购表: 建立 物料号 映射键
    
    逻辑: 
    1. 创建标准的"物料号"列用于关联
    2. 如果 原物料号 有值则用它，否则用原来的物料号
    3. 执行去零清洗，防止前导零导致匹配失败
         
    Args:
        df: 采购表DataFrame
        
    Returns:
        DataFrame: 预处理后的采购表
    """
    # 查找原物料号和物料号列
    orig_part_col = find_column_by_keywords(df, ["原物料号", "原物料"])
    part_col = find_column_by_keywords(df, ["物料号", "物料"])
    
    if part_col is None:
        return df
    
    # 强制转换类型并清洗（去前导零）
    if orig_part_col:
        df[orig_part_col] = df[orig_part_col].astype(str).str.strip().str.lstrip('0')
    df[part_col] = df[part_col].astype(str).str.strip().str.lstrip('0')
    
    # 【核心】创建标准的"物料号"列用于关联
    # 如果原物料号不为空且有效，则用原物料号；否则用物料号
    if orig_part_col:
        df["物料号"] = df[orig_part_col].where(
            (df[orig_part_col] != '') & (df[orig_part_col] != 'nan') & (df[orig_part_col] != 'None'),
            df[part_col]
        )
    else:
        df["物料号"] = df[part_col]
    
    # 额外创建 match_part 列作为备用（保持向后兼容）
    df["match_part"] = df["物料号"]
    
    return df


def force_str(s):
    """万能字符串清洗：去空格、去前导零、转大写"""
    return str(s).strip().replace('.0', '').lstrip('0').upper()


def strict_clean(value):
    """
    强制清洗函数：强转字符串、去空格、去前导零、去 .0
    用于装箱表的关联键标准化
    
    Args:
        value: 任意类型的值
        
    Returns:
        str: 清洗后的字符串
    """
    if pd.isna(value):
        return ""
    return str(value).strip().lstrip('0').replace('.0', '')


def extract_npous_orders(text):
    """使用正则提取所有NPOUS开头的单号"""
    import re
    if pd.isna(text):
        return []
    text = str(text).upper()
    matches = re.findall(r'NPOUS\d+', text)
    return [m.strip().upper() for m in matches]


def parse_npous_date(order_no):
    """从客户订单号(如NPOUS2601280012)提取日期"""
    try:
        order_no = str(order_no).upper().strip()
        if order_no.startswith('NPOUS'):
            # 提取 NPOUS 后的 6 位数字: 260128 -> 2026-01-28
            date_str = order_no[5:11]
            if len(date_str) == 6:
                return pd.to_datetime("20" + date_str, format="%Y%m%d")
    except:
        pass
    return pd.NaT


@st.cache_data(ttl=3600, show_spinner=True)  # 缓存1小时，显示加载动画
def build_chain_master_v2(data_sources):
    """
    构建缺货全链路追踪主表 V2 (新架构)
    
    关联逻辑 (分步执行):
    1. 缺货 ➡️ 采购: 物料号精确匹配 + 客户订单号 包含于 适用机型
    2. 采购 ➡️ 装箱: SAP订单号 + 物料号
    3. 装箱 ➡️ 合同: 箱号 + 物料号
    4. 合同 ➡️ 物流: 发车申请单号
    
    Args:
        data_sources: 数据源字典
        
    Returns:
        DataFrame: 主表数据
    
    【注意】此函数已添加 @st.cache_data 装饰器，确保：
    - 只要原始数据文件不变，就使用缓存结果
    - 搜索和筛选在 UI 层完成（内存级操作，秒速响应）
    """
    master_df = pd.DataFrame()
    
    # ==================== Step 1: 加载并预处理缺货报表 ====================
    backorder_df = data_sources.get("缺货报表", {}).get("df", pd.DataFrame())
    if backorder_df.empty:
        return master_df
    
    # 查找关键列
    order_col = find_column_by_keywords(backorder_df, ["订单号", "客户订单号", "需求单号"])
    part_col = find_column_by_keywords(backorder_df, ["物料号", "备件号"])
    part_desc_col = find_column_by_keywords(backorder_df, ["物料描述", "描述"])
    
    if not order_col or not part_col:
        return master_df
    
    # 初始化主表，保留缺货表原始数据
    master_df = backorder_df.copy()
    
    # 【新增】提取创建时间列
    master_df["提取创建时间"] = master_df[order_col].apply(parse_npous_date)
    
    # 查找未发数量列
    qty_col = find_column_by_keywords(backorder_df, ["未发数量", "数量"])
    if qty_col:
        master_df["_未发数量"] = pd.to_numeric(master_df[qty_col], errors="coerce").fillna(0)
    
    # 【新增】计算美国/加拿大库存：北美库存 + 加拿大库存
    # 数据来源：缺货报表中已有"北美库存"和"加拿大库存"两列
    # 使用fillna(0)处理NaN值后再相加
    na_inventory_col = find_column_by_keywords(backorder_df, ["北美库存", "北美"])
    ca_inventory_col = find_column_by_keywords(backorder_df, ["加拿大库存", "加拿大"])
    
    if na_inventory_col and ca_inventory_col:
        # 转换为数值并处理NaN值
        master_df["_北美库存"] = pd.to_numeric(master_df[na_inventory_col], errors="coerce").fillna(0)
        master_df["_加拿大库存"] = pd.to_numeric(master_df[ca_inventory_col], errors="coerce").fillna(0)
        # 计算总和
        master_df["美国/加拿大库存"] = master_df["_北美库存"] + master_df["_加拿大库存"]
    else:
        # 如果缺少其中一个或两个列，创建空列并记录警告
        master_df["美国/加拿大库存"] = 0
        import warnings
        if not na_inventory_col:
            warnings.warn("缺货报表中未找到'北美库存'列")
        if not ca_inventory_col:
            warnings.warn("缺货报表中未找到'加拿大库存'列")
    
    # 【核心】创建 match_key 物料关联键（保留用于后续装箱关联）
    # 统一使用 strict_clean 清洗物料号
    master_df["match_key"] = master_df[part_col].apply(strict_clean)
    master_df["_客户订单号"] = master_df[order_col].apply(force_str)
    
    # 【新增】保存原始物料号列的引用，用于后续装箱关联
    master_df["_物料号源列"] = part_col
    
    # 初始化采购相关列（待采购状态）
    master_df["SAP订单号"] = None
    master_df["SAP提交时间"] = None
    master_df["ETA"] = None
    master_df["适用机型"] = None
    master_df["主机厂"] = None  # 新增：主机厂字段
    master_df["采购数量"] = None  # 新增：采购数量字段（用于后续装箱数量对比）
    master_df["匹配类型"] = None  # 新增：记录匹配类型（确认/疑似/未匹配）
    
    # ==================== Step 2: 关联采购表 ====================
    proc_df = data_sources.get("采购表", {}).get("df", pd.DataFrame())
    if not proc_df.empty:
        # 预处理采购表
        proc_df = preprocess_procurement_table(proc_df)
        
        # 查找关键列
        sap_order_col = find_column_by_keywords(proc_df, ["SAP订单号", "SAP No"])
        adapt_model_col = find_column_by_keywords(proc_df, ["适配机型", "适用机型", "适配"])
        submit_time_col = find_column_by_keywords(proc_df, ["SAP提交时间", "提交时间"])
        eta_col = find_column_by_keywords(proc_df, ["ETA", "预计到达"])
        # 新增：查找主机厂和数量列
        factory_col = find_column_by_keywords(proc_df, ["主机厂", "工厂"])
        proc_qty_col = find_column_by_keywords(proc_df, ["数量", "采购数量"])
        
        if sap_order_col and adapt_model_col:
            # 【升级】为采购表创建提取订单号的列（处理"一行对多单"）
            proc_df["_extracted_orders"] = proc_df[adapt_model_col].apply(extract_npous_orders)
            
            # 【修复】使用strict_clean清洗SAP订单号和物料号作为关联键
            proc_df["_SAP订单号"] = proc_df[sap_order_col].apply(strict_clean)
            proc_df["_match_key"] = proc_df["物料号"].apply(strict_clean)
            
            # 创建物料号字典，支持多个采购记录
            proc_dict = {}
            for _, row in proc_df.iterrows():
                key = row["_match_key"]
                if key not in proc_dict:
                    proc_dict[key] = []
                proc_dict[key].append({
                    "SAP订单号": row.get("_SAP订单号", None),  # 使用清洗后的SAP订单号
                    "SAP订单号_原始": row.get(sap_order_col, None),  # 保留原始值用于显示
                    "适用机型": row.get(adapt_model_col, None),
                    "SAP提交时间": row.get(submit_time_col, None),
                    "ETA": row.get(eta_col, None),
                    "主机厂": row.get(factory_col, None) if factory_col else None,
                    "采购数量": row.get(proc_qty_col, None) if proc_qty_col else None,
                    "_extracted_orders": row.get("_extracted_orders", [])
                })
            
            # 【核心修复】智能匹配函数：物料号+单号双因子校验
            def smart_match(cust_order, adapt_model_text):
                """
                判断客户订单号是否在采购记录的适用机型字段中
                使用正则提取，包含匹配
                """
                import re
                # 1. 检查客户订单号有效性
                target_order = str(cust_order).strip().upper()
                if target_order == 'NAN' or not target_order:
                    return False
                
                # 2. 从适用机型字段抓取所有NPOUS单号
                raw_text = str(adapt_model_text).upper() if pd.notna(adapt_model_text) else ""
                found_list = re.findall(r'NPOUS\d+', raw_text)
                
                # 3. 清理可能的空格后判断
                cleaned_found = [f.replace(" ", "") for f in found_list]
                return target_order in cleaned_found
            
            # 对每个缺货行进行匹配
            for idx, row in master_df.iterrows():
                match_key = row.get("match_key", "")
                cust_order = str(row.get("_客户订单号", "")).strip() if pd.notna(row.get("_客户订单号")) else ""
                
                if match_key in proc_dict:
                    # 遍历该物料号的所有采购记录，寻找同时满足"物料号+订单号"的记录
                    for proc_info in proc_dict[match_key]:
                        adapt_model = proc_info.get("适用机型", None)
                        
                        # 【核心】双因子校验：物料号已匹配，再校验订单号
                        if smart_match(cust_order, adapt_model):
                            # 匹配成功！写入采购信息
                            master_df.at[idx, "SAP订单号"] = proc_info.get("SAP订单号")
                            master_df.at[idx, "适用机型"] = proc_info.get("适用机型")
                            master_df.at[idx, "SAP提交时间"] = proc_info.get("SAP提交时间")
                            master_df.at[idx, "ETA"] = proc_info.get("ETA")
                            master_df.at[idx, "主机厂"] = proc_info.get("主机厂")  # 新增：写入主机厂
                            master_df.at[idx, "采购数量"] = proc_info.get("采购数量")  # 新增：写入采购数量
                            master_df.at[idx, "匹配类型"] = "确认"  # 记录为确认匹配
                            break  # 找到一个匹配就退出
            
            # ==================== 疑似匹配逻辑 2.0（二次搜索 - 放宽条件）====================
            # 对于没有通过单号关联上的缺货行，执行二次搜索
            # 转换采购表的SAP提交时间为datetime
            if submit_time_col:
                proc_df["_提交时间"] = pd.to_datetime(proc_df[submit_time_col], errors="coerce")
            
            # 对未匹配的行进行疑似搜索
            for idx, row in master_df.iterrows():
                # 跳过已确认匹配的行
                if row.get("匹配类型") == "确认":
                    continue
                
                match_key = row.get("match_key", "")
                create_time = row.get("提取创建时间")
                
                # 在采购表中查找相同物料号的记录
                if match_key in proc_dict:
                    best_match = None  # 记录最佳疑似匹配
                    best_days_diff = None
                    has_material_match = False  # 标记是否有物料匹配
                    earliest_unmatched_diff = None  # 记录最早的不匹配采购时间差
                    
                    for proc_info in proc_dict[match_key]:
                        has_material_match = True  # 至少有物料匹配
                        
                        # 获取采购信息
                        proc_sap_order = proc_info.get("SAP订单号")
                        
                        # 从proc_df中找到对应的行以获取提交时间
                        # 【修复】使用清洗后的列 "_SAP订单号" 进行比较
                        matching_rows = proc_df[
                            (proc_df["_match_key"] == match_key) &
                            (proc_df["_SAP订单号"] == proc_sap_order)
                        ]
                        
                        if matching_rows.empty:
                            continue
                        
                        proc_submit_dt = matching_rows.iloc[0].get("_提交时间")
                        
                        # 疑似匹配条件判断 2.0（放宽版本）
                        # 条件：物料号一致 + 时间窗口（采购在需求后且60天内）
                        # 无需核对数量
                        time_match = False
                        days_diff = None
                        
                        if pd.notna(create_time) and pd.notna(proc_submit_dt):
                            days_diff = (proc_submit_dt - create_time).days
                            # 时间逻辑：SAP提交时间晚于需求创建日，且间隔在60天内
                            time_match = 0 <= days_diff <= 60
                        
                        # 如果满足时间条件，标记为疑似匹配
                        if time_match:
                            # 选择时间最接近的作为最佳匹配
                            if best_match is None or (days_diff is not None and (best_days_diff is None or days_diff < best_days_diff)):
                                best_match = proc_info
                                best_days_diff = days_diff
                        else:
                            # 记录不匹配的时间差（用于诊断说明）
                            if days_diff is not None:
                                if earliest_unmatched_diff is None or days_diff < earliest_unmatched_diff:
                                    earliest_unmatched_diff = days_diff
                    
                    # 应用最佳疑似匹配
                    if best_match:
                        master_df.at[idx, "SAP订单号"] = best_match.get("SAP订单号")
                        master_df.at[idx, "适用机型"] = best_match.get("适用机型")
                        master_df.at[idx, "SAP提交时间"] = best_match.get("SAP提交时间")
                        master_df.at[idx, "ETA"] = best_match.get("ETA")
                        master_df.at[idx, "主机厂"] = best_match.get("主机厂")  # 新增：写入主机厂
                        master_df.at[idx, "采购数量"] = best_match.get("采购数量")  # 新增：写入采购数量
                        master_df.at[idx, "匹配类型"] = "疑似"  # 记录为疑似匹配
                        master_df.at[idx, "_疑似天数差"] = best_days_diff  # 记录天数差用于诊断说明
                    elif has_material_match:
                        # 有物料匹配但不满足时间条件
                        master_df.at[idx, "匹配类型"] = "不相关"
                        master_df.at[idx, "_不相关天数差"] = earliest_unmatched_diff
            
            # 清理临时列
            for col in ["match_key", "_客户订单号"]:
                if col in master_df.columns:
                    master_df = master_df.drop(columns=[col])
    
    # ==================== Step 3: 添加业务周期状态 ====================
    # 根据年份标注状态
    def get_status(row):
        if pd.notna(row.get("SAP订单号")) and row.get("SAP订单号"):
            return "✅ 已采购"
        else:
            order_no = str(row.get("客户订单号", ""))
            if order_no.startswith("NPOUS26"):
                return "❌ 待采购 (2026)"
            elif order_no.startswith("NPOUS25"):
                return "❌ 待采购 (2025)"
            elif order_no.startswith("NPOUS24"):
                return "❌ 待采购 (2024)"
            else:
                return "❌ 待采购"
    
    master_df["采购状态"] = master_df.apply(get_status, axis=1)
    
    # ==================== Step 4: 初始化后续链路的空列 ====================
    # 【防崩溃安全垫】即使关联不到，也要手动确保这些列存在，防止 KeyError
    for col in ["箱号", "装箱日期", "装箱数量", "合同号", "合同日期", "发车申请单号", 
                "预计到港日期", "到港地点", "发运方式", "物流运输单号"]:
        if col not in master_df.columns:
            master_df[col] = None
    
    # ==================== Step 5: 关联箱号明细（升级版 - 双因子匹配 + 一单多箱）====================
    box_df = data_sources.get("箱号明细", {}).get("df", pd.DataFrame())
    if not box_df.empty:
        # 查找关键列
        box_sap_order_col = find_column_by_keywords(box_df, ["SAP需求单号", "SAP 需求单号"])
        box_part_col = find_column_by_keywords(box_df, ["物料号"])
        box_no_col = find_column_by_keywords(box_df, ["箱号"])
        box_date_col = find_column_by_keywords(box_df, ["装箱日期", "创建时间"])
        box_qty_col = find_column_by_keywords(box_df, ["装箱数量", "数量"])
        
        if box_sap_order_col and box_part_col and box_no_col:
            # 使用 strict_clean 强制清洗关联键
            box_df["_SAP需求单号"] = box_df[box_sap_order_col].apply(strict_clean)
            box_df["_物料号"] = box_df[box_part_col].apply(strict_clean)
            box_df["_箱号"] = box_df[box_no_col].astype(str).str.strip()
            
            # 提取装箱数量
            if box_qty_col:
                box_df["_装箱数量"] = pd.to_numeric(box_df[box_qty_col], errors="coerce").fillna(0)
            else:
                box_df["_装箱数量"] = 0
            
            # 创建匹配字典（支持一单多箱）
            box_dict = {}
            for _, row in box_df.iterrows():
                sap_order = row["_SAP需求单号"]
                part_no = row["_物料号"]
                
                # 跳过空值
                if not sap_order or not part_no:
                    continue
                
                key = (sap_order, part_no)
                
                box_no = row["_箱号"] if pd.notna(row["_箱号"]) else ""
                
                box_date = ""
                if box_date_col and pd.notna(row.get(box_date_col)):
                    box_date = str(row[box_date_col])
                
                box_qty = row["_装箱数量"]
                
                # 如果key已存在，说明一单多箱，需要合并
                if key not in box_dict:
                    box_dict[key] = {
                        "箱号列表": [],
                        "装箱日期": box_date,
                        "装箱数量": 0
                    }
                
                # 追加箱号到列表
                if box_no:
                    box_dict[key]["箱号列表"].append(box_no)
                
                # 累加装箱数量
                box_dict[key]["装箱数量"] += box_qty
                
                # 使用最新的装箱日期
                if box_date and not box_dict[key]["装箱日期"]:
                    box_dict[key]["装箱日期"] = box_date
            
            # 执行匹配（对主表的每一行）
            for idx, row in master_df.iterrows():
                # 使用 strict_clean 清洗主表的关联键
                sap_order = strict_clean(row.get("SAP订单号", ""))
                
                # 【修复】使用保存的物料号源列来获取物料号
                part_col_name = row.get("_物料号源列", None)
                if part_col_name and part_col_name in master_df.columns:
                    part_no = strict_clean(row.get(part_col_name, ""))
                else:
                    # 降级方案：尝试使用match_key
                    if "match_key" in master_df.columns:
                        part_no = row.get("match_key", "")
                    else:
                        part_no = ""
                
                # 跳过空值
                if not sap_order or not part_no:
                    continue
                
                key = (sap_order, part_no)
                
                if key in box_dict:
                    # 合并箱号（用逗号连接）
                    box_list = box_dict[key]["箱号列表"]
                    master_df.at[idx, "箱号"] = ", ".join(box_list) if box_list else ""
                    master_df.at[idx, "装箱日期"] = box_dict[key]["装箱日期"]
                    master_df.at[idx, "装箱数量"] = box_dict[key]["装箱数量"]
    
    # ==================== Step 5: 关联合同明细（升级版 - 复合主键 + 全字段抓取）====================
    contract_df = data_sources.get("合同明细", {}).get("df", pd.DataFrame())
    if not contract_df.empty:
        # 查找关键列
        contract_box_col = find_column_by_keywords(contract_df, ["箱号"])
        contract_part_col = find_column_by_keywords(contract_df, ["物料号"])
        contract_no_col = find_column_by_keywords(contract_df, ["合同编号", "合同号"])
        contract_date_col = find_column_by_keywords(contract_df, ["创建时间", "合同创建日期"])
        ship_app_col = find_column_by_keywords(contract_df, ["进出口备件发车申请单号", "发车申请单号"])
        # 新增：发车相关字段
        eta_port_col = find_column_by_keywords(contract_df, ["预计到达日期", "预计到港日期"])
        dest_port_col = find_column_by_keywords(contract_df, ["目的港", "到港地点"])
        ship_method_col = find_column_by_keywords(contract_df, ["发运方式"])
        logistics_no_col = find_column_by_keywords(contract_df, ["物流运输单号"])
        
        if contract_box_col and contract_no_col:
            # 【核心修改】使用 strict_clean 清洗关联键
            contract_df["_箱号"] = contract_df[contract_box_col].apply(strict_clean)
            contract_df["_物料号"] = contract_df[contract_part_col].apply(strict_clean) if contract_part_col else ""
            contract_df["_合同编号"] = contract_df[contract_no_col].astype(str).str.strip()
            
            # 【新增】转换合同创建日期为 datetime
            if contract_date_col:
                contract_df["_合同创建日期"] = pd.to_datetime(contract_df[contract_date_col], errors="coerce")
            
            # 创建匹配字典（支持去重：同箱号+物料号取最新合同）
            contract_dict = {}
            for _, row in contract_df.iterrows():
                box_no = row["_箱号"]
                part_no = row["_物料号"]
                
                # 跳过空值
                if not box_no or not part_no:
                    continue
                
                key = (box_no, part_no)
                
                contract_no = str(row["_合同编号"]) if pd.notna(row["_合同编号"]) else ""
                
                contract_date = None
                if contract_date_col and pd.notna(row.get("_合同创建日期")):
                    contract_date = row["_合同创建日期"]
                
                ship_app_no = ""
                if ship_app_col and pd.notna(row.get(ship_app_col)):
                    ship_app_no = str(row[ship_app_col])
                
                # 新增字段
                eta_port = ""
                if eta_port_col and pd.notna(row.get(eta_port_col)):
                    eta_port = str(row[eta_port_col])
                
                dest_port = ""
                if dest_port_col and pd.notna(row.get(dest_port_col)):
                    dest_port = str(row[dest_port_col])
                
                ship_method = ""
                if ship_method_col and pd.notna(row.get(ship_method_col)):
                    ship_method = str(row[ship_method_col])
                
                logistics_no = ""
                if logistics_no_col and pd.notna(row.get(logistics_no_col)):
                    logistics_no = str(row[logistics_no_col])
                
                # 【去重逻辑】如果key已存在，比较合同日期，保留最新的
                if key in contract_dict:
                    existing_date = contract_dict[key]["合同日期_dt"]
                    # 如果新记录的日期更新，则覆盖
                    if contract_date and existing_date:
                        if contract_date > existing_date:
                            contract_dict[key] = {
                                "合同号": contract_no,
                                "合同日期": contract_date.strftime("%Y-%m-%d") if contract_date else "",
                                "合同日期_dt": contract_date,
                                "发车申请单号": ship_app_no,
                                "预计到港日期": eta_port,
                                "到港地点": dest_port,
                                "发运方式": ship_method,
                                "物流运输单号": logistics_no
                            }
                else:
                    # 首次创建
                    contract_dict[key] = {
                        "合同号": contract_no,
                        "合同日期": contract_date.strftime("%Y-%m-%d") if contract_date else "",
                        "合同日期_dt": contract_date,
                        "发车申请单号": ship_app_no,
                        "预计到港日期": eta_port,
                        "到港地点": dest_port,
                        "发运方式": ship_method,
                        "物流运输单号": logistics_no
                    }
            
            # 执行匹配（使用 strict_clean 清洗主表的关联键）
            for idx, row in master_df.iterrows():
                # 【核心修改】使用 strict_clean 清洗箱号
                box_no_raw = row.get("箱号", "")
                box_no = strict_clean(box_no_raw)
                
                # 【修复】使用保存的物料号源列来获取物料号
                part_col_name = row.get("_物料号源列", None)
                if part_col_name and part_col_name in master_df.columns:
                    part_no = strict_clean(row.get(part_col_name, ""))
                else:
                    part_no = ""
                
                # 跳过空值
                if not box_no or not part_no:
                    continue
                
                key = (box_no, part_no)
                
                if key in contract_dict:
                    master_df.at[idx, "合同号"] = contract_dict[key]["合同号"]
                    master_df.at[idx, "合同日期"] = contract_dict[key]["合同日期"]
                    master_df.at[idx, "发车申请单号"] = contract_dict[key]["发车申请单号"]
                    master_df.at[idx, "预计到港日期"] = contract_dict[key]["预计到港日期"]
                    master_df.at[idx, "到港地点"] = contract_dict[key]["到港地点"]
                    master_df.at[idx, "发运方式"] = contract_dict[key]["发运方式"]
                    master_df.at[idx, "物流运输单号"] = contract_dict[key]["物流运输单号"]
    
    # ==================== Step 6: 关联发车申请 ====================
    ship_df = data_sources.get("发车申请", {}).get("df", pd.DataFrame())
    if not ship_df.empty:
        # 查找关键列
        ship_app_col = find_column_by_keywords(ship_df, ["发车申请单号", "申请单号"])
        ship_no_col = find_column_by_keywords(ship_df, ["发车号", "车次"])
        ship_date_col = find_column_by_keywords(ship_df, ["发车日期", "发车时间"])
        eta_port_col = find_column_by_keywords(ship_df, ["预计到港日期", "预计到达"])
        dest_col = find_column_by_keywords(ship_df, ["到港地点", "目的港", "目的地"])
        creator_col = find_column_by_keywords(ship_df, ["创建人"])
        
        if ship_app_col:
            # 清洗关联键
            ship_df["_发车申请单号"] = clean_join_key(ship_df[ship_app_col])
            
            # 创建匹配字典
            ship_dict = {}
            for _, row in ship_df.iterrows():
                app_no = str(row["_发车申请单号"])
                
                ship_no = ""
                if ship_no_col and pd.notna(row.get(ship_no_col)):
                    ship_no = str(row[ship_no_col])
                
                ship_date = ""
                if ship_date_col and pd.notna(row.get(ship_date_col)):
                    ship_date = str(row[ship_date_col])
                
                eta_port = ""
                if eta_port_col and pd.notna(row.get(eta_port_col)):
                    eta_port = str(row[eta_port_col])
                
                dest = ""
                if dest_col and pd.notna(row.get(dest_col)):
                    dest = str(row[dest_col])
                
                creator = ""
                if creator_col and pd.notna(row.get(creator_col)):
                    creator = str(row[creator_col])
                
                ship_dict[app_no] = {
                    "发车号": ship_no,
                    "发车日期": ship_date,
                    "预计到港日期": eta_port,
                    "到港地点": dest,
                    "创建人": creator
                }
            
            # 执行匹配
            for idx, row in master_df.iterrows():
                app_no = str(row.get("发车申请单号", ""))
                
                if app_no in ship_dict:
                    master_df.loc[idx, "发车号"] = ship_dict[app_no]["发车号"]
                    master_df.loc[idx, "发车日期"] = ship_dict[app_no]["发车日期"]
                    master_df.loc[idx, "预计到港日期"] = ship_dict[app_no]["预计到港日期"]
                    master_df.loc[idx, "到港地点"] = ship_dict[app_no]["到港地点"]
                    master_df.loc[idx, "创建人"] = ship_dict[app_no]["创建人"]
    
    # ==================== Step 7: 添加状态诊断列 ====================
    def get_diagnostic_status(row):
        """
        根据匹配情况生成状态标签（用于分类）
        
        逻辑：
        - 若单号对上（匹配类型=确认）：显示 "🟢 确认为已购"
        - 若满足疑似条件（匹配类型=疑似）：显示 "🟡 疑似已购"（箱号单独在箱号列显示）
        - 若仅物料对上（匹配类型=不相关）：显示 "🔴 存在不相关采购"
        - 若物料号也未匹配：显示 "❌ 未匹配"
        
        注意：不再在状态诊断列显示"疑似已装箱"，如有箱号请查看箱号列
        """
        match_type = row.get("匹配类型")
        
        if match_type == "确认":
            return "🟢 确认为已购"
        elif match_type == "疑似":
            # 统一返回"疑似已购"，箱号信息在箱号列显示
            return "🟡 疑似已购"
        elif match_type == "不相关":
            return "🔴 存在不相关采购"
        else:
            return "❌ 未匹配"
    
    def get_diagnostic_description(row):
        """
        根据匹配情况生成详细的诊断说明
        
        逻辑：
        - 确认为已购：显示"单号精确匹配"
        - 疑似已购：显示"物料号一致，且采购发生在需求后第X天，但未填单号"
        - 存在不相关采购：显示"物料号匹配，但时间不吻合（采购在需求之前或超过60天）"
        - 未匹配：显示"无相关采购记录"
        """
        match_type = row.get("匹配类型")
        
        if match_type == "确认":
            return "单号精确匹配"
        elif match_type == "疑似":
            days_diff = row.get("_疑似天数差")
            if pd.notna(days_diff):
                return f"物料号一致，且采购发生在需求后第{int(days_diff)}天，但未填单号"
            else:
                return "物料号一致，时间窗口匹配，但未填单号"
        elif match_type == "不相关":
            days_diff = row.get("_不相关天数差")
            if pd.notna(days_diff):
                if days_diff < 0:
                    return f"物料号匹配，但时间不吻合（采购在需求之前{abs(int(days_diff))}天）"
                else:
                    return f"物料号匹配，但时间不吻合（采购在需求后{int(days_diff)}天，超过60天窗口）"
            else:
                return "物料号匹配，但时间不吻合（采购在需求之前或超过60天）"
        else:
            return "无相关采购记录"
    
    # 应用状态诊断
    master_df["状态诊断"] = master_df.apply(get_diagnostic_status, axis=1)
    master_df["诊断说明"] = master_df.apply(get_diagnostic_description, axis=1)
    
    return master_df


def render_backorder_chain_tracking():
    """
    渲染缺货全链路追踪页面 V2 (新架构)
    
    【性能优化说明】
    1. load_chain_data_v2() 已缓存，原始数据加载只发生一次（1小时TTL）
    2. build_chain_master_v2() 已缓存，全链路关联只执行一次
    3. 搜索和筛选在内存中完成，使用 pandas 内存级操作（秒速响应）
    
    包含两个视图:
    1. 全局履行监控大表 (Master Overview)
    2. 备件快递进度条 (Visual Tracker)
    """
    import plotly.graph_objects as go
    
    st.title(get_text("backorder.page_title"))
    st.markdown("---")
    
    # ==================== 加载数据 ====================
    # 【优化】第一次加载时执行，之后直接从缓存读取
    with st.spinner(get_text("common.loading") + " (Cached)"):
        data_sources, load_info = load_chain_data_v2()
    
    # ==================== 显示数据源状态 ====================
    col1, col2, col3, col4, col5 = st.columns(5)
    source_names = ["缺货报表", "采购表", "箱号明细", "合同明细", "发车申请"]
    cols = [col1, col2, col3, col4, col5]
    
    for name, col in zip(source_names, cols):
        status = data_sources.get(name, {}).get("status", "pending")
        df = data_sources.get(name, {}).get("df", pd.DataFrame())
        count = len(df) if not df.empty else 0
        
        if status == "success":
            col.success(f"✅ {name}")
        elif status == "pending":
            col.info(f"⏳ {name}")
        else:
            col.error(f"❌ {name}")
    
    st.markdown("---")
    
    # ==================== 构建主表 ====================
    # 【优化】第一次构建时执行，之后直接从缓存读取（如数据源不变）
    with st.spinner("正在构建全链路追踪表（已启用缓存）..."):
        master_df = build_chain_master_v2(data_sources)
    
    if master_df.empty:
        st.warning("⚠️ 无法构建追踪主表，请检查数据源")
        return
    
    st.success(f"🎯 全链路追踪主表已构建，共 {len(master_df)} 条记录")
    
    # ==================== 侧边栏功能 ====================
    with st.sidebar:
        st.markdown("### 🔧 状态筛选器")
        
        # 状态筛选器（multiselect）
        status_options = [
            "🟢 确认为已购",
            "🟡 疑似已购",
            "🔴 存在不相关采购",
            "❌ 未匹配"
        ]
        
        # 【修复】确保默认值为全部状态，保证首次加载显示所有444条记录
        selected_statuses = st.multiselect(
            "选择要显示的订单状态",
            options=status_options,
            default=status_options,  # 【重要】默认全选：显示全部444条
            key="status_filter"
        )
        
        # 【修复】如果用户清空了所有选择，自动重置为显示全部
        if len(selected_statuses) == 0:
            selected_statuses = status_options
        
        st.markdown("---")
        
        # 保留旧的快捷开关（向后兼容）
        hide_suspected = st.checkbox("快捷：隐藏所有疑似已购单", value=False, key="hide_suspected_orders")
        
        # 如果快捷开关被启用，覆盖筛选器设置
        if hide_suspected:
            selected_statuses = [s for s in selected_statuses if s != "🟡 疑似已购"]
    
    # ==================== 渲染全局监控大表 ====================
    render_master_overview(master_df, selected_statuses, data_sources)


def render_master_overview(master_df, selected_statuses=None, data_sources=None):
    """
    渲染全局履行监控大表
    
    新增功能：
    1. 状态诊断列 + 诊断说明列
    2. 高亮显示（确认为已购=浅绿色，疑似=浅橘色）
    3. 侧边栏状态筛选器（multiselect）
    4. 统计看板（4个metric）
    5. 点击疑似行显示穿透对比卡片
    6. 搜索功能（支持订单号、物料号模糊搜索）
    
    表格列定义:
    [缺货端]: 客户订单号、物料号、物料描述、未发数量、提取创建时间、状态诊断、诊断说明
    [采购端]: SAP订单号、SAP提交时间、ETA (空值显示"待采购")
    [交付端]: 箱号、装箱日期 (空值显示"待备货")
    [合同端]: 合同号、合同日期 (空值显示"未做合同")
    [物流端]: 发车号、预计到港日期、到港地点、创建人
    """
    st.markdown("### 📊 全局履行监控大表")
    
    # ==================== 搜索功能 ====================
    search_text = st.text_input(
        "🔍 搜索订单号或物料号", 
        placeholder="输入客户订单号或物料号进行模糊搜索...",
        key="backorder_search"
    )
    
    # 如果selected_statuses为None，显示全部（向后兼容）
    if selected_statuses is None:
        selected_statuses = ["🟢 确认为已购", "🟡 疑似已购", "🔴 存在不相关采购", "❌ 未匹配"]
    
    # 根据筛选器过滤数据
    # 【修复】简化状态匹配逻辑：直接精确匹配状态值
    def match_status(status_val):
        """匹配状态值 - 只进行精确匹配"""
        if pd.isna(status_val):
            return False
        status_str = str(status_val).strip()
        
        # 直接与筛选的状态值进行精确匹配
        return status_str in selected_statuses
    
    filtered_df = master_df[master_df["状态诊断"].apply(match_status)].copy()
    
    # ==================== 应用搜索过滤 ====================
    if search_text:
        # 查找客户订单号和物料号列
        order_col = find_column_by_keywords(filtered_df, ["客户订单号", "订单号", "需求单号"])
        part_col = find_column_by_keywords(filtered_df, ["物料号", "备件号"])
        
        # 执行模糊搜索
        mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)
        
        if order_col:
            mask |= filtered_df[order_col].astype(str).str.contains(search_text, case=False, na=False)
        
        if part_col:
            mask |= filtered_df[part_col].astype(str).str.contains(search_text, case=False, na=False)
        
        filtered_df = filtered_df[mask]
        
        if len(filtered_df) == 0:
            st.warning(f"🔍 未找到包含 '{search_text}' 的记录")
            return
        else:
            st.success(f"🔍 找到 {len(filtered_df)} 条匹配记录")
    
    st.markdown("---")
    
    # ==================== 统计看板（4个指标卡）====================
    st.markdown("### 📈 订单状态统计")
    
    # 计算各状态的数量（基于当前筛选器）
    confirmed_count = len(filtered_df[filtered_df["状态诊断"] == "🟢 确认为已购"])
    suspected_count = len(filtered_df[filtered_df["状态诊断"] == "🟡 疑似已购"])
    irrelevant_count = len(filtered_df[filtered_df["状态诊断"] == "🔴 存在不相关采购"])
    unmatched_count = len(filtered_df[filtered_df["状态诊断"] == "❌ 未匹配"])
    
    # 使用4列布局显示指标卡
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="🟢 确认为已购",
            value=f"{confirmed_count}",
            delta="单号精确匹配",
            delta_color="normal"
        )
    
    with col2:
        st.metric(
            label="🟡 疑似已购",
            value=f"{suspected_count}",
            delta="时间+物料匹配",
            delta_color="off"
        )
    
    with col3:
        st.metric(
            label="🔴 存在不相关采购",
            value=f"{irrelevant_count}",
            delta="仅物料匹配",
            delta_color="off"
        )
    
    with col4:
        st.metric(
            label="❌ 未匹配",
            value=f"{unmatched_count}",
            delta="无相关采购",
            delta_color="off"
        )
    
    st.markdown("---")
    
    # 根据侧边栏开关过滤数据（旧代码保留兼容）
    # 【修复】只在用户实际修改了筛选条件时才显示
    total_possible_statuses = len([
        "🟢 确认为已购",
        "🟡 疑似已购",
        "🔴 存在不相关采购",
        "❌ 未匹配"
    ])
    
    # 检查是否真的启用了筛选（选择数少于全部状态）
    is_filtering_active = len(selected_statuses) < total_possible_statuses
    
    if is_filtering_active:
        st.info(f"🔍 已启用筛选：当前显示 {len(filtered_df)} / {len(master_df)} 条记录")
    else:
        # 用户没有修改筛选条件，应该显示全部记录
        if len(filtered_df) < len(master_df):
            st.warning(
                f"⚠️ 数据异常提示：未应用筛选时仍有 {len(master_df) - len(filtered_df)} 条记录不可见。"
                f"当前显示 {len(filtered_df)} / {len(master_df)} 条记录。"
                f"可能原因：状态诊断值异常。请联系管理员检查数据。"
            )
    
    # 准备显示数据
    display_cols = []
    
    # 缺货端列（优先显示）
    for col_name in ["客户订单号", "物料号", "物料描述"]:
        col = find_column_by_keywords(filtered_df, [col_name])
        if col:
            display_cols.append(col)
    
    # 添加未发数量和提取创建时间
    if "_未发数量" in filtered_df.columns:
        display_cols.append("_未发数量")
    
    # 【新增】添加美国/加拿大库存（位置在未发数量之后）
    if "美国/加拿大库存" in filtered_df.columns:
        display_cols.append("美国/加拿大库存")
    
    if "提取创建时间" in filtered_df.columns:
        display_cols.append("提取创建时间")
    
    # 添加状态诊断列（必须显示）
    if "状态诊断" in filtered_df.columns:
        display_cols.append("状态诊断")
    
    # 添加诊断说明列（必须显示）
    if "诊断说明" in filtered_df.columns:
        display_cols.append("诊断说明")
    
    # 采购端列（新增主机厂和采购数量）
    for col_name in ["SAP订单号", "主机厂", "SAP提交时间", "ETA", "采购数量"]:
        if col_name in filtered_df.columns:
            display_cols.append(col_name)
    
    # 交付端列（新增装箱数量）
    for col_name in ["箱号", "装箱日期", "装箱数量"]:
        if col_name in filtered_df.columns:
            display_cols.append(col_name)
    
    # 合同端列（新增发车申请单号）
    for col_name in ["合同号", "合同日期", "发车申请单号"]:
        if col_name in filtered_df.columns:
            display_cols.append(col_name)
    
    # 物流端列（新增发运方式、物流运输单号）
    for col_name in ["预计到港日期", "到港地点", "发运方式", "物流运输单号"]:
        if col_name in filtered_df.columns:
            display_cols.append(col_name)
    
    # 过滤存在的列
    display_cols = [col for col in display_cols if col in filtered_df.columns]
    
    if not display_cols:
        st.warning("无法显示数据")
        return
    
    # 创建显示DataFrame
    display_df = filtered_df[display_cols].copy()
    
    # 重命名列为友好名称
    rename_map = {
        "_未发数量": "未发数量",
    }
    display_df = display_df.rename(columns=rename_map)
    
    # 【修复1】格式化数量列：最多显示2位小数
    for col in ["未发数量", "采购数量", "装箱数量", "美国/加拿大库存"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(
                lambda x: f"{float(x):.2f}".rstrip('0').rstrip('.') if pd.notna(x) and str(x) not in ["", "待采购", "nan", "None"] else x
            )
    
    # 【升级】智能空值处理 + 异常提醒 + 物流状态
    from datetime import datetime, timedelta
    
    for idx, row in display_df.iterrows():
        # 获取SAP订单号判断采购状态
        sap_order = row.get("SAP订单号", "")
        has_sap = sap_order and str(sap_order).strip() and str(sap_order) not in ["", "待采购", "nan", "None"]
        
        # 获取合同号判断合同状态
        contract_no = row.get("合同号", "")
        has_contract = contract_no and str(contract_no).strip() and str(contract_no) not in ["", "未做合同", "nan", "None"]
        
        # 处理箱号列的空值显示
        if "箱号" in display_df.columns:
            box_no = row.get("箱号", "")
            has_box = box_no and str(box_no).strip() and str(box_no) not in ["", "待备货", "nan", "None"]
            
            if has_box:
                # 有箱号：检查数量是否匹配
                proc_qty = row.get("采购数量", 0)
                box_qty = row.get("装箱数量", 0)
                
                # 转换为数值进行对比
                proc_qty_num = pd.to_numeric(proc_qty, errors="coerce")
                box_qty_num = pd.to_numeric(box_qty, errors="coerce")
                
                # 如果采购数量和装箱数量不相等且都有值，添加警告图标
                if pd.notna(proc_qty_num) and pd.notna(box_qty_num) and proc_qty_num != box_qty_num:
                    display_df.at[idx, "箱号"] = f"⚠️ {box_no}"
                else:
                    display_df.at[idx, "箱号"] = str(box_no)
            elif has_sap:
                # 有SAP单号但无箱号
                display_df.at[idx, "箱号"] = "📦 待装箱"
            else:
                # 连SAP单号都没有
                display_df.at[idx, "箱号"] = "⏳ 待采购"
        
        # 处理其他空值显示
        if "SAP订单号" in display_df.columns:
            if not has_sap:
                display_df.at[idx, "SAP订单号"] = "⏳ 待采购"
        
        if "ETA" in display_df.columns:
            eta = row.get("ETA", "")
            if not eta or str(eta).strip() in ["", "nan", "None"]:
                display_df.at[idx, "ETA"] = "⏳ 待采购" if not has_sap else ""
        
        if "主机厂" in display_df.columns:
            factory = row.get("主机厂", "")
            if not factory or str(factory).strip() in ["", "nan", "None"]:
                display_df.at[idx, "主机厂"] = ""
        
        # 【新增】物流状态智能显示
        if "合同号" in display_df.columns:
            if not has_contract:
                # 无合同号
                display_df.at[idx, "合同号"] = "📋 待签合同"
        
        # 【修复】预计到港日期 - 只显示原始日期值，不添加任何额外状态文本
        if "预计到港日期" in display_df.columns:
            eta_port = row.get("预计到港日期", "")
            
            if eta_port and str(eta_port).strip() not in ["", "nan", "None"]:
                # 直接显示日期，不添加图标、状态文字或描述
                try:
                    # 尝试解析日期并转换为标准格式 YYYY-MM-DD
                    eta_date = pd.to_datetime(str(eta_port))
                    formatted_date = eta_date.strftime("%Y-%m-%d")
                    display_df.at[idx, "预计到港日期"] = formatted_date
                except:
                    # 如果解析失败，保留原值
                    display_df.at[idx, "预计到港日期"] = str(eta_port)
            else:
                # 无预计到港日期时显示空白
                display_df.at[idx, "预计到港日期"] = ""
        
        # 【新增】到港地点空值处理
        if "到港地点" in display_df.columns:
            dest = row.get("到港地点", "")
            if not dest or str(dest).strip() in ["", "nan", "None"]:
                display_df.at[idx, "到港地点"] = ""
        
        # 【新增】发运方式空值处理
        if "发运方式" in display_df.columns:
            ship_method = row.get("发运方式", "")
            if not ship_method or str(ship_method).strip() in ["", "nan", "None"]:
                display_df.at[idx, "发运方式"] = ""
        
        # 【新增】物流运输单号空值处理
        if "物流运输单号" in display_df.columns:
            logistics_no = row.get("物流运输单号", "")
            if not logistics_no or str(logistics_no).strip() in ["", "nan", "None"]:
                display_df.at[idx, "物流运输单号"] = ""
    
    # 格式化日期列
    for col in display_df.columns:
        if "日期" in col or "时间" in col:
            display_df[col] = display_df[col].apply(
                lambda x: str(x)[:10] if pd.notna(x) and str(x) not in ["待采购", "待备货", "未做合同"] else x
            )
    
    # 创建高亮样式函数
    def highlight_rows(row):
        """
        根据状态诊断列高亮行：
        - 🟢 确认为已购：浅绿色 rgba(144, 238, 144, 0.3)
        - 🟡 疑似已购：浅橘色 rgba(255, 200, 100, 0.3)
        - 🔴 存在不相关采购：浅红色 rgba(255, 182, 193, 0.3)
        """
        if "状态诊断" not in row:
            return [''] * len(row)
        
        status = row.get("状态诊断", "")
        
        if status == "🟢 确认为已购":
            return ['background-color: rgba(144, 238, 144, 0.3)'] * len(row)
        elif status == "🟡 疑似已购":
            return ['background-color: rgba(255, 200, 100, 0.3)'] * len(row)
        elif status == "🔴 存在不相关采购":
            return ['background-color: rgba(255, 182, 193, 0.3)'] * len(row)
        else:
            return [''] * len(row)
    
    # 应用样式并显示表格
    styled_df = display_df.style.apply(highlight_rows, axis=1)
    
    st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True,
        height=500
    )
    
    st.caption(get_text_safe("backorder_tracker.total_records", current=len(filtered_df), original=len(master_df)))
    
    # ==================== 穿透对比卡片 ====================
    st.markdown("---")
    st.markdown(f"### {get_text('backorder_tracker.suspected_order_comparison')}")
    
    # 提取疑似行（只需检查确切的"🟡 疑似已购"状态）
    suspected_df = filtered_df[filtered_df["状态诊断"] == "🟡 疑似已购"]
    
    if suspected_df.empty:
        st.success(get_text("backorder_tracker.no_suspected_orders"))
    else:
        # 统计疑似已装箱的数量（即有箱号的疑似订单）
        suspected_packed = len(suspected_df[
            (suspected_df["箱号"].notna()) & 
            (suspected_df["箱号"].astype(str).str.strip() != "") &
            (~suspected_df["箱号"].astype(str).isin(["待备货", "nan", "None", ""]))
        ])
        suspected_unpacked = len(suspected_df) - suspected_packed
        
        st.info(get_text_safe("backorder_tracker.suspected_found_info", total=len(suspected_df), packed=suspected_packed, unpacked=suspected_unpacked))
        
        # 创建选择器
        suspected_list = []
        for idx, row in suspected_df.iterrows():
            order_col = find_column_by_keywords(suspected_df, ["客户订单号", "订单号"])
            part_col = find_column_by_keywords(suspected_df, ["物料号"])
            
            order_no = row.get(order_col, "N/A") if order_col else "N/A"
            part_no = row.get(part_col, "N/A") if part_col else "N/A"
            
            suspected_list.append(f"{order_no} - {part_no}")
        
        selected = st.selectbox(
            get_text("backorder_tracker.select_suspected_order"),
            options=range(len(suspected_list)),
            format_func=lambda x: suspected_list[x],
            key="suspected_order_selector"
        )
        
        if selected is not None:
            # 获取选中的行
            selected_row = suspected_df.iloc[selected]
            
            # 左右两列布局
            col_left, col_right = st.columns(2)
            
            with col_left:
                st.markdown(f"#### {get_text('backorder_tracker.backorder_detail_title')}")
                
                # 查找列名
                order_col = find_column_by_keywords(suspected_df, ["客户订单号", "订单号"])
                part_col = find_column_by_keywords(suspected_df, ["物料号"])
                desc_col = find_column_by_keywords(suspected_df, ["物料描述"])
                
                if order_col:
                    st.write(f"**{get_text('backorder_tracker.customer_order_no')}:** {selected_row.get(order_col, 'N/A')}")
                if part_col:
                    st.write(f"**{get_text('backorder_tracker.part_no')}:** {selected_row.get(part_col, 'N/A')}")
                if desc_col:
                    st.write(f"**{get_text('backorder_tracker.part_desc')}:** {selected_row.get(desc_col, 'N/A')}")
                
                st.write(f"**{get_text('backorder_tracker.unshipped_qty')}:** {selected_row.get('_未发数量', 'N/A')}")
                
                create_time = selected_row.get("提取创建时间")
                if pd.notna(create_time):
                    st.write(f"**{get_text('backorder_tracker.create_time')}:** {str(create_time)[:10]}")
                else:
                    st.write(f"**{get_text('backorder_tracker.create_time')}:** N/A")
            
            with col_right:
                st.markdown(f"#### {get_text('backorder_tracker.closest_procurement')}")
                
                sap_order = selected_row.get("SAP订单号", "N/A")
                st.write(f"**{get_text('backorder_tracker.sap_order_no')}:** {sap_order}")
                
                # 显示主机厂信息
                factory = selected_row.get("主机厂", "")
                if factory and str(factory).strip() not in ["", "nan", "None"]:
                    st.write(f"**{get_text('backorder_tracker.factory')}:** {factory}")
                
                # 从采购表中查找详细信息
                if data_sources and sap_order and sap_order not in ["N/A", "待采购", "⏳ 待采购"]:
                    proc_df = data_sources.get("采购表", {}).get("df", pd.DataFrame())
                    if not proc_df.empty:
                        sap_order_col = find_column_by_keywords(proc_df, ["SAP订单号", "SAP No"])
                        if sap_order_col:
                            matching_proc = proc_df[proc_df[sap_order_col].astype(str).str.strip() == str(sap_order).strip()]
                            if not matching_proc.empty:
                                proc_row = matching_proc.iloc[0]
                                
                                # 查找负责人列
                                owner_col = find_column_by_keywords(proc_df, ["负责人", "采购员", "创建人"])
                                if owner_col:
                                    st.write(f"**{get_text('backorder_tracker.responsible_person')}:** {proc_row.get(owner_col, 'N/A')}")
                                
                                # 查找数量列
                                qty_col = find_column_by_keywords(proc_df, ["数量"])
                                if qty_col:
                                    st.write(f"**{get_text('backorder_tracker.procurement_qty')}:** {proc_row.get(qty_col, 'N/A')}")
                
                submit_time = selected_row.get("SAP提交时间")
                if pd.notna(submit_time):
                    st.write(f"**{get_text('backorder_tracker.sap_submit_time')}:** {str(submit_time)[:10]}")
                else:
                    st.write(f"**{get_text('backorder_tracker.sap_submit_time')}:** N/A")
                
                eta = selected_row.get("ETA", "N/A")
                st.write(f"**{get_text('backorder_tracker.eta')}:** {eta}")
                
                # 显示装箱信息（如果有）
                box_no = selected_row.get("箱号", "")
                if box_no and str(box_no).strip() not in ["", "nan", "None", "待备货", "📦 待装箱", "⏳ 待采购"]:
                    st.markdown("---")
                    st.markdown("**📦 装箱信息:**")
                    # 去掉警告图标显示原始箱号
                    clean_box_no = str(box_no).replace("⚠️ ", "")
                    st.write(f"**{get_text('backorder_tracker.box_no')}:** {clean_box_no}")
                    
                    box_date = selected_row.get("装箱日期", "")
                    if box_date and str(box_date).strip() not in ["", "nan", "None"]:
                        st.write(f"**{get_text('backorder_tracker.box_date')}:** {str(box_date)[:10]}")
                    
                    box_qty = selected_row.get("装箱数量", "")
                    if box_qty and str(box_qty).strip() not in ["", "nan", "None", "0"]:
                        st.write(f"**装箱数量:** {box_qty}")
                
                st.warning(get_text("backorder_tracker.suspect_match_warning"))
    
    st.markdown("---")


def render_visual_tracker(master_df):
    """
    渲染备件快递进度条
    
    交互: 搜索 NPOUS 号或物料号
    视觉: 垂直时间轴
    节点:
    1. 缺货登记
    2. 采购确认
    3. 仓库装箱
    4. 合同完成
    5. 物流在途
    """
    st.markdown(f"### {get_text('backorder_tracker.visual_tracker')}")
    
    # 搜索框
    col1, col2 = st.columns([3, 1])
    
    with col1:
        search_key = st.text_input(
            get_text("backorder_tracker.search_placeholder"),
            placeholder=get_text("backorder_tracker.search_placeholder_eg"),
            key="tracker_search"
        )
    
    with col2:
        search_type = st.selectbox(
            get_text("backorder_tracker.search_type"),
            [get_text("backorder_tracker.customer_order_no"), get_text("backorder_tracker.part_no")]
        )
    
    if not search_key:
        st.info(get_text("backorder_tracker.enter_search_keyword"))
        return
    
    # 执行搜索
    if search_type == get_text("backorder_tracker.customer_order_no"):
        results = master_df[master_df["_客户订单号"].astype(str).str.contains(search_key, na=False)]
    else:
        results = master_df[master_df["_物料号"].astype(str).str.contains(search_key, na=False)]
    
    if results.empty:
        st.warning(get_text("backorder_tracker.no_matching_records"))
        return
    
    st.success(get_text_safe("backorder_tracker.found_records", count=len(results)))
    
    # 显示搜索结果（取第一条）
    row = results.iloc[0]
    
    # 构建垂直时间轴
    st.markdown("---")
    
    # 节点 1: 缺货登记
    with st.expander(get_text("backorder_tracker.node1_title"), expanded=True):
        st.markdown(f"**{get_text('backorder_tracker.status_completed')}**")
        st.write(f"**{get_text('backorder_tracker.customer_order_no')}:** {row.get('订单号_原始', 'N/A')}")
        st.write(f"**{get_text('backorder_tracker.part_no')}:** {row.get('物料号_原始', 'N/A')}")
        st.write(f"**{get_text('backorder_tracker.part_desc')}:** {row.get('物料描述', 'N/A')}")
        if "缺货数量" in row:
            st.write(f"**缺货数量:** {row.get('缺货数量', 'N/A')}")
    
    # 节点 2: 采购确认
    sap_order = row.get("SAP订单号", "")
    sap_status = get_text("backorder_tracker.status_completed") if sap_order and str(sap_order) not in ["", "待采购"] else get_text("backorder_tracker.status_in_progress")
    with st.expander(f"{get_text('backorder_tracker.node2_title')} ({sap_status})", expanded=True):
        if sap_order and str(sap_order) not in ["", "待采购"]:
            st.write(f"**{get_text('backorder_tracker.sap_order_no')}:** {sap_order}")
            st.write(f"**{get_text('backorder_tracker.sap_submit_time')}:** {row.get('SAP提交时间', 'N/A')}")
            st.write(f"**{get_text('backorder_tracker.eta')}:** {row.get('ETA', 'N/A')}")
        else:
            st.info(get_text("backorder_tracker.waiting_procurement"))
    
    # 节点 3: 仓库装箱
    box_no = row.get("箱号", "")
    box_status = get_text("backorder_tracker.status_completed") if box_no and str(box_no) not in ["", "待备货"] else get_text("backorder_tracker.status_in_progress")
    with st.expander(f"{get_text('backorder_tracker.node3_title')} ({box_status})", expanded=True):
        if box_no and str(box_no) not in ["", "待备货"]:
            st.write(f"**{get_text('backorder_tracker.box_no')}:** {box_no}")
            st.write(f"**{get_text('backorder_tracker.box_date')}:** {row.get('装箱日期', 'N/A')}")
        else:
            st.info(get_text("backorder_tracker.waiting_warehouse"))
    
    # 节点 4: 合同完成
    contract_no = row.get("合同号", "")
    contract_status = get_text("backorder_tracker.status_completed") if contract_no and str(contract_no) not in ["", "未做合同"] else get_text("backorder_tracker.status_in_progress")
    with st.expander(f"{get_text('backorder_tracker.node4_title')} ({contract_status})", expanded=True):
        if contract_no and str(contract_no) not in ["", "未做合同"]:
            st.write(f"**{get_text('backorder_tracker.contract_no')}:** {contract_no}")
            st.write(f"**{get_text('backorder_tracker.contract_date')}:** {row.get('合同日期', 'N/A')}")
        else:
            st.info(get_text("backorder_tracker.waiting_contract"))
    
    # 节点 5: 物流在途
    ship_no = row.get("发车号", "")
    ship_status = get_text("backorder_tracker.status_completed") if ship_no and str(ship_no) else get_text("backorder_tracker.status_in_progress")
    with st.expander(f"{get_text('backorder_tracker.node5_title')} ({ship_status})", expanded=True):
        if ship_no and str(ship_no):
            st.write(f"**{get_text('backorder_tracker.ship_no')}:** {ship_no}")
            st.write(f"**{get_text('backorder_tracker.ship_date')}:** {row.get('发车日期', 'N/A')}")
            st.write(f"**{get_text('backorder_tracker.eta_arrival')}:** {row.get('预计到港日期', 'N/A')}")
            st.write(f"**{get_text('backorder_tracker.arrival_location')}:** {row.get('到港地点', 'N/A')}")
            st.write(f"**{get_text('backorder_tracker.creator')}:** {row.get('创建人', 'N/A')}")
        else:
            st.info(get_text("backorder_tracker.waiting_shipment"))


def main():
    """
    模块入口（用于独立测试）
    """
    render_sales_dashboard()


if __name__ == "__main__":
    main()
