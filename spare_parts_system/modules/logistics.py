# -*- coding: utf-8 -*-
"""
物流看板模块（Logistics Dashboard）

物流成本分析页面：
1. 核心指标：运费总额、合同明细总价、总成本
2. 趋势分析：按月运费趋势
3. 分布分析：按发运方式的运费分布
4. 成本结构：运费与合同明细总价比例

数据源：物流成本表
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from core.i18n import get_text


def load_logistics_data():
    """
    加载物流成本数据
    
    Returns:
        pd.DataFrame: 物流数据
    """
    from config import LOGISTICS_DATA_DIR, USE_OSS, read_excel_from_oss, list_oss_files
    
    data_dir = Path(LOGISTICS_DATA_DIR)
    
    # OSS模式：从OSS读取
    if USE_OSS:
        import oss2
        from config import get_oss_bucket, OSS_CONFIG
        
        bucket = get_oss_bucket()
        prefix = "data_source/logistics/"
        
        logistics_files = []
        for obj in oss2.ObjectIterator(bucket, prefix=prefix):
            if "物流成本表" in obj.key and not obj.key.endswith("/"):
                logistics_files.append(obj.key)
        
        if not logistics_files:
            return pd.DataFrame(), {"status": "warning", "message": "未找到物流成本表" if st.session_state.get("lang", "ZH") == "ZH" else "Logistics cost table not found"}
        
        # 读取OSS数据
        dfs = []
        for oss_key in logistics_files:
            try:
                df = read_excel_from_oss(oss_key)
                # 跳过前3列元数据
                if len(df.columns) > 3:
                    df = df.iloc[:, 3:].copy()
                dfs.append(df)
            except Exception as e:
                warn_msg = f"读取物流数据失败: {oss_key}" if st.session_state.get("lang", "ZH") == "ZH" else f"Failed to read logistics data: {oss_key}"
                st.warning(warn_msg)
        
        if not dfs:
            return pd.DataFrame(), {"status": "warning", "message": "无法读取物流数据" if st.session_state.get("lang", "ZH") == "ZH" else "Unable to read logistics data"}
        
        logistics_df = pd.concat(dfs, ignore_index=True)
        success_msg = f"成功读取物流数据，共 {len(logistics_df)} 条记录" if st.session_state.get("lang", "ZH") == "ZH" else f"Successfully loaded {len(logistics_df)} logistics records"
        return logistics_df, {"status": "success", "message": success_msg}
    
    # 本地模式：从本地读取
    # 查找物流成本表
    logistics_files = []
    for f in data_dir.iterdir():
        if f.is_file() and "物流成本表" in f.name and not f.name.startswith("~"):
            logistics_files.append(f)
    
    if not logistics_files:
        return pd.DataFrame(), {"status": "warning", "message": "未找到物流成本表" if st.session_state.get("lang", "ZH") == "ZH" else "Logistics cost table not found"}
    
    # 读取数据
    dfs = []
    for f in logistics_files:
        try:
            df = pd.read_excel(f)
            # 跳过前3列元数据
            if len(df.columns) > 3:
                df = df.iloc[:, 3:].copy()
            dfs.append(df)
        except Exception as e:
            warn_msg = f"读取物流数据失败: {f.name}" if st.session_state.get("lang", "ZH") == "ZH" else f"Failed to read logistics data: {f.name}"
            st.warning(warn_msg)
    
    if not dfs:
        return pd.DataFrame(), {"status": "warning", "message": "无法读取物流数据" if st.session_state.get("lang", "ZH") == "ZH" else "Unable to read logistics data"}
    
    logistics_df = pd.concat(dfs, ignore_index=True)
    
    success_msg = f"成功读取物流数据，共 {len(logistics_df)} 条记录" if st.session_state.get("lang", "ZH") == "ZH" else f"Successfully loaded {len(logistics_df)} logistics records"
    return logistics_df, {"status": "success", "message": success_msg}


def render_logistics_dashboard():
    """
    渲染物流成本分析页面
    """
    st.title(get_text("logistics.page_title"))
    st.markdown("---")
    
    # Step 1: 加载数据
    with st.spinner(get_text("logistics.loading_logistics")):
        logistics_df, logistics_info = load_logistics_data()
    
    if logistics_info["status"] != "success":
        st.warning(f"⚠️ {logistics_info['message']}")
        return
    
    if logistics_df.empty:
        st.warning(get_text("logistics.empty_data"))
        return
    
    st.info(get_text("common.data_loaded"))
    
    # Step 2: 字段识别
    # 识别关键列
    create_time_col = None
    freight_col = None
    contract_price_col = None
    shipping_method_col = None
    
    for col in logistics_df.columns:
        col_str = str(col)
        if "创建时间" in col_str:
            create_time_col = col
        # 优先匹配 "运费(合同货币)"，再匹配普通 "运费"
        elif "运费(合同货币)" in col_str:
            freight_col = col
        elif "运费" in col_str and freight_col is None:
            freight_col = col
        elif "合同明细总价" in col_str or "总价(总价)" in col_str:
            contract_price_col = col
        elif "发运方式" in col_str:
            shipping_method_col = col
    
    # 修复：确保正确识别合同明细总价列
    # 优先使用 "合同明细总价(运费)"，不要用 "总价(总价)"
    if "合同明细总价(运费)" in logistics_df.columns:
        contract_price_col = "合同明细总价(运费)"
    
    # Step 3: 发运方式标准化映射（中英文统一）
    def normalize_shipping_method(method):
        """标准化发运方式，统一中英文"""
        if pd.isna(method):
            return "Unknown"
        method_str = str(method).strip().lower()
        mapping = {
            # 空运
            "air": "空运", "air freight": "空运", "air cargo": "空运",
            "空运": "空运", "航空": "空运", "air freight express": "空运",
            # 海运
            "sea": "海运", "sea freight": "海运", "ocean": "海运",
            "海运": "海运", "船运": "海运", "海运拼箱": "海运",
            # 陆运/快递
            "land": "陆运", "陆运": "陆运", "truck": "陆运",
            "express": "快递", "快递": "快递", "courier": "快递",
            # 多式联运
            "multimodal": "多式联运", "多式联运": "多式联运", "combined": "多式联运",
        }
        return mapping.get(method_str, str(method))  # 未匹配时返回原始值
    
    # 应用发运方式映射
    if shipping_method_col:
        logistics_df["_shipping_method_normalized"] = logistics_df[shipping_method_col].apply(normalize_shipping_method)
    
    if create_time_col is None:
        st.error(get_text("logistics.no_date_column"))
        return
    
    # Step 3: 数据清洗
    # 转换日期列
    logistics_df["_create_date"] = pd.to_datetime(logistics_df[create_time_col], errors="coerce").dt.normalize()
    logistics_df["_year"] = logistics_df["_create_date"].dt.year
    logistics_df["_year_month"] = logistics_df["_create_date"].dt.to_period("M")
    
    # 转换数值列
    if freight_col:
        logistics_df["_freight"] = pd.to_numeric(logistics_df[freight_col], errors="coerce").fillna(0)
    else:
        logistics_df["_freight"] = 0
    
    if contract_price_col:
        logistics_df["_contract_price"] = pd.to_numeric(logistics_df[contract_price_col], errors="coerce").fillna(0)
    else:
        logistics_df["_contract_price"] = 0
    
    # 计算总价 = 合同明细总价 + 运费
    logistics_df["_total_price"] = logistics_df["_contract_price"] + logistics_df["_freight"]
    
    # 侧边栏筛选器
    st.sidebar.markdown(f"### {get_text('logistics.logistics_filter')}")
    
    # 年份筛选
    available_years = sorted(logistics_df["_year"].dropna().unique().tolist())
    available_years = [int(y) for y in available_years if y > 2000]
    
    all_text = get_text("common.all_years")
    selected_logistics_year = st.sidebar.selectbox(
        get_text("common.select_year"),
        [all_text] + [str(y) for y in available_years],
        index=0
    )
    
    # 发运方式筛选 - 使用标准化后的发运方式
    available_methods = []
    if "_shipping_method_normalized" in logistics_df.columns:
        available_methods = sorted(logistics_df["_shipping_method_normalized"].dropna().unique().tolist())
    elif shipping_method_col:
        available_methods = sorted(logistics_df[shipping_method_col].dropna().unique().tolist())
    
    selected_methods = st.sidebar.multiselect(
        get_text("logistics.shipping_method") + " (Filter)",
        available_methods,
        default=available_methods
    )
    
    # 应用筛选
    filtered_df = logistics_df.copy()
    
    # 检查是否选择了具体年份（不是"全部"相关的选项）
    all_texts = ["全部", "All Years", "全部年份", "All"]
    is_all_years = selected_logistics_year in all_texts
    
    if not is_all_years:
        try:
            filtered_df = filtered_df[filtered_df["_year"] == int(selected_logistics_year)]
        except ValueError:
            pass  # 如果转换失败，保持不过滤
    
    # 使用标准化发运方式筛选
    if selected_methods and "_shipping_method_normalized" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["_shipping_method_normalized"].isin(selected_methods)]
    elif selected_methods and shipping_method_col:
        filtered_df = filtered_df[filtered_df[shipping_method_col].isin(selected_methods)]
        filtered_df = filtered_df[filtered_df[shipping_method_col].isin(selected_methods)]
    
    # Step 4: 计算核心指标
    total_freight = filtered_df["_freight"].sum()
    total_contract = filtered_df["_contract_price"].sum()
    total_cost = filtered_df["_total_price"].sum()
    
    # 转换为千元单位
    total_freight_k = total_freight / 1000
    total_contract_k = total_contract / 1000
    total_cost_k = total_cost / 1000
    
    # Step 5: 渲染KPI卡片 - 按年份展示
    st.markdown(f"### {get_text('logistics.kpi_title')}")
    
    # 计算各年份运费
    yearly_freight = logistics_df.groupby("_year").agg({
        "_freight": "sum"
    }).reset_index()
    
    # 获取2024和2025运费（千元）
    freight_2024 = yearly_freight[yearly_freight["_year"] == 2024]["_freight"].sum() / 1000 if 2024 in yearly_freight["_year"].values else 0
    freight_2025 = yearly_freight[yearly_freight["_year"] == 2025]["_freight"].sum() / 1000 if 2025 in yearly_freight["_year"].values else 0
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            label=get_text("logistics.freight_2024"),
            value=f"${freight_2024:,.1f} K",
        )
    
    with col2:
        st.metric(
            label=get_text("logistics.freight_2025"),
            value=f"${freight_2025:,.1f} K",
        )
    
    with col3:
        st.metric(
            label=get_text("logistics.total_cost"),
            value=f"${total_cost_k:,.1f} K",
        )
    
    st.markdown("---")
    
    # Step 6: 运费趋势图（按发运方式分色）
    st.markdown(f"### {get_text('logistics.freight_trend')}")
    
    # 确定使用的发运方式列（优先使用标准化后的）
    method_col_for_chart = "_shipping_method_normalized" if "_shipping_method_normalized" in filtered_df.columns else shipping_method_col
    
    if "_year_month" in filtered_df.columns:
        # 按年月和发运方式分组
        if method_col_for_chart:
            monthly_by_method = filtered_df.groupby(["_year_month", method_col_for_chart]).agg({
                "_freight": "sum"
            }).reset_index()
            
            monthly_by_method["_year_month"] = monthly_by_method["_year_month"].astype(str)
            monthly_by_method = monthly_by_method.sort_values("_year_month")
            
            # 趋势图 - 按发运方式分色
            fig_trend = px.area(
                monthly_by_method,
                x="_year_month",
                y="_freight",
                color=method_col_for_chart,
                title=get_text("logistics.monthly_freight"),
                labels={
                    "_year_month": get_text("sales.month"),
                    "_freight": get_text("logistics.freight"),
                    method_col_for_chart: get_text("logistics.shipping_method")
                },
            )
            fig_trend.update_layout(hovermode="x unified")
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            # 如果没有发运方式列，显示总体趋势
            monthly_stats = filtered_df.groupby("_year_month").agg({
                "_freight": "sum",
                "_contract_price": "sum"
            }).reset_index()
            
            monthly_stats["_year_month"] = monthly_stats["_year_month"].astype(str)
            monthly_stats = monthly_stats.sort_values("_year_month")
            
            # 趋势图
            fig_trend = px.area(
                monthly_stats,
                x="_year_month",
                y="_freight",
                title=get_text("logistics.monthly_freight"),
                labels={"_year_month": get_text("sales.month"), "_freight": get_text("logistics.freight")},
                color_discrete_sequence=["#3498db"]
            )
            fig_trend.update_layout(hovermode="x unified")
            st.plotly_chart(fig_trend, use_container_width=True)
    
    st.markdown("---")
    
    # Step 7: 发运方式分布
    st.markdown(f"### {get_text('logistics.shipping_method_dist')}")
    
    # 确定使用的发运方式列（优先使用标准化后的）
    method_col_for_chart = "_shipping_method_normalized" if "_shipping_method_normalized" in filtered_df.columns else shipping_method_col
    
    if method_col_for_chart and not filtered_df.empty:
        method_stats = filtered_df.groupby(method_col_for_chart).agg({
            "_freight": "sum",
            "_total_price": "sum"
        }).reset_index()
        
        method_stats = method_stats.sort_values("_freight", ascending=False)
        
        # 饼图 - 运费分布
        fig_pie = px.pie(
            method_stats,
            values="_freight",
            names=method_col_for_chart,
            title=get_text("logistics.freight_by_method"),
            hole=0.4,
        )
        st.plotly_chart(fig_pie, use_container_width=True)
    
    st.markdown("---")
    
    # Step 8: 成本结构 - 运费 vs 合同明细总价
    st.markdown(f"### {get_text('logistics.cost_structure')}")
    
    if total_cost > 0:
        freight_ratio = total_freight / total_cost * 100
        contract_ratio = total_contract / total_cost * 100
        
        # 环形图
        fig_donut = go.Figure(data=[go.Pie(
            labels=[get_text("logistics.freight"), get_text("logistics.contract_price")],
            values=[total_freight, total_contract],
            hole=0.5,
            textinfo="label+percent",
            marker=dict(colors=["#e74c3c", "#2ecc71"])
        )])
        
        fig_donut.update_layout(
            title=get_text("logistics.freight_vs_contract"),
            showlegend=True
        )
        
        st.plotly_chart(fig_donut, use_container_width=True)
    
    st.markdown("---")
    
    # Step 9: 按年份对比
    st.markdown(f"### {get_text('logistics.yearly_comparison')}")
    
    yearly_stats = logistics_df.groupby("_year").agg({
        "_freight": "sum",
        "_contract_price": "sum",
        "_total_price": "sum"
    }).reset_index()
    
    yearly_stats = yearly_stats.sort_values("_year")
    
    # 转换为K单位
    yearly_stats["_freight_k"] = yearly_stats["_freight"] / 1000
    yearly_stats["_contract_price_k"] = yearly_stats["_contract_price"] / 1000
    
    # 对比柱状图
    fig_yearly = px.bar(
        yearly_stats,
        x="_year",
        y="_freight_k",
        title=get_text("logistics.yearly_freight"),
        labels={"_year": "Year", "_freight_k": "Freight ($ K)"},
        color="_freight_k",
        color_continuous_scale="Blues",
    )
    
    st.plotly_chart(fig_yearly, use_container_width=True)
    
    st.markdown("---")
    
    # Step 10: 明细表
    with st.expander(get_text("logistics.detail_table"), expanded=False):
        display_cols = [create_time_col, shipping_method_col, freight_col, contract_price_col, "_total_price"]
        display_cols = [c for c in display_cols if c in filtered_df.columns]
        
        detail_df = filtered_df[display_cols].head(100).copy()
        
        rename_map = {
            create_time_col: get_text("logistics.create_time"),
            shipping_method_col: get_text("logistics.shipping_method"),
            freight_col: get_text("logistics.freight"),
            contract_price_col: get_text("logistics.contract_price"),
            "_total_price": get_text("logistics.total_price")
        }
        
        detail_df = detail_df.rename(columns=rename_map)
        
        # 格式化显示
        for col in detail_df.columns:
            if col in [get_text("logistics.freight"), get_text("logistics.contract_price"), get_text("logistics.total_price")]:
                detail_df[col] = detail_df[col].apply(lambda x: f"${x:,.2f}")
            elif col == get_text("logistics.create_time"):
                detail_df[col] = detail_df[col].apply(lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else "N/A")
        
        st.dataframe(detail_df, use_container_width=True, hide_index=True)


def load_logistics_with_year_filter(year: int = None):
    """
    加载物流数据并应用年份过滤
    
    Args:
        year: 可选，指定年份
    
    Returns:
        pd.DataFrame: 过滤后的物流数据
    """
    logistics_df, _ = load_logistics_data()
    
    if logistics_df.empty:
        return logistics_df
    
    # 提取年份
    for col in logistics_df.columns:
        if "创建时间" in str(col):
            logistics_df["_create_date"] = pd.to_datetime(logistics_df[col], errors="coerce")
            logistics_df["_year"] = logistics_df["_create_date"].dt.year
            
            if year:
                logistics_df = logistics_df[logistics_df["_year"] == year].copy()
            break
    
    return logistics_df


# ==================== 在途物料预警分析函数 ====================


def load_contract_details():
    """
    加载合同明细数据
    
    Returns:
        pd.DataFrame: 合同明细数据
    """
    from config import LOGISTICS_DATA_DIR
    
    data_dir = Path(LOGISTICS_DATA_DIR)
    
    # 查找合同明细表
    contract_files = []
    for f in data_dir.iterdir():
        if f.is_file() and "合同明细" in f.name and not f.name.startswith("~"):
            contract_files.append(f)
    
    if not contract_files:
        return pd.DataFrame(), {"status": "warning", "message": "未找到合同明细表"}
    
    # 读取数据
    dfs = []
    for f in contract_files:
        try:
            df = pd.read_excel(f)
            # 跳过前3列元数据
            if len(df.columns) > 3:
                df = df.iloc[:, 3:].copy()
            dfs.append(df)
        except Exception as e:
            st.warning(f"读取合同明细失败: {f.name}")
    
    if not dfs:
        return pd.DataFrame(), {"status": "warning", "message": "无法读取合同明细"}
    
    contract_df = pd.concat(dfs, ignore_index=True)
    
    return contract_df, {"status": "success", "message": f"成功读取合同明细，共 {len(contract_df)} 条记录"}


def render_in_transit_analysis():
    """
    渲染在途物料与预警分析页面
    """
    from datetime import datetime, timedelta
    
    st.title(get_text("in_transit.page_title"))
    st.markdown("---")
    
    # Step 1: 加载数据
    with st.spinner(get_text("common.loading")):
        contract_df, contract_info = load_contract_details()
    
    if contract_info["status"] != "success":
        st.warning(f"⚠️ {contract_info['message']}")
        return
    
    if contract_df.empty:
        st.warning("⚠️ Contract details data is empty")
        return
    
    st.info(get_text("common.data_loaded"))
    
    # Step 2: 字段识别
    box_col = None
    eta_col = None
    shipping_method_col = None
    destination_col = None
    total_price_col = None
    qty_col = None
    
    for col in contract_df.columns:
        col_str = str(col)
        if col_str == "箱号":
            box_col = col
        elif "预计到达日期" in col_str:
            eta_col = col
        elif "发运方式" in col_str:
            shipping_method_col = col
        elif "目的港" in col_str:
            destination_col = col
        elif col_str == "总价":
            total_price_col = col
        elif col_str == "数量":
            qty_col = col
    
    available_cols = get_text("common.available_columns")
    with st.expander(available_cols, expanded=False):
        st.write(contract_df.columns.tolist())
    
    identified_cols = "Identified columns:" if st.session_state.get("lang") == "EN" else "识别的列："
    st.write(f"{identified_cols} Box={box_col}, ETA={eta_col}, Method={shipping_method_col}, Destination={destination_col}")
    
    eta_error = "❌ ETA column not found" if st.session_state.get("lang") == "EN" else "❌ 未找到预计到达日期列"
    if eta_col is None:
        st.error(eta_error)
        return
    
    # Step 3: 数据处理
    contract_df["_eta_date"] = pd.to_datetime(contract_df[eta_col], errors="coerce").dt.normalize()
    
    today = datetime.now().date()
    today_dt = pd.Timestamp(today)
    
    contract_df["_is_in_transit"] = contract_df["_eta_date"] > today_dt
    contract_df["_is_arriving_soon"] = (contract_df["_eta_date"] >= today_dt) & (contract_df["_eta_date"] <= today_dt + timedelta(days=3))
    
    if total_price_col:
        contract_df["_total_price"] = pd.to_numeric(contract_df[total_price_col], errors="coerce").fillna(0)
    else:
        contract_df["_total_price"] = 0
    
    if qty_col:
        contract_df["_quantity"] = pd.to_numeric(contract_df[qty_col], errors="coerce").fillna(0)
    else:
        contract_df["_quantity"] = 0
    
    # 侧边栏筛选
    filter_label = "🔍 In-Transit Filter" if st.session_state.get("lang") == "EN" else "🔍 在途分析筛选"
    method_label = "Shipping Method" if st.session_state.get("lang") == "EN" else "选择发运方式"
    dest_label = "Destination" if st.session_state.get("lang") == "EN" else "选择目的港"
    
    st.sidebar.markdown(f"### {filter_label}")
    
    available_methods = []
    if shipping_method_col:
        available_methods = sorted(contract_df[shipping_method_col].dropna().unique().tolist())
    
    selected_methods = st.sidebar.multiselect(method_label, available_methods, default=available_methods)
    
    available_destinations = []
    if destination_col:
        available_destinations = sorted(contract_df[destination_col].dropna().unique().tolist())
    
    selected_destinations = st.sidebar.multiselect(dest_label, available_destinations, default=available_destinations)
    
    # 应用筛选
    filtered_df = contract_df.copy()
    
    if selected_methods and shipping_method_col:
        filtered_df = filtered_df[filtered_df[shipping_method_col].isin(selected_methods)]
    
    if selected_destinations and destination_col:
        filtered_df = filtered_df[filtered_df[destination_col].isin(selected_destinations)]
    
    in_transit_df = filtered_df[filtered_df["_is_in_transit"] == True]
    arriving_soon_df = filtered_df[filtered_df["_is_arriving_soon"] == True]
    
    # Step 4: 计算指标
    in_transit_count = len(in_transit_df)
    in_transit_price = in_transit_df["_total_price"].sum()
    in_transit_qty = in_transit_df["_quantity"].sum()
    
    if box_col and box_col in in_transit_df.columns:
        in_transit_box_count = in_transit_df[box_col].nunique()
        arriving_box_count = arriving_soon_df[box_col].nunique() if box_col in arriving_soon_df.columns else 0
    else:
        in_transit_box_count = 0
        arriving_box_count = 0
    
    arriving_soon_count = len(arriving_soon_df)
    arriving_soon_price = arriving_soon_df["_total_price"].sum()
    
    # Step 5: KPI卡片
    st.markdown("### 📊 在途物料指标")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(label="📦 在途物料总数", value=f"{in_transit_count:,}")
    with col2:
        st.metric(label="💰 在途总价", value=f"¥{in_transit_price:,.0f}")
    with col3:
        st.metric(label="📋 在途数量", value=f"{in_transit_qty:,.0f}")
    with col4:
        st.metric(label="🚢 在途箱量", value=f"{in_transit_box_count:,}")
    
    st.markdown("---")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(label="🔥 即将到岸(3天内)", value=f"{arriving_soon_count:,}")
    with col2:
        st.metric(label="💵 即将到岸总价", value=f"¥{arriving_soon_price:,.0f}")
    with col3:
        st.metric(label="📦 即将到岸箱量", value=f"{arriving_box_count:,}")
    with col4:
        if in_transit_count > 0:
            st.metric(label="📈 到岸率", value=f"{arriving_soon_count/in_transit_count*100:.1f}%")
        else:
            st.metric(label="📈 到岸率", value="N/A")
    
    st.markdown("---")
    
    # Step 6: 即将到岸明细
    st.markdown("### 🔥 即将到岸明细")
    
    if not arriving_soon_df.empty and box_col:
        display_cols = [box_col, shipping_method_col, destination_col, eta_col, "_total_price", "_quantity"]
        display_cols = [c for c in display_cols if c in arriving_soon_df.columns]
        
        detail_df = arriving_soon_df[display_cols].copy()
        
        rename_map = {box_col: "箱号", shipping_method_col: "发运方式", destination_col: "目的港", eta_col: "预计到达日期", "_total_price": "总价", "_quantity": "数量"}
        detail_df= detail_df.rename(columns=rename_map)
        
        if "预计到达日期" in detail_df.columns:
            detail_df["预计到达日期"] = detail_df["预计到达日期"].apply(lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else "N/A")
        if "总价" in detail_df.columns:
            detail_df["总价"] = detail_df["总价"].apply(lambda x: f"¥{x:,.0f}")
        
        detail_df["状态"] = "🔥 即将到港"
        
        cols = ["状态", "箱号", "发运方式", "目的港", "预计到达日期", "总价", "数量"]
        cols = [c for c in cols if c in detail_df.columns]
        detail_df = detail_df[cols]
        
        st.dataframe(detail_df, use_container_width=True, hide_index=True)
    else:
        st.info("暂无即将到岸的物料")
    
    st.markdown("---")
    
    # Step 7: 在途明细
    st.markdown("### 📋 在途订单明细")
    
    if not in_transit_df.empty:
        display_cols = [box_col, shipping_method_col, destination_col, eta_col, "_total_price", "_quantity"]
        display_cols = [c for c in display_cols if c in in_transit_df.columns]
        
        detail_df = in_transit_df[display_cols].copy()
        
        rename_map = {box_col: "箱号", shipping_method_col: "发运方式", destination_col: "目的港", eta_col: "预计到达日期", "_total_price": "总价", "_quantity": "数量"}
        detail_df = detail_df.rename(columns=rename_map)
        
        if "预计到达日期" in detail_df.columns:
            detail_df["预计到达日期"] = detail_df["预计到达日期"].apply(lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else "N/A")
        if "总价" in detail_df.columns:
            detail_df["总价"] = detail_df["总价"].apply(lambda x: f"¥{x:,.0f}")
        
        cols = ["箱号", "发运方式", "目的港", "预计到达日期", "总价", "数量"]
        cols = [c for c in cols if c in detail_df.columns]
        detail_df = detail_df[cols]
        
        st.dataframe(detail_df, use_container_width=True, hide_index=True)
        st.caption(f"共 {len(detail_df)} 条在途记录")
    else:
        st.info("暂无在途物料")


# ==================== 待发木箱统计函数 ====================


def load_pending_boxes():
    """
    加载箱号未创建合同数据
    
    Returns:
        pd.DataFrame: 箱号未创建合同数据
    """
    from config import LOGISTICS_DATA_DIR
    
    data_dir = Path(LOGISTICS_DATA_DIR)
    
    # 查找箱号未创建合同表
    box_files = []
    for f in data_dir.iterdir():
        if f.is_file() and "箱号未创建合同" in f.name and not f.name.startswith("~"):
            box_files.append(f)
    
    if not box_files:
        return pd.DataFrame(), {"status": "warning", "message": "未找到箱号未创建合同表"}
    
    # 读取数据
    dfs = []
    for f in box_files:
        try:
            df = pd.read_excel(f)
            # 跳过前3列元数据
            if len(df.columns) > 3:
                df = df.iloc[:, 3:].copy()
            dfs.append(df)
        except Exception as e:
            st.warning(f"读取箱号表失败: {f.name}")
    
    if not dfs:
        return pd.DataFrame(), {"status": "warning", "message": "无法读取箱号数据"}
    
    box_df = pd.concat(dfs, ignore_index=True)
    
    return box_df, {"status": "success", "message": f"成功读取箱号数据，共 {len(box_df)} 条记录"}


def render_pending_boxes():
    """
    渲染待发木箱统计页面
    """
    import math
    
    st.title(get_text("pending_box.page_title"))
    st.markdown("---")
    
    # Step 1: 加载数据
    with st.spinner(get_text("common.loading")):
        box_df, box_info = load_pending_boxes()
    
    if box_info["status"] != "success":
        st.warning(f"⚠️ {box_info['message']}")
        return
    
    if box_df.empty:
        st.warning("⚠️ Box data is empty")
        return
    
    st.info(get_text("common.data_loaded"))
    
    # Step 2: 字段识别
    length_col = None
    width_col = None
    height_col = None
    net_weight_col = None
    price_col = None
    oem_col = None
    shipping_method_col = None
    
    for col in box_df.columns:
        col_str = str(col)
        if col_str == "长":
            length_col = col
        elif col_str == "宽":
            width_col = col
        elif col_str == "高":
            height_col = col
        elif col_str == "净重":
            net_weight_col = col
        elif col_str == "采购总价":
            price_col = col
        elif col_str == "主机厂":
            oem_col = col
        elif col_str == "发运方式":
            shipping_method_col = col
    
    with st.expander("📋 可用列列表", expanded=False):
        st.write(box_df.columns.tolist())
    
    st.write(f"识别的列：长={length_col}, 宽={width_col}, 高={height_col}, 净重={net_weight_col}, 采购总价={price_col}, 主机厂={oem_col}, 发运方式={shipping_method_col}")
    
    # Step 3: 数据清洗 - 转换数值类型
    if length_col:
        box_df["_length"] = pd.to_numeric(box_df[length_col], errors="coerce").fillna(0)
    else:
        box_df["_length"] = 0
    
    if width_col:
        box_df["_width"] = pd.to_numeric(box_df[width_col], errors="coerce").fillna(0)
    else:
        box_df["_width"] = 0
    
    if height_col:
        box_df["_height"] = pd.to_numeric(box_df[height_col], errors="coerce").fillna(0)
    else:
        box_df["_height"] = 0
    
    if net_weight_col:
        box_df["_net_weight"] = pd.to_numeric(box_df[net_weight_col], errors="coerce").fillna(0)
    else:
        box_df["_net_weight"] = 0
    
    if price_col:
        box_df["_price"] = pd.to_numeric(box_df[price_col], errors="coerce").fillna(0)
    else:
        box_df["_price"] = 0
    
    # 计算体积 (长 * 宽 * 高) / 1e9 转换为立方米
    box_df["_volume"] = (box_df["_length"] * box_df["_width"] * box_df["_height"]) / 1e9
    
    # 侧边栏筛选
    st.sidebar.markdown("### 🔍 木箱分析筛选")
    
    available_oems = []
    if oem_col:
        available_oems = sorted(box_df[oem_col].dropna().unique().tolist())
    
    selected_oems = st.sidebar.multiselect(
        "选择主机厂",
        available_oems,
        default=available_oems
    )
    
    # 应用筛选
    filtered_df = box_df.copy()
    
    if selected_oems and oem_col:
        filtered_df = filtered_df[filtered_df[oem_col].isin(selected_oems)]
    
    # Step 4: 计算核心指标
    total_boxes = len(filtered_df)
    total_price = filtered_df["_price"].sum()
    total_net_weight = filtered_df["_net_weight"].sum()
    total_volume = filtered_df["_volume"].sum()
    
    # 计算高柜需求 (总体积 / 65)
    container_count = math.ceil(total_volume / 65) if total_volume > 0 else 0
    
    # 格式化数值
    total_price_k = total_price / 1000  # 千元
    total_weight_k = total_net_weight / 1000  # 千kg
    
    # Step 5: KPI卡片 (第一行)
    st.markdown("### 📊 待发木箱指标")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            label="📦 总箱量",
            value=f"{total_boxes:,}",
        )
    
    with col2:
        st.metric(
            label="💰 采购总价",
            value=f"¥{total_price_k:,.1f} K",
        )
    
    with col3:
        st.metric(
            label="⚖️ 总净重",
            value=f"{total_weight_k:,.1f} K kg",
        )
    
    st.markdown("---")
    
    # 第二行KPI
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric(
            label="📐 总体积",
            value=f"{total_volume:,.2f} m³",
        )
    
    with col2:
        st.metric(
            label="🚢 高柜需求",
            value=f"{container_count:,}",
        )
    
    st.markdown("---")
    
    # Step 6: 按主机厂分布
    st.markdown("### 📊 主机厂分布")
    
    if oem_col and not filtered_df.empty:
        oem_stats = filtered_df.groupby(oem_col).agg({
            "_price": "sum",
            "_net_weight": "sum",
            "_volume": "sum"
        }).reset_index()
        
        oem_stats = oem_stats.sort_values("_price", ascending=False)
        
        # 横向柱状图
        fig_oem = px.bar(
            oem_stats,
            x="_price",
            y=oem_col,
            orientation="h",
            title="各主机厂采购总价分布",
            labels={"_price": "采购总价 (¥)", oem_col: "主机厂"},
            color="_price",
            color_continuous_scale="Blues",
        )
        
        st.plotly_chart(fig_oem, use_container_width=True)
    
    st.markdown("---")
    
    # Step 7: 按发运方式统计
    st.markdown("### 🚢 发运方式分布")
    
    if shipping_method_col and not filtered_df.empty:
        method_stats = filtered_df.groupby(shipping_method_col).agg({
            "_price": "sum",
            "_net_weight": "sum",
            "_volume": "sum"
        }).reset_index()
        
        method_stats = method_stats.sort_values("_price", ascending=False)
        
        # 表格展示
        method_display = method_stats.copy()
        method_display["_price"] = method_display["_price"].apply(lambda x: f"¥{x/1000:,.1f} K")
        method_display["_net_weight"] = method_display["_net_weight"].apply(lambda x: f"{x/1000:,.1f} K kg")
        method_display["_volume"] = method_display["_volume"].apply(lambda x: f"{x:,.2f} m³")
        
        method_display = method_display.rename(columns={
            shipping_method_col: "发运方式",
            "_price": "采购总价",
            "_net_weight": "总净重",
            "_volume": "总体积"
        })
        
        st.dataframe(method_display, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # Step 8: 明细表
    st.markdown("### 📋 木箱明细")
    
    if not filtered_df.empty:
        display_cols = [length_col, width_col, height_col, net_weight_col, price_col, oem_col, shipping_method_col]
        display_cols = [c for c in display_cols if c in filtered_df.columns]
        
        detail_df = filtered_df[display_cols].copy()
        
        rename_map = {
            length_col: "长(mm)",
            width_col: "宽(mm)",
            height_col: "高(mm)",
            net_weight_col: "净重(kg)",
            price_col: "采购总价",
            oem_col: "主机厂",
            shipping_method_col: "发运方式"
        }
        detail_df = detail_df.rename(columns=rename_map)
        
        # 格式化金额
        if "采购总价" in detail_df.columns:
            detail_df["采购总价"] = detail_df["采购总价"].apply(lambda x: f"¥{x:,.0f}")
        
        st.dataframe(detail_df, use_container_width=True, hide_index=True)
        
        st.caption(f"共 {len(detail_df)} 条记录")
    else:
        st.info("暂无木箱数据")


# ==================== 合同未发出明细函数 ====================


def render_unsent_contracts():
    """
    渲染合同未发出明细页面
    """
    st.title(get_text("unsent_contract.page_title"))
    st.markdown("---")
    
    # Step 1: 加载数据
    with st.spinner(get_text("common.loading")):
        contract_df, contract_info = load_contract_details()
    
    if contract_info["status"] != "success":
        st.warning(f"⚠️ {contract_info['message']}")
        return
    
    if contract_df.empty:
        st.warning("⚠️ Contract details data is empty")
        return
    
    st.info(get_text("common.data_loaded"))
    
    # Step 2: 字段识别
    contract_no_col = None
    shipment_app_col = None  # 进出口备件发车申请单号
    demand_no_col = None
    part_no_col = None
    part_desc_col = None
    qty_col = None
    total_price_col = None
    create_time_col = None
    
    for col in contract_df.columns:
        col_str = str(col)
        if "合同编号" in col_str:
            contract_no_col = col
        elif "发车申请单号" in col_str:
            shipment_app_col = col
        elif col_str == "需求单号":
            demand_no_col = col
        elif col_str == "物料号":
            part_no_col = col
        elif "物料描述" in col_str and "物料号" in col_str:
            part_desc_col = col
        elif col_str == "数量":
            qty_col = col
        elif col_str == "总价":
            total_price_col = col
        elif col_str == "创建时间":
            create_time_col = col
    
    with st.expander("📋 可用列列表", expanded=False):
        st.write(contract_df.columns.tolist())
    
    st.write(f"识别的列：合同编号={contract_no_col}, 发车申请={shipment_app_col}")
    
    if contract_no_col is None or shipment_app_col is None:
        st.error("❌ 未找到关键列")
        return
    
    # Step 3: 筛选未发出记录
    # 合同编号不为空 且 发车申请单号为空
    contract_df["_contract_no"] = contract_df[contract_no_col].astype(str).str.strip()
    contract_df["_shipment_app"] = contract_df[shipment_app_col].fillna('').astype(str).str.strip()
    
    # 筛选条件：合同编号不为空 且 发车申请单号为空
    unsent_df = contract_df[
        (contract_df["_contract_no"] != '') & 
        (contract_df["_contract_no"] != 'nan') &
        (contract_df["_shipment_app"] == '') |
        (contract_df["_shipment_app"] == 'nan')
    ].copy()
    
    # 简化筛选逻辑
    unsent_df = contract_df[
        (contract_df["_contract_no"].notna()) & 
        (contract_df["_contract_no"] != '') &
        (
            (contract_df[shipment_app_col].isna()) |
            (contract_df[shipment_app_col].fillna('').astype(str).str.strip() == '')
        )
    ].copy()
    
    # 添加标记列
    unsent_df["合同已创建未发出"] = "是"
    
    # Step 4: 转换数值列
    if total_price_col:
        unsent_df["_total_price"] = pd.to_numeric(unsent_df[total_price_col], errors="coerce").fillna(0)
    else:
        unsent_df["_total_price"] = 0
    
    if qty_col:
        unsent_df["_quantity"] = pd.to_numeric(unsent_df[qty_col], errors="coerce").fillna(0)
    else:
        unsent_df["_quantity"] = 0
    
    # 转换日期列
    if create_time_col:
        unsent_df["_create_date"] = pd.to_datetime(unsent_df[create_time_col], errors="coerce")
    
    # Step 5: 计算KPI
    total_count = len(unsent_df)
    total_price = unsent_df["_total_price"].sum()
    total_qty = unsent_df["_quantity"].sum()
    
    # 格式化数值（千单位）
    total_price_k = total_price / 1000
    total_qty_k = total_qty / 1000
    
    # Step 6: KPI卡片
    st.markdown("### 📊 未发出合同指标")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(
            label="📋 未发物料数",
            value=f"{total_count:,}",
        )
    
    with col2:
        st.metric(
            label="💰 未发总价",
            value=f"¥{total_price_k:,.1f} K",
        )
    
    with col3:
        st.metric(
            label="📦 未发数量",
            value=f"{total_qty_k:,.1f} K",
        )
    
    with col4:
        # 按需求单号去重统计
        if demand_no_col:
            unique_orders = unsent_df[demand_no_col].nunique()
        else:
            unique_orders = 0
        st.metric(
            label="📄 未发订单数",
            value=f"{unique_orders:,}",
        )
    
    with col5:
        # 按合同编号去重
        unique_contracts = unsent_df["_contract_no"].nunique()
        st.metric(
            label="📃 未发合同数",
            value=f"{unique_contracts:,}",
        )
    
    st.markdown("---")
    
    # Step 7: 搜索功能
    st.markdown("### 🔍 查询筛选")
    
    # 物料号搜索
    available_parts = []
    if part_no_col:
        available_parts = sorted(unsent_df[part_no_col].dropna().unique().tolist())
    
    selected_part = st.selectbox(
        "按物料号筛选",
        ["全部"] + available_parts,
        index=0
    )
    
    # 应用筛选
    filtered_df = unsent_df.copy()
    
    if selected_part != "全部" and part_no_col:
        filtered_df = filtered_df[filtered_df[part_no_col] == selected_part]
    
    # Step 8: 明细表格
    st.markdown("### 📋 未发出明细表")
    
    if not filtered_df.empty:
        # 准备显示列
        display_cols = [demand_no_col, part_no_col, part_desc_col, "_quantity", "_total_price", "_create_date", "合同已创建未发出"]
        display_cols = [c for c in display_cols if c in filtered_df.columns]
        
        detail_df = filtered_df[display_cols].copy()
        
        # 重命名列
        rename_map = {
            demand_no_col: "需求单号",
            part_no_col: "物料号",
            part_desc_col: "物料描述",
            "_quantity": "数量",
            "_total_price": "总价",
            "_create_date": "创建时间",
            "合同已创建未发出": "合同已创建未发出"
        }
        detail_df = detail_df.rename(columns=rename_map)
        
        # 格式化日期
        if "创建时间" in detail_df.columns:
            detail_df["创建时间"] = detail_df["创建时间"].apply(
                lambda x: x.strftime("%Y-%m-%d %H:%M") if pd.notna(x) else "N/A"
            )
        
        # 格式化金额
        if "总价" in detail_df.columns:
            detail_df["总价"] = detail_df["总价"].apply(lambda x: f"¥{x:,.0f}")
        
        # 格式化数量
        if "数量" in detail_df.columns:
            detail_df["数量"] = detail_df["数量"].apply(lambda x: f"{x:,.0f}")
        
        # 按创建时间倒序排列
        if "创建时间" in detail_df.columns:
            detail_df = detail_df.sort_values("创建时间", ascending=False)
        
        # 调整列顺序
        cols = ["合同已创建未发出", "需求单号", "物料号", "物料描述", "数量", "总价", "创建时间"]
        cols = [c for c in cols if c in detail_df.columns]
        detail_df = detail_df[cols]
        
        st.dataframe(detail_df, use_container_width=True, hide_index=True)
        
        st.caption(f"共 {len(detail_df)} 条记录")
    else:
        st.info("暂无未发出的合同明细")
    
    st.markdown("---")
    
    # Step 9: 按供应商统计
    st.markdown("### 📊 未发物料分布")
    
    if part_no_col:
        part_stats = unsent_df.groupby(part_no_col).agg({
            "_total_price": "sum",
            "_quantity": "sum"
        }).reset_index()
        
        part_stats = part_stats.sort_values("_total_price", ascending=False).head(20)
        
        fig_part = px.bar(
            part_stats,
            x=part_no_col,
            y="_total_price",
            title="未发物料金额 Top 20",
            labels={part_no_col: "物料号", "_total_price": "总价 (¥)"},
            color="_total_price",
            color_continuous_scale="Reds",
        )
        
        st.plotly_chart(fig_part, use_container_width=True)
