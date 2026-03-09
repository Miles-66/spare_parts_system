# -*- coding: utf-8 -*-
"""
采购看板模块（Procurement Dashboard）

采购全景概览页面：
1. 核心指标：总采购额、订单总数、平均采购单价
2. 趋势分析：按月采购总额趋势
3. 分布分析：各主机厂采购金额贡献
4. 物料排名：按物料采购金额排名

数据源：miles采购表
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from core.data_engine import load_procurement_data_with_cache
from core.i18n import get_text, get_text_safe
from config import find_column_by_alias


def render_procurement_dashboard() -> None:
    """
    渲染采购看板页面

    功能：
    - 响应侧边栏年份过滤器
    - 显示核心指标卡片
    - 展示采购趋势图
    - 展示主机厂分布图
    - 展示物料排名表
    """
    st.title(get_text("procurement.page_title"))
    st.markdown("---")

    # Step 1: 加载采购数据
    with st.spinner(get_text("procurement.loading_procurement")):
        procurement_df, procurement_info = load_procurement_data_with_cache()

    # 检查数据加载状态
    if procurement_info["status"] != "success":
        st.warning(f"⚠️ {procurement_info['message']}")
        return

    if procurement_df.empty:
        st.warning(get_text("procurement.empty_data"))
        return

    # 显示数据源信息
    with st.expander(get_text("common.data_source"), expanded=False):
        st.write(procurement_info["message"])

    # Step 2: 获取侧边栏年份筛选器（响应全局过滤器）
    selected_year = st.session_state.get("selected_year", None)

    # 显示当前筛选条件
    if selected_year:
        st.info(get_text_safe("sales.filter_selected_year", year=selected_year))
    else:
        st.info(get_text("procurement.filter_all_years"))

    # ==================== Step 3: 建立统一映射层（兼容中英文） ====================
    st.markdown("---")
    st.markdown(f"### {get_text('procurement.data_preprocessing')}")

    # 【架构师指令】使用别名映射层识别列名
    # 无论原始数据是中文还是英文，都能正确识别

    # 显示可用列
    with st.expander(get_text("common.available_columns"), expanded=False):
        st.write(procurement_df.columns.tolist())

    # 通过别名映射识别关键列
    qty_col = find_column_by_alias(procurement_df.columns.tolist(), "quantity")
    price_col = find_column_by_alias(procurement_df.columns.tolist(), "unit_price")
    oem_col = find_column_by_alias(procurement_df.columns.tolist(), "oem")
    submit_time_col = find_column_by_alias(procurement_df.columns.tolist(), "submit_time")
    demand_no_col = find_column_by_alias(procurement_df.columns.tolist(), "demand_no")
    part_no_col = find_column_by_alias(procurement_df.columns.tolist(), "part_no")
    part_desc_col = find_column_by_alias(procurement_df.columns.tolist(), "part_desc")

    # ==================== Step 4: 金额单位统一为万元 ====================
    # 容错处理：验证关键列存在
    if price_col is None:
        st.error("❌ 错误：未找到单价列（支持: PMS价格, unit_price, 单价, price）")
        return

    if qty_col is None:
        st.error("❌ 错误：未找到数量列（支持: quantity, 数量, qty）")
        return

    # 【关键修复】将识别到的列重命名为标准列名
    # 后续代码统一使用英文标准列名
    rename_dict = {}
    if qty_col and qty_col != "quantity":
        rename_dict[qty_col] = "quantity"
    if price_col and price_col != "unit_price":
        rename_dict[price_col] = "unit_price"
    if oem_col and oem_col != "oem":
        rename_dict[oem_col] = "oem"
    if submit_time_col and submit_time_col != "submit_time":
        rename_dict[submit_time_col] = "submit_time"
    if demand_no_col and demand_no_col != "demand_no":
        rename_dict[demand_no_col] = "demand_no"
    if part_no_col and part_no_col != "part_no":
        rename_dict[part_no_col] = "part_no"
    if part_desc_col and part_desc_col != "part_desc":
        rename_dict[part_desc_col] = "part_desc"

    if rename_dict:
        procurement_df = procurement_df.rename(columns=rename_dict)

        # 【关键修复】更新列变量引用，指向重命名后的列
        # 因为 rename_dict 中的 key 是旧名称，value 是新名称
        price_col = rename_dict.get(price_col, price_col)
        qty_col = rename_dict.get(qty_col, qty_col)
        oem_col = rename_dict.get(oem_col, oem_col)
        submit_time_col = rename_dict.get(submit_time_col, submit_time_col)
        demand_no_col = rename_dict.get(demand_no_col, demand_no_col)
        part_no_col = rename_dict.get(part_no_col, part_no_col)
        part_desc_col = rename_dict.get(part_desc_col, part_desc_col)

    # 【核心逻辑】内存计算总价（对齐 Power BI）
    # 公式：Total Amount = PMS价格 × quantity
    procurement_df["_qty_numeric"] = pd.to_numeric(procurement_df["quantity"], errors="coerce").fillna(0)
    procurement_df["_price_numeric"] = pd.to_numeric(procurement_df["unit_price"], errors="coerce").fillna(0)
    procurement_df["_total_price"] = procurement_df["_qty_numeric"] * procurement_df["_price_numeric"]

    # Step 4: 提取年月列
    if submit_time_col:
        procurement_df["_year_month"] = pd.to_datetime(
            procurement_df[submit_time_col], errors="coerce"
        ).dt.to_period("M")
        
        procurement_df["_year"] = pd.to_datetime(
            procurement_df[submit_time_col], errors="coerce"
        ).dt.year
        
        if selected_year:
            procurement_df = procurement_df[procurement_df["_year"] == selected_year].copy()

    # 过滤有效数据（总价 > 0）
    valid_df = procurement_df[procurement_df["_total_price"] > 0].copy()

    if valid_df.empty:
        st.warning("⚠️ 筛选后无有效采购数据")
        return

    # Step 5: 计算核心指标
    total_amount = valid_df["_total_price"].sum()
    total_orders = len(valid_df)
    avg_price = valid_df["_total_price"].mean() if len(valid_df) > 0 else 0

    # 转换为百万单位
    total_amount_m = total_amount / 1_000_000
    avg_price_m = avg_price / 1_000_000

    # Step 6: 渲染KPI指标卡
    st.markdown(f"### {get_text('procurement.kpi_title')}")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            label=get_text("procurement.total_procurement"),
            value=f"¥{total_amount_m:,.2f} M",
            delta=None,
        )

    with col2:
        st.metric(
            label=get_text("procurement.order_count"),
            value=f"{total_orders:,}",
            delta=None,
        )

    with col3:
        st.metric(
            label=get_text("procurement.avg_unit_price"),
            value=f"¥{avg_price_m:,.2f} K",
            delta=None,
        )

    st.markdown("---")

    # Step 6: 计算分组指标
    # 按主机厂分组
    if "oem" in valid_df.columns:
        # 获取翻译
        oem_label = "OEM" if st.session_state.get("lang") == "EN" else "主机厂"
        amount_label = "Amount" if st.session_state.get("lang") == "EN" else "采购金额"
        count_label = "Orders" if st.session_state.get("lang") == "EN" else "订单数"
        
        # 【防御性修复】检查 demand_no 是否存在
        if "demand_no" in valid_df.columns:
            oem_stats = valid_df.groupby("oem").agg({
                "_total_price": "sum",
                "demand_no": "count"
            }).reset_index()
            oem_stats.columns = [oem_label, amount_label, count_label]
        else:
            # fallback: 使用行索引作为订单计数
            oem_stats = valid_df.groupby("oem").agg({
                "_total_price": "sum"
            }).reset_index()
            oem_stats.columns = [oem_label, amount_label]
            oem_stats[count_label] = 0  # 无法统计订单数
        
        oem_stats = oem_stats.sort_values(amount_label, ascending=False)
        oem_stats[amount_label] = oem_stats[amount_label] / 1_000_000  # 转换为百万

    # 按年月分组
    if "_year_month" in valid_df.columns:
        ym_label = "Year-Month" if st.session_state.get("lang") == "EN" else "年月"
        amount_label = "Amount" if st.session_state.get("lang") == "EN" else "采购金额"
        
        monthly_stats = valid_df.groupby("_year_month").agg({
            "_total_price": "sum"
        }).reset_index()
        monthly_stats.columns = [ym_label, amount_label]
        monthly_stats[amount_label] = monthly_stats[amount_label] / 1_000_000  # 转换为百万
        monthly_stats[ym_label] = monthly_stats[ym_label].astype(str)
        monthly_stats = monthly_stats.sort_values(ym_label)

    # Step 7: 渲染趋势图
    st.markdown(f"### {get_text('procurement.monthly_procurement')}")

    if "_year_month" in valid_df.columns and not monthly_stats.empty:
        # 获取当前语言的标签
        ym_label = "Year-Month" if st.session_state.get("lang") == "EN" else "月份"
        amount_label = "Amount (¥ M)" if st.session_state.get("lang") == "EN" else "采购金额 (¥ M)"
        trend_title = "Monthly Procurement (M ¥)" if st.session_state.get("lang") == "EN" else "月度采购总额趋势（单位：百万元）"
        
        # 获取实际列名
        actual_ym_col = monthly_stats.columns[0]
        actual_amount_col = monthly_stats.columns[1]
        
        # 趋势图
        fig_trend = px.bar(
            monthly_stats,
            x=actual_ym_col,
            y=actual_amount_col,
            title=trend_title,
            labels={actual_ym_col: ym_label, actual_amount_col: amount_label},
            color=actual_amount_col,
            color_continuous_scale="Blues",
        )

        fig_trend.update_layout(
            xaxis_title=ym_label,
            yaxis_title=amount_label,
            hovermode="x unified",
        )

        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("暂无时间维度数据")

    # Step 8: 渲染主机厂分布图
    st.markdown("### 🏭 主机厂分布")

    if "oem" in valid_df.columns and not oem_stats.empty:
        # 获取当前语言的标签
        oem_label = "OEM" if st.session_state.get("lang") == "EN" else "主机厂"
        amount_label = "Amount (¥ M)" if st.session_state.get("lang") == "EN" else "采购金额 (¥ M)"
        
        # 获取实际列名
        actual_oem_col = oem_stats.columns[0]
        actual_amount_col = oem_stats.columns[1]
        
        # 柱状图
        fig_dist = px.bar(
            oem_stats.head(15),
            x=actual_oem_col,
            y=actual_amount_col,
            title="各主机厂采购金额贡献（Top 15，单位：百万元）",
            labels={actual_oem_col: oem_label, actual_amount_col: amount_label},
            color=actual_amount_col,
            color_continuous_scale="Viridis",
        )

        fig_dist.update_layout(
            xaxis_title=oem_label,
            yaxis_title=amount_label,
            hovermode="x unified",
        )

        st.plotly_chart(fig_dist, use_container_width=True)

        # 饼图（可选）
        fig_pie = px.pie(
            oem_stats,
            values=actual_amount_col,
            names=actual_oem_col,
            title="主机厂采购金额占比",
            hole=0.4,
        )

        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("暂无主机厂数据")

    st.markdown("---")

    # Step 9: 渲染物料排名表
    st.markdown("### 📦 物料采购排名")

    # 按物料分组统计
    if "part_no" in valid_df.columns:
        part_stats = valid_df.groupby("part_no").agg({
            "_total_price": "sum",
            "quantity": "sum",
            "part_desc": "first" if "part_desc" in valid_df.columns else "last"
        }).reset_index()

        part_stats.columns = ["物料号", "采购金额", "总数量", "物料描述"]

        # 转换金额单位
        part_stats["采购金额"] = part_stats["采购金额"] / 1_000_000  # 百万

        # 排序并取Top 50
        part_stats = part_stats.sort_values("采购金额", ascending=False).head(50)

        # 格式化显示
        part_stats_display = part_stats.copy()
        part_stats_display["采购金额"] = part_stats_display["采购金额"].apply(
            lambda x: f"¥{x:,.2f} M"
        )
        part_stats_display["总数量"] = part_stats_display["总数量"].apply(
            lambda x: f"{x:,.0f}"
        )

        # 重命名列
        part_stats_display = part_stats_display.rename(columns={
            "part_no": "物料号",
            "part_desc": "物料描述",
            "采购金额": "采购金额 (¥ M)",
            "总数量": "总数量"
        })

        # 调整列顺序
        cols = ["物料号", "物料描述", "采购金额 (¥ M)", "总数量"]
        cols = [c for c in cols if c in part_stats_display.columns]
        part_stats_display = part_stats_display[cols]

        st.dataframe(
            part_stats_display,
            use_container_width=True,
            hide_index=True,
        )

        st.caption(f"共 {len(part_stats)} 种物料（显示 Top 50）")

    st.markdown("---")

    # Step 10: 明细表格（可选）
    with st.expander("📋 采购明细数据（前100行）", expanded=False):
        # 显示原始列
        display_cols = [col for col in ["demand_no", "part_no", "part_desc", "oem", "quantity", "unit_price", "_total_price", "submit_time"] if col in valid_df.columns]

        detail_df = valid_df[display_cols].head(100).copy()

        # 格式化金额
        if "_total_price" in detail_df.columns:
            detail_df["_total_price"] = detail_df["_total_price"].apply(lambda x: f"¥{x:,.2f}")

        # 格式化数量
        if "quantity" in detail_df.columns:
            detail_df["quantity"] = detail_df["quantity"].apply(lambda x: f"{x:,.0f}")

        # 重命名列
        rename_map = {
            "demand_no": "需求单号",
            "part_no": "物料号",
            "part_desc": "物料描述",
            "oem": "主机厂",
            "quantity": "数量",
            "unit_price": "PMS价格",
            "_total_price": "总价",
            "submit_time": "SAP提交时间"
        }
        detail_df = detail_df.rename(columns=rename_map)

        st.dataframe(detail_df, use_container_width=True, hide_index=True)


def load_procurement_with_year_filter(year: int = None) -> pd.DataFrame:
    """
    加载采购数据并应用年份过滤

    Args:
        year: 可选，指定年份

    Returns:
        pd.DataFrame: 过滤后的采购数据
    """
    procurement_df, _ = load_procurement_data_with_cache()

    if procurement_df.empty:
        return procurement_df

    # 计算总价
    if "quantity" in procurement_df.columns and "unit_price" in procurement_df.columns:
        procurement_df["_total_price"] = (
            pd.to_numeric(procurement_df["quantity"], errors="coerce").fillna(0) *
            pd.to_numeric(procurement_df["unit_price"], errors="coerce").fillna(0)
        )

    # 提取年份
    if "submit_time" in procurement_df.columns:
        procurement_df["_year"] = pd.to_datetime(
            procurement_df["submit_time"], errors="coerce"
        ).dt.year

        # 执行年份过滤
        if year:
            procurement_df = procurement_df[procurement_df["_year"] == year].copy()

    return procurement_df


# ==================== 采购交付分析函数 ====================


def load_box_data() -> pd.DataFrame:
    """
    加载箱号明细表数据
    
    Returns:
        pd.DataFrame: 箱号明细数据
    """
    from pathlib import Path
    from config import PROCUREMENT_DATA_DIR
    
    data_dir = Path(PROCUREMENT_DATA_DIR)
    
    # 查找箱号明细表
    box_files = []
    for f in data_dir.iterdir():
        if f.is_file() and "箱号" in f.name:
            box_files.append(f)
    
    if not box_files:
        return pd.DataFrame()
    
    # 读取箱号数据
    dfs = []
    for f in box_files:
        try:
            df = pd.read_excel(f)
            if len(df.columns) > 3:
                df = df.iloc[:, 3:].copy()
            dfs.append(df)
        except Exception as e:
            st.warning(f"读取箱号文件失败: {f.name}")
    
    if not dfs:
        return pd.DataFrame()
    
    box_df = pd.concat(dfs, ignore_index=True)
    return box_df


def render_procurement_delivery_analysis() -> None:
    """
    渲染采购交付分析页面
    """
    st.title(get_text("procurement_delivery.page_title"))
    st.markdown("---")
    
    # Step 1: 加载数据
    with st.spinner(get_text("common.loading")):
        procurement_df, proc_info = load_procurement_data_with_cache()
        box_df = load_box_data()
    
    if proc_info["status"] != "success":
        st.warning(f"⚠️ {proc_info['message']}")
        return
    
    if procurement_df.empty:
        st.warning(get_text("procurement.empty_data"))
        return
    
    st.info(get_text("common.data_loaded"))
    
    # Step 2: 数据预处理 - 识别关键列
    # 采购表关键列 - 显式识别 SAP订单号
    qty_col = find_column_by_alias(procurement_df.columns.tolist(), "quantity")
    price_col = find_column_by_alias(procurement_df.columns.tolist(), "unit_price")
    submit_time_col = find_column_by_alias(procurement_df.columns.tolist(), "submit_time")
    demand_no_col = find_column_by_alias(procurement_df.columns.tolist(), "demand_no")
    # 显式检查 SAP订单号 列
    if demand_no_col is None:
        for col in procurement_df.columns:
            if "SAP订单号" in str(col):
                demand_no_col = col
                break
    part_no_col = find_column_by_alias(procurement_df.columns.tolist(), "part_no")
    oem_col = find_column_by_alias(procurement_df.columns.tolist(), "oem")
    
    # 箱号表关键列识别 - 优先识别 SAP 需求单号
    box_qty_col = None
    box_demand_no_col = None
    box_part_no_col = None
    box_create_time_col = None
    
    for col in box_df.columns:
        col_lower = col.lower()
        if "数量" in col:
            box_qty_col = col
        # 优先匹配 "SAP 需求单号"（460开头），再匹配普通"需求单号"
        elif "SAP 需求单号" in col:
            box_demand_no_col = col
        elif "需求单号" in col and box_demand_no_col is None:
            box_demand_no_col = col
        # 优先匹配 "物料号"，再匹配 "原物料号"
        elif "物料号" in col and "原" not in col:
            box_part_no_col = col
        elif "原物料号" in col and box_part_no_col is None:
            box_part_no_col = col
        elif "创建时间" in col:
            box_create_time_col = col
    
    # 标准化采购表列名 - 优先使用 SAP 订单号
    rename_dict = {}
    if qty_col and qty_col != "quantity":
        rename_dict[qty_col] = "quantity"
    if price_col and price_col != "unit_price":
        rename_dict[price_col] = "unit_price"
    if submit_time_col and submit_time_col != "submit_time":
        rename_dict[submit_time_col] = "submit_time"
    # 优先使用 SAP 订单号
    sap_order_col = None
    for col in procurement_df.columns:
        if "SAP订单号" in col:
            sap_order_col = col
            break
    if sap_order_col:
        rename_dict[sap_order_col] = "demand_no"
    elif demand_no_col and demand_no_col != "demand_no":
        rename_dict[demand_no_col] = "demand_no"
    if part_no_col and part_no_col != "part_no":
        rename_dict[part_no_col] = "part_no"
    if oem_col and oem_col != "oem":
        rename_dict[oem_col] = "oem"
    
    if rename_dict:
        procurement_df = procurement_df.rename(columns=rename_dict)
    
    # 调试：显示处理前的列名
    with st.expander("🔍 调试信息：关联键检查", expanded=True):
        st.write(f"采购表列名: {procurement_df.columns.tolist()}")
        st.write(f"箱号表列名: {box_df.columns.tolist()}")  # 显式显示箱号表所有列名
        st.write(f"识别的 demand_no 列: {demand_no_col}")
        st.write(f"识别的 part_no 列 (采购表): {part_no_col}")
        st.write(f"识别的箱号 part_no 列: {box_part_no_col}")  # 显式显示识别的物料号列
        st.write(f"识别的箱号需求单号列: {box_demand_no_col}")
        
        # 深度诊断：关联键精度探测
        st.markdown("### 1. 关联键精度探测")
        
        # 采购表 demand_no 样本
        if "demand_no" in procurement_df.columns:
            proc_sample = procurement_df["demand_no"].dropna().head(5).tolist()
            st.write(f"采购表 demand_no 样本: {proc_sample}")
            st.write(f"采购表 demand_no 类型: {procurement_df['demand_no'].dtype}")
        
        # 箱号表 sap_demand_no 样本
        if box_demand_no_col and box_demand_no_col in box_df.columns:
            box_sample = box_df[box_demand_no_col].dropna().head(5).tolist()
            st.write(f"箱号表 sap_demand_no 样本: {box_sample}")
            st.write(f"箱号表 sap_demand_no 类型: {box_df[box_demand_no_col].dtype}")
        
        # 采购表 part_no 样本
        if "part_no" in procurement_df.columns:
            proc_part_sample = procurement_df["part_no"].dropna().head(5).tolist()
            st.write(f"采购表 part_no 样本: {proc_part_sample}")
            st.write(f"采购表 part_no 类型: {procurement_df['part_no'].dtype}")
            # 计算平均长度
            proc_lens = procurement_df["part_no"].dropna().astype(str).str.len()
            st.write(f"采购表 part_no 平均长度: {proc_lens.mean():.1f}")
        
        # 箱号表 part_no 样本
        if "part_no" in box_df.columns:
            box_part_sample = box_df["part_no"].dropna().head(5).tolist()
            st.write(f"箱号表 part_no 样本: {box_part_sample}")
            st.write(f"箱号表 part_no 类型: {box_df['part_no'].dtype}")
            # 计算平均长度
            box_lens = box_df["part_no"].dropna().astype(str).str.len()
            st.write(f"箱号表 part_no 平均长度: {box_lens.mean():.1f}")
        
        # 深度诊断：尝试仅基于 demand_no 关联
        st.markdown("### 降级关联测试（仅用 demand_no）")
        if "demand_no" in procurement_df.columns and "demand_no" in box_df.columns:
            try:
                # 准备箱号汇总（只用 demand_no）
                box_agg_simple = box_df.groupby("demand_no").agg({
                    "box_qty": "sum"
                }).reset_index()
                box_agg_simple = box_agg_simple.rename(columns={"box_qty": "packed_qty_simple"})
                
                temp_merge = procurement_df.merge(box_agg_simple, on="demand_no", how="inner")
                if len(temp_merge) > 0:
                    st.write(f"降级关联成功! 匹配行数: {len(temp_merge)}")
                    st.write("样本数据（采购表 part_no vs 箱号表 part_no）:")
                    # 找一个共同的 demand_no
                    sample_demand = temp_merge["demand_no"].iloc[0]
                    st.write(f"示例订单号: {sample_demand}")
                    proc_parts = temp_merge[temp_merge["demand_no"] == sample_demand]["part_no"].unique()
                    st.write(f"采购表物料号: {proc_parts}")
                    box_parts = box_df[box_df["demand_no"] == sample_demand]["part_no"].unique()
                    st.write(f"箱号表物料号: {box_parts}")
                else:
                    st.write("降级关联也失败（demand_no 不匹配）")
            except Exception as e:
                st.write(f"降级关联测试出错: {e}")
    
    # 标准化箱号表列名 - 强制使用 SAP 需求单号
    box_rename = {}
    if box_qty_col and box_qty_col != "box_qty":
        box_rename[box_qty_col] = "box_qty"
    # 强制将 SAP 需求单号 重命名为 demand_no
    if box_demand_no_col:
        box_rename[box_demand_no_col] = "demand_no"
    if box_part_no_col and box_part_no_col != "part_no":
        box_rename[box_part_no_col] = "part_no"
    if box_create_time_col and box_create_time_col != "box_create_time":
        box_rename[box_create_time_col] = "box_create_time"
    
    if box_rename:
        box_df = box_df.rename(columns=box_rename)
    
    # Step 3: 数据关联预处理 - 三步对齐法
    # 3.1 强制转换单号为字符串，去除空格和 .0 后缀
    if "demand_no" in procurement_df.columns:
        procurement_df["demand_no"] = (
            procurement_df["demand_no"]
            .astype(str)
            .str.replace(r'\.0$', '', regex=True)
            .str.strip()
        )
    if "demand_no" in box_df.columns:
        box_df["demand_no"] = (
            box_df["demand_no"]
            .astype(str)
            .str.replace(r'\.0$', '', regex=True)
            .str.strip()
        )
    if "part_no" in box_df.columns:
        box_df["part_no"] = box_df["part_no"].astype(str).str.strip()
    if "part_no" in procurement_df.columns:
        procurement_df["part_no"] = procurement_df["part_no"].astype(str).str.strip()
    
    # 3.2 箱号表按 SAP需求单号 + 物料号 groupby 求和
    if "demand_no" in box_df.columns and "part_no" in box_df.columns and "box_qty" in box_df.columns:
        box_agg = box_df.groupby(["demand_no", "part_no"]).agg({
            "box_qty": "sum",
            "box_create_time": "max"
        }).reset_index()
        # 重命名列
        box_agg = box_agg.rename(columns={"box_qty": "packed_qty"})
    else:
        st.error(f"箱号表缺少关键列! 可用列: {box_df.columns.tolist()}")
        return
    
    # 3.3 Left Join 采购表与箱号汇总表
    merged_df = procurement_df.merge(
        box_agg,
        on=["demand_no", "part_no"],
        how="left"
    )
    
    # 确保 packed_qty 列存在
    if "packed_qty" not in merged_df.columns:
        merged_df["packed_qty"] = 0
    
    # 关联质量报告
    total_records = len(merged_df)
    matched_records = len(merged_df[merged_df["packed_qty"] > 0])
    unmatched_records = total_records - matched_records
    
    with st.expander("📊 关联质量报告", expanded=False):
        st.write(f"总采购记录数: {total_records:,}")
        st.write(f"成功关联箱号记录数: {matched_records:,}")
        st.write(f"孤立订单数 (未找到箱号): {unmatched_records:,}")
        if total_records > 0:
            st.write(f"关联率: {matched_records/total_records*100:.1f}%")
    
    # 填充缺失值为0
    merged_df["packed_qty"] = merged_df["packed_qty"].fillna(0)
    
    # Step 4: 字段计算
    # 转换数值列
    merged_df["_qty"] = pd.to_numeric(merged_df.get("quantity", 0), errors="coerce").fillna(0)
    merged_df["_price"] = pd.to_numeric(merged_df.get("unit_price", 0), errors="coerce").fillna(0)
    
    # 未交付数量 = 采购数量 - 累计装箱数量 (若 < 0 则设为 0)
    merged_df["_undelivered_qty"] = (merged_df["_qty"] - merged_df["packed_qty"]).clip(lower=0)
    
    # 未交付金额 = 未交付数量 * PMS价格
    merged_df["_undelivered_amount"] = merged_df["_undelivered_qty"] * merged_df["_price"]
    
    # 转换日期列
    if "submit_time" in merged_df.columns:
        merged_df["_submit_date"] = pd.to_datetime(merged_df["submit_time"], errors="coerce").dt.normalize()
    
    if "box_create_time" in merged_df.columns:
        merged_df["_box_date"] = pd.to_datetime(merged_df["box_create_time"], errors="coerce").dt.normalize()
    
    # 交货周期 = 箱号创建时间 - SAP提交时间
    if "_submit_date" in merged_df.columns and "_box_date" in merged_df.columns:
        merged_df["_delivery_cycle"] = (merged_df["_box_date"] - merged_df["_submit_date"]).dt.days
    else:
        merged_df["_delivery_cycle"] = None
    
    # 是否延期: 周期 > 30 则为 "是"
    merged_df["_is_delayed"] = merged_df["_delivery_cycle"].apply(
        lambda x: "是" if pd.notna(x) and x > 30 else "否"
    )
    
    # 获取年份筛选
    selected_year = st.session_state.get("selected_year", None)
    
    # 应用年份筛选
    if selected_year and "_submit_date" in merged_df.columns:
        merged_df["_year"] = merged_df["_submit_date"].dt.year
        merged_df = merged_df[merged_df["_year"] == selected_year]
    
    # 侧边栏筛选器
    st.sidebar.markdown("### 🔍 交付分析筛选")
    
    # 订单完结状态筛选
    completion_status = st.sidebar.radio(
        "订单是否完结",
        ["全部", "已完结", "未完结"],
        index=0
    )
    
    # OEM 多选筛选
    available_oems = []
    if "oem" in merged_df.columns:
        available_oems = sorted(merged_df["oem"].dropna().unique().tolist())
    
    selected_oems = st.sidebar.multiselect(
        "选择主机厂 (OEM)",
        available_oems,
        default=available_oems
    )
    
    # 应用筛选
    if completion_status == "已完结":
        merged_df = merged_df[merged_df["_undelivered_qty"] == 0]
    elif completion_status == "未完结":
        merged_df = merged_df[merged_df["_undelivered_qty"] > 0]
    
    if selected_oems and "oem" in merged_df.columns:
        merged_df = merged_df[merged_df["oem"].isin(selected_oems)]
    
    # Step 5: 计算核心指标
    total_undelivered_amount = merged_df["_undelivered_amount"].sum()
    total_undelivered_qty = merged_df["_undelivered_qty"].sum()
    avg_delivery_cycle = merged_df["_delivery_cycle"].mean()
    
    # Step 6: 渲染KPI卡片
    st.markdown("### 📊 核心指标")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            label="💰 未交付总金额",
            value=f"¥{total_undelivered_amount:,.0f}",
        )
    
    with col2:
        st.metric(
            label="📦 未交付总数量",
            value=f"{total_undelivered_qty:,.0f}",
        )
    
    with col3:
        st.metric(
            label="⏱️ 平均交货周期",
            value=f"{avg_delivery_cycle:.1f} 天" if pd.notna(avg_delivery_cycle) else "N/A",
        )
    
    st.markdown("---")
    
    # Step 7: 按主机厂展示未交付金额
    st.markdown("### 🏭 主机厂未交付金额分布")
    
    # 获取语言标签
    oem_label = "OEM" if st.session_state.get("lang") == "EN" else "主机厂"
    
    if "oem" in merged_df.columns:
        oem_undelivered = merged_df.groupby("oem").agg({
            "_undelivered_amount": "sum",
            "_undelivered_qty": "sum",
        }).reset_index()
        oem_undelivered = oem_undelivered.sort_values("_undelivered_amount", ascending=False)
        
        fig_oem = px.bar(
            oem_undelivered.head(15),
            x="oem",
            y="_undelivered_amount",
            title="各主机厂未交付金额（单位：元）",
            labels={"oem": oem_label, "_undelivered_amount": "未交付金额"},
            color="_undelivered_amount",
            color_continuous_scale="Reds",
        )
        st.plotly_chart(fig_oem, use_container_width=True)
    
    st.markdown("---")
    
    # Step 8: 交付率与延期率排名
    st.markdown("### 📈 交付率与延期率排名")
    
    # 获取语言标签
    oem_label = "OEM" if st.session_state.get("lang") == "EN" else "主机厂"
    
    if "oem" in merged_df.columns and "_is_delayed" in merged_df.columns:
        # 计算每个OEM的交付率和延期率
        oem_stats = merged_df.groupby("oem").agg({
            "_undelivered_qty": "sum",
            "_qty": "sum",
            "_is_delayed": lambda x: (x == "是").sum(),
        }).reset_index()
        
        # 计算交付率 = (总数量 - 未交付数量) / 总数量
        oem_stats["_fulfill_rate"] = (oem_stats["_qty"] - oem_stats["_undelivered_qty"]) / oem_stats["_qty"].replace(0, 1) * 100
        # 延期率 = 延期订单数 / 总订单数
        oem_stats["_delay_rate"] = oem_stats["_is_delayed"] / oem_stats["_qty"].replace(0, 1) * 100
        
        oem_stats = oem_stats.sort_values("_fulfill_rate", ascending=False)
        
        fig_rate = px.bar(
            oem_stats.head(15),
            x="oem",
            y="_fulfill_rate",
            title="各主机厂交付率排名",
            labels={"oem": oem_label, "_fulfill_rate": "交付率 (%)"},
            color="_fulfill_rate",
            color_continuous_scale="Greens",
        )
        st.plotly_chart(fig_rate, use_container_width=True)
    
    st.markdown("---")
    
    # Step 9: 延期率趋势
    st.markdown("### 📉 延期率趋势")
    
    # 获取语言标签
    month_label = "Month" if st.session_state.get("lang") == "EN" else "月份"
    
    if "_submit_date" in merged_df.columns and "_is_delayed" in merged_df.columns:
        merged_df["_year_month"] = merged_df["_submit_date"].dt.to_period("M")
        
        monthly_stats = merged_df.groupby("_year_month").agg({
            "_is_delayed": lambda x: (x == "是").sum(),
            "demand_no": "count",
        }).reset_index()
        
        monthly_stats.columns = ["年月", "延期数", "总数"]
        monthly_stats["延期率"] = monthly_stats["延期数"] / monthly_stats["总数"] * 100
        monthly_stats["年月"] = monthly_stats["年月"].astype(str)
        
        # 获取实际列名
        actual_ym_col = "年月"
        actual_delay_col = "延期率"
        
        fig_trend = px.line(
            monthly_stats,
            x=actual_ym_col,
            y=actual_delay_col,
            title="延期率月度趋势",
            labels={actual_ym_col: month_label, actual_delay_col: "延期率 (%)"},
            markers=True,
        )
        st.plotly_chart(fig_trend, use_container_width=True)
    
    st.markdown("---")
    
    # Step 10: 明细表
    with st.expander("📋 交付明细数据（前100行）", expanded=False):
        display_cols = ["demand_no", "part_no", "oem", "quantity", "packed_qty", 
                       "_undelivered_qty", "unit_price", "_undelivered_amount", 
                       "_delivery_cycle", "_is_delayed"]
        display_cols = [c for c in display_cols if c in merged_df.columns]
        
        detail_df = merged_df[display_cols].head(100).copy()
        detail_df = detail_df.rename(columns={
            "demand_no": "需求单号",
            "part_no": "物料号",
            "oem": "主机厂",
            "quantity": "采购数量",
            "packed_qty": "已装箱数量",
            "_undelivered_qty": "未交付数量",
            "unit_price": "单价",
            "_undelivered_amount": "未交付金额",
            "_delivery_cycle": "交货周期(天)",
            "_is_delayed": "是否延期",
        })
        st.dataframe(detail_df, use_container_width=True, hide_index=True)
