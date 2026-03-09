# -*- coding: utf-8 -*-
"""
库存追踪看板模块 (Inventory Tracking Dashboard)

全链路在途追踪 - 正向状态追踪法

功能:
1. 库存追踪看板: 广义在途库存分布 (四阶段)
2. 库存健康诊断: 安全库存、再订货点、健康评分
3. 物料详情: 按物料号查看四阶段分布
4. 异常清单: 数据质量问题记录

数据源:
- A表: miles采购表 (采购需求)
- B表: 温新宇可用的箱号明细 (装箱状态)
- C表: dayu可用的进出口备件合同明细 (合同状态)
- D表: 海上在途1.xlsx (海上在途)
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from core.i18n import get_text
from core.inventory_engine import run_inventory_pipeline, get_summary_stats, validate_data_quality
from core.inventory_health_engine import run_health_diagnostic


def load_inventory_data(start_date=None):
    """加载库存追踪数据"""
    if start_date is None:
        from core.inventory_engine import DATE_ANCHOR
        start_date = DATE_ANCHOR
    
    return run_inventory_pipeline(start_date)


def render_inventory_dashboard():
    """渲染库存管理页面（根据功能选择显示对应内容）"""
    curr_lang = st.session_state.get("lang", "ZH")
    
    # 页面标题
    st.title("📦 " + ("库存管理" if curr_lang == "ZH" else "Inventory Management"))
    st.markdown("---")
    
    # 检查是否有指定的功能ID（从session_state获取）
    # 由于app.py中没有传递参数，我们检查session_state中的当前功能
    current_page_id = st.session_state.get("current_page_id", "inventory_tracking")
    
    # 根据功能ID显示对应内容
    if current_page_id == "inventory_health":
        # 直接显示库存健康诊断（不带Tab）
        render_inventory_health(curr_lang)
    else:
        # 默认显示库存追踪
        render_inventory_tracking(curr_lang)


def render_inventory_tracking(curr_lang: str):
    """渲染库存追踪看板"""
    
    # ========== 侧边栏: 筛选条件 ==========
    sidebar_title = "🔍 " + ("筛选条件" if curr_lang == "ZH" else "Filters")
    st.sidebar.markdown(f"### {sidebar_title}")
    
    # 日期选择器
    from core.inventory_engine import DATE_ANCHOR
    date_label = "开始日期" if curr_lang == "ZH" else "Start Date"
    date_option = st.sidebar.date_input(
        date_label,
        value=DATE_ANCHOR.date(),
        min_value=datetime(2024, 1, 1).date(),
        max_value=datetime.today().date()
    )
    
    # 刷新按钮
    refresh_label = "🔄 " + ("刷新数据" if curr_lang == "ZH" else "Refresh Data")
    refresh_btn = st.sidebar.button(
        refresh_label,
        key="inventory_refresh_btn"
    )
    
    # ========== 加载数据 ==========
    # 注意：不使用cache_data因为返回的是dict包含DataFrame
    if "inventory_result" not in st.session_state or refresh_btn:
        loading_text = "加载库存追踪数据..." if curr_lang == "ZH" else "Loading inventory tracking data..."
        with st.spinner(loading_text):
            try:
                st.session_state.inventory_result = load_inventory_data(pd.Timestamp(date_option))
            except Exception as e:
                error_text = f"加载数据失败: {e}" if curr_lang == "ZH" else f"Failed to load data: {e}"
                st.error(error_text)
                return
    
    result = st.session_state.get("inventory_result")
    
    # 检查结果是否有效
    if result is None:
        no_data_text = "暂无库存追踪数据" if curr_lang == "ZH" else "No inventory data available"
        st.warning(no_data_text)
        return
    
    if not isinstance(result, dict) or "summary" not in result:
        no_data_text = "暂无库存追踪数据" if curr_lang == "ZH" else "No inventory data available"
        st.warning(no_data_text)
        return
    
    df = result.get("summary")
    
    if df is None or df.empty:
        no_data_text = "暂无库存追踪数据" if curr_lang == "ZH" else "No inventory data available"
        st.warning(no_data_text)
        return
    
    # 确保必要的列存在
    required_cols = ["_stage1_domestic", "_stage2_boxed", "_stage3_approval", "_stage4_shipping"]
    for col in required_cols:
        if col not in df.columns:
            df[col] = 0
    if "_received_proxy" not in df.columns:
        df["_received_proxy"] = 0
    
    # ========== 数据质量提示 ==========
    quality = validate_data_quality(result)
    if quality.get("status") == "ok":
        st.success("✅ 数据质量校验通过 - 守恒率: 100%" if curr_lang == "ZH" else "✅ Data Quality Pass - Consistency: 100%")
    else:
        st.warning("⚠️ 数据质量存在异常" if curr_lang == "ZH" else "⚠️ Data Quality Warning")
    
    # ========== 汇总统计 ==========
    stats = get_summary_stats(result)
    
    st.markdown("### 📊 广义在途库存总览" if curr_lang == "ZH" else "### 📊 In-Transit Inventory Overview")
    
    # KPI 指标卡
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(
            label="总物料数" if curr_lang == "ZH" else "Total SKUs",
            value=f"{stats.get('total_parts', 0):,}"
        )
    
    with col2:
        st.metric(
            label="总需求" if curr_lang == "ZH" else "Total Demand",
            value=f"{stats.get('total_demand', 0):,}"
        )
    
    with col3:
        st.metric(
            label="广义在途" if curr_lang == "ZH" else "In Transit",
            value=f"{stats.get('total_in_transit', 0):,}"
        )
    
    with col4:
        value_k = stats.get('total_value', 0) / 1000
        st.metric(
            label="总货值(K)" if curr_lang == "ZH" else "Total Value(K)",
            value=f"{value_k:,.1f}K"
        )
    
    with col5:
        # 计算在途占比
        transit_ratio = stats.get('total_in_transit', 0) / max(stats.get('total_demand', 1), 1) * 100
        st.metric(
            label="在途占比" if curr_lang == "ZH" else "Transit Ratio",
            value=f"{transit_ratio:.1f}%"
        )
    
    st.markdown("---")
    
    # ========== 四级状态分布 ==========
    st.markdown("### 🔄 四级在途状态分布" if curr_lang == "ZH" else "### 🔄 Four-Stage Distribution")
    
    # 创建状态数据
    stage_data = pd.DataFrame([
        {
            "stage": "Stage1: 未装箱" if curr_lang == "ZH" else "Stage1: Unboxed",
            "quantity": stats.get('stage1_domestic', 0),
            "color": "#3498db"
        },
        {
            "stage": "Stage2: 装箱未合同" if curr_lang == "ZH" else "Stage2: Boxed Not Contracted",
            "quantity": stats.get('stage2_boxed', 0),
            "color": "#e67e22"
        },
        {
            "stage": "Stage3: 合同审批中" if curr_lang == "ZH" else "Stage3: Contract Approval",
            "quantity": stats.get('stage3_approval', 0),
            "color": "#9b59b6"
        },
        {
            "stage": "Stage4: 海上在途" if curr_lang == "ZH" else "Stage4: In Transit (Sea)",
            "quantity": stats.get('stage4_shipping', 0),
            "color": "#1abc9c"
        }
    ])
    
    # 横向柱状图
    fig_stages = px.bar(
        stage_data,
        x="quantity",
        y="stage",
        orientation="h",
        text="quantity",
        color="color",
        color_discrete_map="identity",
        title="四级在途数量分布" if curr_lang == "ZH" else "Four-Stage Quantity Distribution"
    )
    
    fig_stages.update_layout(
        xaxis_title="数量" if curr_lang == "ZH" else "Quantity",
        yaxis_title="状态" if curr_lang == "ZH" else "Stage",
        showlegend=False,
        height=400
    )
    
    st.plotly_chart(fig_stages, use_container_width=True)
    
    # ========== 饼图 ==========
    col_pie1, col_pie2 = st.columns(2)
    
    with col_pie1:
        st.markdown("#### 📊 数量分布" if curr_lang == "ZH" else "#### 📊 Quantity Distribution")
        
        qty_data = pd.DataFrame([
            {"stage": "未装箱", "quantity": stats.get('stage1_domestic', 0)},
            {"stage": "装箱未合同", "quantity": stats.get('stage2_boxed', 0)},
            {"stage": "合同审批中", "quantity": stats.get('stage3_approval', 0)},
            {"stage": "海上在途", "quantity": stats.get('stage4_shipping', 0)},
        ])
        
        fig_donut = px.pie(
            qty_data,
            values="quantity",
            names="stage",
            hole=0.4,
            title="在途数量占比" if curr_lang == "ZH" else "In-Transit Quantity Proportion"
        )
        
        st.plotly_chart(fig_donut, use_container_width=True)
    
    with col_pie2:
        st.markdown("#### 💰 货值分布" if curr_lang == "ZH" else "#### 💰 Value Distribution")
        
        # 计算各阶段货值
        df["_stage1_value"] = df["_stage1_domestic"] * df["_unit_price"]
        df["_stage2_value"] = df["_stage2_boxed"] * df["_unit_price"]
        df["_stage3_value"] = df["_stage3_approval"] * df["_unit_price"]
        df["_stage4_value"] = df["_stage4_shipping"] * df["_unit_price"]
        
        value_data = pd.DataFrame([
            {"stage": "未装箱", "value": df["_stage1_value"].sum()},
            {"stage": "装箱未合同", "value": df["_stage2_value"].sum()},
            {"stage": "合同审批中", "value": df["_stage3_value"].sum()},
            {"stage": "海上在途", "value": df["_stage4_value"].sum()},
        ])
        
        fig_pie = px.pie(
            value_data,
            values="value",
            names="stage",
            hole=0.4,
title="货值占比" if curr_lang == "ZH" else "Value Proportion"
        )
        
        st.plotly_chart(fig_pie, use_container_width=True)
    
    st.markdown("---")
    
    # ========== 物料详情表 ==========
    st.markdown("### 🔍 物料汇总明细" if curr_lang == "ZH" else "### 🔍 Part Summary Details")
    
    # 准备显示数据
    display_cols = [
        "_part_no",
        "_qty_a",
        "_stage1_domestic",
        "_stage2_boxed",
        "_stage3_approval",
        "_stage4_shipping",
        "_received_proxy",
        "_total_in_transit",
        "_total_demand",
        "_unit_price",
        "_total_value"
    ]
    
    # 过滤存在的列
    display_cols = [c for c in display_cols if c in df.columns]
    
    display_df = df[display_cols].copy()
    
    # 重命名列
    col_rename = {
        "_part_no": "物料号" if curr_lang == "ZH" else "Part No",
        "_qty_a": "A表需求" if curr_lang == "ZH" else "Demand(A)",
        "_stage1_domestic": "未装箱" if curr_lang == "ZH" else "Unboxed",
        "_stage2_boxed": "装箱未合同" if curr_lang == "ZH" else "Boxed No Contract",
        "_stage3_approval": "合同审批中" if curr_lang == "ZH" else "Contract Approval",
        "_stage4_shipping": "海上在途" if curr_lang == "ZH" else "In Transit",
        "_received_proxy": "已入库代理" if curr_lang == "ZH" else "Received Proxy",
        "_total_in_transit": "总在途" if curr_lang == "ZH" else "Total In Transit",
        "_total_demand": "总需求" if curr_lang == "ZH" else "Demand",
        "_unit_price": "单价" if curr_lang == "ZH" else "Unit Price",
        "_total_value": "总货值" if curr_lang == "ZH" else "Total Value"
    }
    
    display_df = display_df.rename(columns=col_rename)
    
    # 排序
    display_df = display_df.sort_values("总在途" if curr_lang == "ZH" else "Total In Transit", ascending=False)
    
    # 分页显示
    page_size = 20
    total_pages = (len(display_df) + page_size - 1) // page_size
    
    if "inventory_page" not in st.session_state:
        st.session_state.inventory_page = 1
    
    page = st.number_input(
        "页码" if curr_lang == "ZH" else "Page",
        min_value=1,
        max_value=max(1, total_pages),
        value=st.session_state.inventory_page
    )
    
    st.session_state.inventory_page = page
    
    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, len(display_df))
    
    st.dataframe(
        display_df.iloc[start_idx:end_idx],
        use_container_width=True,
        height=600
    )
    
    st.markdown(f"共 {len(display_df)} 条记录，当前第 {page}/{total_pages} 页")
    
    # ========== 异常清单 ==========
    st.markdown("---")
    st.markdown("### ⚠️ 异常清单" if curr_lang == "ZH" else "### ⚠️ Anomaly List")
    
    anomalies = result.get("anomalies", {})
    
    # 显示异常统计
    col_an1, col_an2, col_an3 = st.columns(3)
    
    with col_an1:
        anomaly_count = len(anomalies.get("b_gt_a", pd.DataFrame()))
        st.metric(
            "B>A 异常数" if curr_lang == "ZH" else "B>A Anomalies",
            anomaly_count
        )
    
    with col_an2:
        anomaly_count = len(anomalies.get("c_gt_b", pd.DataFrame()))
        st.metric(
            "C>B 异常数" if curr_lang == "ZH" else "C>B Anomalies",
            anomaly_count
        )
    
    with col_an3:
        anomaly_count = len(anomalies.get("d_gt_c", pd.DataFrame()))
        st.metric(
            "D>C 异常数" if curr_lang == "ZH" else "D>C Anomalies",
            anomaly_count
        )
    
    # ========== 物料追踪详情 ==========
    st.markdown("---")
    st.markdown("### 🌊 物料追踪详情" if curr_lang == "ZH" else "### 🌊 Part Tracking Details")
    
    # 物料搜索
    part_search = st.selectbox(
        "选择物料号查看详情" if curr_lang == "ZH" else "Select Part No for Details",
        options=sorted(df["_part_no"].unique().tolist())
    )
    
    if part_search:
        part_data = df[df["_part_no"] == part_search].iloc[0]
        
        # 显示物料信息
        col_info1, col_info2 = st.columns(2)
        
        with col_info1:
            st.markdown(f"**物料号:** {part_data['_part_no']}")
            st.markdown(f"**A表需求:** {int(part_data.get('_qty_a', 0))}")
        
        with col_info2:
            st.markdown(f"**单价:** ¥{part_data.get('_unit_price', 0):,.2f}")
            st.markdown(f"**总货值:** ¥{part_data.get('_total_value', 0):,.2f}")
        
        # 瀑布流图
        fig_waterfall = go.Figure(go.Waterfall(
            name="库存追踪",
            orientation="v",
            measure=["relative", "relative", "relative", "relative", "total"],
            x=["未装箱", "装箱未合同", "合同审批中", "海上在途", "总在途"],
            y=[
                part_data["_stage1_domestic"],
                part_data["_stage2_boxed"],
                part_data["_stage3_approval"],
                part_data["_stage4_shipping"],
                part_data["_total_in_transit"]
            ],
            connector={"line": {"color": "rgb(63, 63, 63)"}},
            increasing={"marker": {"color": "#3498db"}},
            decreasing={"marker": {"color": "#e74c3c"}},
            totals={"marker": {"color": "#1abc9c"}}
        ))
        
        fig_waterfall.update_layout(
            title=f"物料 {part_data['_part_no']} 库存追踪瀑布流",
            showlegend=False,
            height=400
        )
        
        st.plotly_chart(fig_waterfall, use_container_width=True)
        
        # 详细指标
        detail_cols = st.columns(5)
        
        with detail_cols[0]:
            st.metric("未装箱", int(part_data["_stage1_domestic"]))
        with detail_cols[1]:
            st.metric("装箱未合同", int(part_data["_stage2_boxed"]))
        with detail_cols[2]:
            st.metric("合同审批中", int(part_data["_stage3_approval"]))
        with detail_cols[3]:
            st.metric("海上在途", int(part_data["_stage4_shipping"]))
        with detail_cols[4]:
            st.metric("总在途", int(part_data["_total_in_transit"]))


def render_inventory_health(curr_lang: str):
    """渲染库存健康诊断"""
    
    # ========== 侧边栏: 筛选条件 ==========
    diag_title = "🔍 " + ("诊断筛选" if curr_lang == "ZH" else "Diagnostic Filters")
    st.sidebar.markdown(f"### {diag_title}")
    
    # 刷新按钮
    refresh_label = "🔄 " + ("刷新诊断" if curr_lang == "ZH" else "Refresh")
    refresh_btn = st.sidebar.button(
        refresh_label,
        key="health_refresh_btn"
    )
    
    # 健康状态筛选
    health_filter_options = ["全部", "积压", "缺货预警", "正常"] if curr_lang == "ZH" else ["All", "Overstock", "Stockout", "Normal"]
    health_filter_label = "健康状态筛选" if curr_lang == "ZH" else "Health Status Filter"
    selected_health_filter = st.sidebar.multiselect(
        health_filter_label,
        health_filter_options,
        default=health_filter_options
    )
    
    # 物料号/物料名称搜索
    search_placeholder = "输入物料号或物料名称..." if curr_lang == "ZH" else "Enter part no or name..."
    search_label = "🔍 " + ("物料号/名称搜索" if curr_lang == "ZH" else "Search Part No/Name")
    search_keyword = st.sidebar.text_input(
        search_label,
        value="",
        placeholder=search_placeholder
    )
    
    # ========== 加载诊断数据 ==========
    if "health_result" not in st.session_state or refresh_btn:
        loading_text = "正在分析库存健康状态..." if curr_lang == "ZH" else "Analyzing inventory health..."
        with st.spinner(loading_text):
            try:
                st.session_state.health_result = run_health_diagnostic()
            except Exception as e:
                error_text = f"加载诊断数据失败: {e}" if curr_lang == "ZH" else f"Failed to load diagnostic data: {e}"
                st.error(error_text)
                return
    
    result = st.session_state.get("health_result")
    
    if result is None or "error" in result:
        no_data_text = "暂无健康诊断数据" if curr_lang == "ZH" else "No health diagnostic data"
        st.warning(no_data_text)
        return
    
    df = result.get("data")
    stats = result.get("stats", {})
    
    if df is None or df.empty:
        st.warning("暂无健康诊断数据" if curr_lang == "ZH" else "No health diagnostic data")
        return
    
    # ========== 诊断汇总统计 ==========
    st.markdown("### 📊 库存健康总览" if curr_lang == "ZH" else "### 📊 Inventory Health Overview")
    
    # 第一行：物料数量指标
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "总物料数" if curr_lang == "ZH" else "Total SKUs",
            f"{stats.get('total_parts', 0):,}"
        )
    
    with col2:
        normal_count = stats.get('normal_parts', 0)
        st.metric(
            "正常" if curr_lang == "ZH" else "Normal",
            f"{normal_count:,}",
            delta_color="normal"
        )
    
    with col3:
        stockout_count = stats.get('stockout_parts', 0)
        st.metric(
            "缺货预警" if curr_lang == "ZH" else "Stockout Alert",
            f"{stockout_count:,}",
            delta_color="inverse"
        )
    
    with col4:
        overstock_count = stats.get('overstock_parts', 0)
        st.metric(
            "积压" if curr_lang == "ZH" else "Overstock",
            f"{overstock_count:,}",
            delta_color="inverse"
        )
    
    # 第二行：库存价值指标
    col5, col6, col7, col8 = st.columns(4)
    
    with col5:
        total_value = stats.get('total_value', 0)
        total_value_k = total_value / 1000
        st.metric(
            "总库存价值(K)" if curr_lang == "ZH" else "Total Inventory Value(K)",
            f"${total_value_k:,.1f}K"
        )
    
    with col6:
        normal_value = stats.get('normal_value', 0)
        normal_value_k = normal_value / 1000
        st.metric(
            "正常库存价值(K)" if curr_lang == "ZH" else "Normal Value(K)",
            f"${normal_value_k:,.1f}K",
            delta_color="normal"
        )
    
    with col7:
        stockout_value = stats.get('stockout_value', 0)
        stockout_value_k = stockout_value / 1000
        st.metric(
            "缺货总价(K)" if curr_lang == "ZH" else "Stockout Value(K)",
            f"${stockout_value_k:,.1f}K",
            delta_color="inverse"
        )
    
    with col8:
        overstock_value = stats.get('overstock_value', 0)
        overstock_value_k = overstock_value / 1000
        st.metric(
            "积压总价(K)" if curr_lang == "ZH" else "Overstock Value(K)",
            f"${overstock_value_k:,.1f}K",
            delta_color="inverse"
        )
    
    st.markdown("---")
    
    # 计算比例
    total = stats.get('total_parts', 1)
    normal_ratio = normal_count / total * 100
    stockout_ratio = stockout_count / total * 100
    overstock_ratio = overstock_count / total * 100
    
    # 进度条显示比例
    st.markdown("#### 库存健康比例" if curr_lang == "ZH" else "#### Health Ratio")
    progress_data = pd.DataFrame({
        "状态": ["正常", "缺货预警", "积压"] if curr_lang == "ZH" else ["Normal", "Stockout", "Overstock"],
        "占比": [normal_ratio, stockout_ratio, overstock_ratio],
        "颜色": ["#27ae60", "#e74c3c", "#f39c12"]
    })
    
    # ========== 健康等级分布 ==========
    st.markdown("### 🏥 健康等级分布" if curr_lang == "ZH" else "### 🏥 Health Level Distribution")
    
    # 健康等级饼图 - 翻译标签
    level_counts = df["health_level"].value_counts()
    
    # 翻译健康等级标签（ZH->EN）
    level_translation = {
        "正常": "Normal",
        "缺货预警": "Stockout",
        "积压": "Overstock"
    }
    
    # 如果是英文，翻译标签
    if curr_lang == "EN":
        translated_counts = level_counts.rename(index=level_translation)
    else:
        translated_counts = level_counts
    
    level_data = pd.DataFrame({
        "level": translated_counts.index,
        "count": translated_counts.values
    })
    
    # 颜色映射（新的三类分类）
    level_colors = {
        "正常": "#27ae60",
        "缺货预警": "#e74c3c",
        "积压": "#f39c12",
        "Normal": "#27ae60",
        "Stockout": "#e74c3c",
        "Overstock": "#f39c12"
    }
    
    fig_pie = px.pie(
        level_data,
        values="count",
        names="level",
        hole=0.4,
        title="健康等级占比" if curr_lang == "ZH" else "Health Level Proportion",
        color="level",
        color_discrete_map=level_colors
    )
    
    st.plotly_chart(fig_pie, use_container_width=True)
    
    st.markdown("---")
    
    # 应用侧边栏健康状态筛选
    if "全部" not in selected_health_filter and "All" not in selected_health_filter:
        # 映射筛选选项到健康等级
        health_level_map = {
            "积压": "积压",
            "缺货预警": "缺货预警",
            "正常": "正常",
            "Overstock": "积压",
            "Stockout": "缺货预警",
            "Normal": "正常"
        }
        filter_levels = [health_level_map.get(f, f) for f in selected_health_filter]
        df = df[df["health_level"].isin(filter_levels)]
    
    # ========== 库存关键指标 ==========
    st.markdown("### 📈 库存关键指标" if curr_lang == "ZH" else "### 📈 Key Inventory Metrics")
    
    # 筛选控件
    col_filter1, col_filter2 = st.columns(2)
    
    with col_filter1:
        level_filter = st.multiselect(
            "健康等级筛选" if curr_lang == "ZH" else "Health Level Filter",
            options=df["health_level"].unique().tolist(),
            default=df["health_level"].unique().tolist()
        )
    
    with col_filter2:
        has_inventory = st.checkbox(
            "仅显示有库存" if curr_lang == "ZH" else "Only show with inventory",
            value=False
        )
    
    # 应用筛选
    filtered_df = df[df["health_level"].isin(level_filter)]
    if has_inventory:
        filtered_df = filtered_df[filtered_df["inventory_qty"] > 0]
    
    # 应用搜索过滤
    if search_keyword:
        search_lower = search_keyword.lower()
        filtered_df = filtered_df[
            filtered_df["_part_no"].astype(str).str.lower().str.contains(search_lower, na=False) |
            filtered_df["part_name"].astype(str).str.lower().str.contains(search_lower, na=False)
        ]
    
    # ========== 安全库存 vs 当前库存 ==========
    st.markdown("#### 🔒 安全库存 vs 当前库存" if curr_lang == "ZH" else "#### 🔒 Safety Stock vs Current Inventory")
    
    # 散点图
    scatter_df = filtered_df.copy()
    scatter_df["库存状态"] = scatter_df.apply(
        lambda x: "库存充足" if x["inventory_qty"] >= x["safety_stock"] 
                 else ("库存偏低" if x["inventory_qty"] > 0 else "无库存"),
        axis=1
    )
    
    # 过滤掉无安全库存的数据用于散点图
    scatter_plot_df = scatter_df[scatter_df["safety_stock"] > 0].head(2000)
    
    if not scatter_plot_df.empty:
        fig_scatter = px.scatter(
            scatter_plot_df,
            x="safety_stock",
            y="inventory_qty",
            color="health_level",
            color_discrete_map=level_colors,
            hover_data=["_part_no", "daily_demand", "rop"],
            title="安全库存 vs 当前库存" if curr_lang == "ZH" else "Safety Stock vs Current Inventory",
            labels={
                "safety_stock": "安全库存" if curr_lang == "ZH" else "Safety Stock",
                "inventory_qty": "当前库存" if curr_lang == "ZH" else "Current Inventory"
            }
        )
        
        # 添加对角线参考
        max_val = max(scatter_plot_df["safety_stock"].max(), scatter_plot_df["inventory_qty"].max())
        fig_scatter.add_shape(
            type="line",
            x0=0, y0=0, x1=max_val, y1=max_val,
            line=dict(color="gray", dash="dash")
        )
        
        st.plotly_chart(fig_scatter, use_container_width=True)
    
    st.markdown("---")
    
    # ========== 需要关注的物料 ==========
    st.markdown("### ⚠️ 需要关注的物料" if curr_lang == "ZH" else "### ⚠️ Parts Need Attention")
    
    # 需要补货的物料（使用新的缺货预警分类）
    need_reorder_df = filtered_df[filtered_df["health_level"] == "缺货预警"].head(50)
    
    if not need_reorder_df.empty:
        st.markdown("#### 🚨 缺货预警物料" if curr_lang == "ZH" else "#### 🚨 Stockout Alert Parts")
        
        reorder_cols = ["_part_no", "part_name", "inventory_qty", "safety_stock", "stockout_qty", "sla"]
        reorder_cols = [c for c in reorder_cols if c in need_reorder_df.columns]
        
        display_reorder = need_reorder_df[reorder_cols].copy()
        display_reorder = display_reorder.rename(columns={
            "_part_no": "物料号" if curr_lang == "ZH" else "Part No",
            "part_name": "物料名称" if curr_lang == "ZH" else "Part Name",
            "inventory_qty": "当前库存" if curr_lang == "ZH" else "Inventory",
            "safety_stock": "安全库存" if curr_lang == "ZH" else "Safety Stock",
            "stockout_qty": "缺货数量" if curr_lang == "ZH" else "Stockout Qty",
            "sla": "服务系数" if curr_lang == "ZH" else "SLA"
        })
        
        st.dataframe(display_reorder, use_container_width=True, height=300)
    
    # 积压物料（使用新的积压分类）
    overstock_df = filtered_df[filtered_df["health_level"] == "积压"].head(50)
    
    if not overstock_df.empty:
        st.markdown("#### 📦 积压物料清单" if curr_lang == "ZH" else "#### 📦 Overstock Parts List")
        
        over_cols = ["_part_no", "part_name", "inventory_qty", "days_of_supply", "overstock_qty", "sla"]
        over_cols = [c for c in over_cols if c in overstock_df.columns]
        
        display_over = overstock_df[over_cols].copy()
        display_over = display_over.rename(columns={
            "_part_no": "物料号" if curr_lang == "ZH" else "Part No",
            "part_name": "物料名称" if curr_lang == "ZH" else "Part Name",
            "inventory_qty": "当前库存" if curr_lang == "ZH" else "Inventory",
            "days_of_supply": "周转天数" if curr_lang == "ZH" else "Days of Supply",
            "overstock_qty": "积压数量" if curr_lang == "ZH" else "Overstock Qty",
            "sla": "服务系数" if curr_lang == "ZH" else "SLA"
        })
        
        st.dataframe(display_over, use_container_width=True, height=300)
    
    st.markdown("---")
    
    # ========== 完整物料列表 ==========
    st.markdown("### 📋 完整物料健康明细" if curr_lang == "ZH" else "### 📋 Full Parts Health Details")
    
    # 准备显示数据（包含物料名称、服务系数、积压数量、缺货数量）
    display_health_cols = [
        "_part_no",
        "part_name",
        "_unit_price",      # 价格
        "inventory_qty",   # 在库库存
        "total_in_transit", # 在途库存
        "total_inventory",  # 总库存
        "monthly_demand",  # 月需求
        "daily_demand",    # 日需求
        "final_lt",         # 交期（含海运50天）
        "lt_std",          # 交期标准差
        "safety_stock",    # 安全库存
        "rop",             # 再订货点
        "max_inventory",    # 最大库存
        "suggested_reorder_qty",  # 建议补货量
        "suggested_process_qty",  # 建议处理量
        "health_level",    # 状态
        "health_reason"     # 诊断原因
    ]
    
    display_health_cols = [c for c in display_health_cols if c in filtered_df.columns]
    display_health_df = filtered_df[display_health_cols].copy()
    
    # 重命名列
    col_rename_health = {
        "_part_no": "物料号",
        "part_name": "物料描述",
        "_unit_price": "单价",
        "inventory_qty": "在库库存",
        "total_in_transit": "在途库存",
        "total_inventory": "总库存",
        "monthly_demand": "月需求",
        "daily_demand": "日需求",
        "base_lt": "提前期平均",
        "lt_std": "提前期标准差",
        "safety_stock": "安全库存",
        "rop": "再订货点",
        "max_inventory": "最大库存",
        "suggested_reorder_qty": "建议补货量",
        "suggested_process_qty": "建议处理量",
        "health_level": "状态",
        "health_reason": "诊断原因",
        "final_lt": "交期(含海运)"
    }
    
    # 英文映射
    col_rename_health_en = {
        "_part_no": "Part No",
        "part_name": "Part Name",
        "_unit_price": "Unit Price",
        "inventory_qty": "Inventory",
        "total_in_transit": "In Transit",
        "total_inventory": "Total Stock",
        "monthly_demand": "Monthly Demand",
        "daily_demand": "Daily Demand",
        "base_lt": "Lead Time Avg",
        "lt_std": "Lead Time Std",
        "safety_stock": "Safety Stock",
        "rop": "ROP",
        "max_inventory": "Max Inventory",
        "suggested_reorder_qty": "Reorder Qty",
        "suggested_process_qty": "Process Qty",
        "health_level": "Status",
        "health_reason": "Diagnosis",
        "final_lt": "Lead Time (w/ Sea)"
    }
    
    # 根据语言选择映射
    if curr_lang == "ZH":
        col_rename = col_rename_health
    else:
        col_rename = col_rename_health_en
    
    display_health_df = display_health_df.rename(columns=col_rename)
    
    # 排序
    sort_col = "健康评分" if curr_lang == "ZH" else "Health Score"
    if sort_col in display_health_df.columns:
        display_health_df = display_health_df.sort_values(sort_col, ascending=True)
    
    # 分页
    page_size = 20
    total_pages = (len(display_health_df) + page_size - 1) // page_size
    
    if "health_page" not in st.session_state:
        st.session_state.health_page = 1
    
    page = st.number_input(
        "页码" if curr_lang == "ZH" else "Page",
        min_value=1,
        max_value=max(1, total_pages),
        value=st.session_state.health_page,
        key="health_page_input"
    )
    
    st.session_state.health_page = page
    
    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, len(display_health_df))
    
    st.dataframe(
        display_health_df.iloc[start_idx:end_idx],
        use_container_width=True,
        height=600
    )
    
    st.markdown(f"共 {len(display_health_df)} 条记录，当前第 {page}/{total_pages} 页")
    
    # 导出功能
    st.markdown("---")
    export_col1, export_col2 = st.columns(2)
    
    # CSV 导出
    csv = display_health_df.to_csv(index=False, encoding='utf-8-sig')
    export_col1.download_button(
        label="📥 导出 CSV" if curr_lang == "ZH" else "📥 Export CSV",
        data=csv,
        file_name=f"inventory_health_details_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv;charset=utf-8-sig",
        key="export_csv"
    )
    
    # Excel 导出
    try:
        import io
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            display_health_df.to_excel(writer, index=False, sheet_name='Inventory Health')
        buffer.seek(0)
        export_col2.download_button(
            label="📊 导出 Excel" if curr_lang == "ZH" else "📊 Export Excel",
            data=buffer,
            file_name=f"inventory_health_details_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="export_excel"
        )
    except Exception as e:
        # 如果 Excel 导出失败，隐藏按钮
        pass
