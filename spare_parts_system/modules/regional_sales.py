#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
区域销售分析模块
美国市场销售分布可视化

功能：
- 美国50州 + DC 销售分布地图
- 气泡大小 = 销售金额
- 颜色 = 销售金额
- 强制确认时间过滤
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from core.i18n import get_text


def render_regional_sales(orders_df: pd.DataFrame) -> None:
    """
    渲染美国区域销售分布图
    
    业务规则：
    - 仅统计美国50州 + DC 销售数据
    - 排除 International/Unknown/非美国地区
    - 排除确认时间为空的无效订单
    - 气泡大小对应销售金额 (USD)
    """
    st.markdown("---")
    
    curr_lang = st.session_state.get("lang", "ZH")
    us_title = "🗺️ US Sales Distribution" if curr_lang == "EN" else "🗺️ 美国销售分布"
    st.markdown(f"### {us_title}")
    
    # ==================== Step 1: 确认时间强制过滤 ====================
    # 排除尚未确认或无效的订单
    confirm_time_col = None
    for col in orders_df.columns:
        col_lower = col.lower()
        if any(kw.lower() in col_lower for kw in ["确认时间", "confirm", "确认"]):
            confirm_time_col = col
            break
    
    # 执行过滤
    if confirm_time_col and confirm_time_col in orders_df.columns:
        orders_df = orders_df[orders_df[confirm_time_col].notna()].copy()
    
    if orders_df.empty:
        st.info("暂无已确认的销售数据")
        return
    
    # ==================== Step 2: 识别关键列 ====================
    # 省/州列
    state_col = None
    for col in orders_df.columns:
        if "省" in col or "州" in col or "state" in col.lower() or "province" in col.lower():
            state_col = col
            break
    
    # 金额列
    amount_col = "amount"
    
    # 验证列存在
    if state_col not in orders_df.columns or amount_col not in orders_df.columns:
        st.warning("缺少必要数据列")
        return
    
    # ==================== Step 3: 州名到缩写转换 ====================
    # 美国50州 + DC 映射字典
    state_abbr_map = {
        "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
        "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
        "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
        "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
        "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
        "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
        "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
        "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
        "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
        "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
        "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
        "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
        "Wisconsin": "WI", "Wyoming": "WY", "District Of Columbia": "DC", "D.C.": "DC",
        # 缩写形式
        "AL": "AL", "AK": "AK", "AZ": "AZ", "AR": "AR", "CA": "CA", "CO": "CO",
        "CT": "CT", "DE": "DE", "FL": "FL", "GA": "GA", "HI": "HI", "ID": "ID",
        "IL": "IL", "IN": "IN", "IA": "IA", "KS": "KS", "KY": "KY", "LA": "LA",
        "ME": "ME", "MD": "MD", "MA": "MA", "MI": "MI", "MN": "MN", "MS": "MS",
        "MO": "MO", "MT": "MT", "NE": "NE", "NV": "NV", "NH": "NH", "NJ": "NJ",
        "NM": "NM", "NY": "NY", "NC": "NC", "ND": "ND", "OH": "OH", "OK": "OK",
        "OR": "OR", "PA": "PA", "RI": "RI", "SC": "SC", "SD": "SD", "TN": "TN",
        "TX": "TX", "UT": "UT", "VT": "VT", "VA": "VA", "WA": "WA", "WV": "WV",
        "WI": "WI", "WY": "WY", "DC": "DC",
    }
    
    # 执行转换
    orders_df["_state_code"] = orders_df[state_col].astype(str).str.strip().str.title()
    orders_df["_state_code"] = orders_df["_state_code"].map(state_abbr_map).fillna("Unknown")
    
    # 金额转换
    orders_df["_amount"] = pd.to_numeric(orders_df[amount_col], errors="coerce").fillna(0)
    
    # ==================== Step 4: 美国市场锁定过滤 ====================
    # 仅保留美国50州 + DC
    valid_us_states = list(state_abbr_map.values())
    
    geo_df = orders_df[
        orders_df["_state_code"].isin(valid_us_states) &
        (orders_df["_amount"] > 0)
    ].copy()
    
    if geo_df.empty:
        no_data_text = "No US sales data" if curr_lang == "EN" else "暂无美国区域销售数据"
        st.info(no_data_text)
        return
    
    # ==================== Step 5: 数据聚合 ====================
    geo_stats = geo_df.groupby("_state_code").agg({
        "_amount": "sum"
    }).reset_index()
    geo_stats.columns = ["_state_code", "total_amount"]
    geo_stats["_state_code"] = geo_stats["_state_code"].str.upper().str[:2]
    
    # ==================== Step 6: 地图可视化 ====================
    map_title = "🗺️ US State Sales (Bubble = Amount)" if curr_lang == "EN" else "🗺️ 美国各州销售分布（气泡大小 = 销售金额）"
    fig = px.scatter_geo(
        geo_stats,
        locations="_state_code",
        locationmode="USA-states",
        size="total_amount",
        color="total_amount",
        hover_name="_state_code",
        hover_data={
            "total_amount": ":$,.2f",
            "_state_code": False
        },
        color_continuous_scale="Blues",
        range_color=[0, geo_stats["total_amount"].quantile(0.90)],
        size_max=35,
        title=map_title,
    )
    
    fig.update_layout(
        geo=dict(
            scope="usa",
            projection_type="albers usa",
            showland=True,
            landcolor="rgb(248, 248, 248)",
            countrycolor="rgb(200, 200, 200)",
            showlakes=True,
            lakecolor="rgb(255, 255, 255)",
        ),
        coloraxis=dict(
            colorbar=dict(title="Sales ($)" if curr_lang == "EN" else "销售金额 ($)"),
        ),
        margin=dict(l=0, r=0, t=50, b=0),
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # ==================== Step 7: Top 10 区域表格 ====================
    top_geo = geo_stats.nlargest(10, "total_amount")[["_state_code", "total_amount"]]
    top_geo.columns = ["State" if curr_lang == "EN" else "州代码", "Sales ($)" if curr_lang == "EN" else "销售金额 ($)"]
    top_geo["Sales ($)" if curr_lang == "EN" else "销售金额 ($)"] = top_geo["Sales ($)" if curr_lang == "EN" else "销售金额 ($)"].apply(lambda x: f"${x:,.2f}")
    
    top10_text = "**Top 10 Sales Regions**" if curr_lang == "EN" else "**Top 10 销售区域**"
    st.markdown(top10_text)
    st.dataframe(top_geo, use_container_width=True, hide_index=True)
