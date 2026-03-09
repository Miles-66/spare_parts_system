# -*- coding: utf-8 -*-
"""
子公司备件管理系统 - 主入口

负责侧边栏导航和模块调度。
"""

import streamlit as st
from pathlib import Path
import pandas as pd

# 设置页面配置
PAGE_TITLES = {
    "ZH": "徐工北美备件管理系统",
    "EN": "XCMG North America Parts Management System"
}

st.set_page_config(
    page_title=PAGE_TITLES["ZH"],
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 添加项目根目录到路径
import sys
sys.path.insert(0, str(Path(__file__).parent))

# 导入模块
from modules.sales import render_sales_dashboard, render_backorder_analysis, render_pending_shipment, render_backorder_chain_tracking
from modules.procurement import render_procurement_dashboard, render_procurement_delivery_analysis
from modules.logistics import render_logistics_dashboard, render_in_transit_analysis, render_unsent_contracts, render_pending_boxes
from modules.forecasting import render_forecasting
from modules.inventory import render_inventory_dashboard


# ==================== 菜单配置（翻译映射表） ====================
# 逻辑ID -> 中英文映射
MENU_CONFIG = {
    # 销售板块
    "sales_db": {"ZH": "销售看板", "EN": "Sales Dashboard"},
    "pending_shipment": {"ZH": "待发货清单", "EN": "Pending Shipping"},
    "backorder_analysis": {"ZH": "缺货分析", "EN": "Backorder Analysis"},
    "backorder_tracker": {"ZH": "缺货全链路追踪", "EN": "Full Chain Tracker"},
    "demand_forecast": {"ZH": "需求预测", "EN": "Demand Forecast"},
    # 采购板块
    "procurement_db": {"ZH": "采购看板", "EN": "Procurement Dashboard"},
    "procurement_delivery": {"ZH": "采购交付分析", "EN": "Procurement Delivery"},
    # 库存板块
    "inventory_tracking": {"ZH": "库存追踪", "EN": "Inventory Tracking"},
    "inventory_health": {"ZH": "库存健康诊断", "EN": "Inventory Health"},
    # 物流板块
    "logistics_db": {"ZH": "物流看板", "EN": "Logistics Dashboard"},
    "in_transit_warning": {"ZH": "在途预警", "EN": "Transit Alerts"},
    "unsent_contracts": {"ZH": "合同未发出", "EN": "Unsent Contracts"},
    "pending_boxes": {"ZH": "待发木箱", "EN": "Pending Boxes"},
}

# 板块配置：板块Key -> 逻辑ID列表
BOARD_KEYS = {
    "ZH": ["📈 销售板块", "🏗️ 采购板块", "📦 库存板块", "🚢 物流板块"],
    "EN": ["📈 Sales", "📦 Procurement", "🏗️ Inventory", "🚢 Logistics"],
}

# 板块配置：板块Key -> 逻辑ID列表
BOARD_CONFIG = {
    "sales": ["sales_db", "pending_shipment", "backorder_analysis", "backorder_tracker", "demand_forecast"],
    "procurement": ["procurement_db", "procurement_delivery"],
    "inventory": ["inventory_tracking", "inventory_health"],
    "logistics": ["logistics_db", "in_transit_warning", "unsent_contracts", "pending_boxes"],
}

# 逻辑ID -> 渲染函数映射
RENDER_FUNCTIONS = {
    "sales_db": render_sales_dashboard,
    "pending_shipment": render_pending_shipment,
    "backorder_analysis": render_backorder_analysis,
    "backorder_tracker": render_backorder_chain_tracking,
    "demand_forecast": render_forecasting,
    "procurement_db": render_procurement_dashboard,
    "procurement_delivery": render_procurement_delivery_analysis,
    "inventory_tracking": render_inventory_dashboard,
    "inventory_health": render_inventory_dashboard,
    "logistics_db": render_logistics_dashboard,
    "in_transit_warning": render_in_transit_analysis,
    "unsent_contracts": render_unsent_contracts,
    "pending_boxes": render_pending_boxes,
}


def main():
    """
    主函数：应用入口
    """
    # --- 语言状态管理 ---
    if "lang" not in st.session_state:
        st.session_state.lang = "ZH"
    
    # 先获取当前语言状态用于选择器显示
    curr_lang = st.session_state.lang
    
    # 侧边栏语言切换
    lang_label = "🌐 Language" if curr_lang == "EN" else "🌐 语言"
    st.sidebar.markdown(f"### {lang_label}")
    lang_options = ["中文", "English"]
    lang_selection = st.sidebar.selectbox(
        "选择语言" if curr_lang == "ZH" else "Select Language",
        lang_options,
        index=0 if st.session_state.lang == "ZH" else 1,
        label_visibility="collapsed"
    )
    st.session_state.lang = "ZH" if lang_selection == "中文" else "EN"
    curr_lang = st.session_state.lang
    
    # 显示顶部标题（根据语言动态显示）
    if curr_lang == "EN":
        st.title("🏗️ XCMG North America Parts Management System")
    else:
        st.title("🏗️ 徐工北美备件管理系统")
    
    # 侧边栏导航
    nav_title = "🚗 Navigation" if curr_lang == "EN" else "🚗 备件管理系统"
    st.sidebar.title(nav_title)

    # 第一级：选择板块（下拉选择）
    board_label = "📂 Select Board" if curr_lang == "EN" else "📂 选择板块"
    board_options = BOARD_KEYS[curr_lang]
    selected_group_key = st.sidebar.selectbox(
        board_label,
        options=board_options,
        index=0
    )
    
    # 获取选中的板块对应的逻辑ID列表
    # 通过索引映射
    board_index = board_options.index(selected_group_key)
    board_keys_list = ["sales", "procurement", "inventory", "logistics"]
    selected_board_id = board_keys_list[board_index]
    sub_page_ids = BOARD_CONFIG[selected_board_id]
    # 将逻辑ID转换为当前语言显示名称
    sub_page_labels = [MENU_CONFIG[pid][curr_lang] for pid in sub_page_ids]
    
    st.sidebar.markdown("---")
    select_label = "Select Module:" if curr_lang == "EN" else "选择功能："
    st.sidebar.markdown(f"**{select_label}**")
    selected_label = st.sidebar.radio(
        "功能选择",
        options=sub_page_labels,
        label_visibility="collapsed"
    )
    
    # 将选中的标签转回逻辑ID（根据当前语言）
    page_id = [k for k, v in MENU_CONFIG.items() if v[curr_lang] == selected_label][0]

    # 数据刷新按钮
    st.sidebar.markdown("---")
    refresh_text = "🔄 Refresh Cache" if curr_lang == "EN" else "🔄 刷新数据"
    if st.sidebar.button(refresh_text):
        st.cache_data.clear()
        st.rerun()

    # 显示数据源状态
    from core.data_engine import check_data_folders
    status = check_data_folders()

    status_label = "📁 Data Sources" if curr_lang == "EN" else "📁 数据源状态"
    st.sidebar.markdown(f"### {status_label}")
    for name, info in status.items():
        if info["status"] == "ready":
            files_text = "files" if curr_lang == "EN" else "个文件"
            st.sidebar.success(f"✅ {name}: {info['file_count']} {files_text}")
        elif info["status"] == "warning":
            st.sidebar.warning(f"⚠️ {name}: {info['message']}")
        else:
            st.sidebar.error(f"❌ {name}: {info['message']}")

    # 年份全局筛选器（销售看板和采购相关页面使用）
    selected_years = None
    if page_id in ["sales_db", "procurement_db", "procurement_delivery"]:
        year_label = "📅 Select Years" if curr_lang == "EN" else "📅 年份筛选"
        st.sidebar.markdown(f"### {year_label}")
        
        # 尝试从数据中动态获取年份
        year_options = []
        try:
            if page_id in ["sales_db"]:
                from modules.sales import load_orders_data_with_cache
                orders_df, _ = load_orders_data_with_cache()
                if not orders_df.empty:
                    for col in orders_df.columns:
                        col_check = str(col)
                        if "时间" in col_check or "确认" in col_check:
                            try:
                                dates = pd.to_datetime(orders_df[col], errors="coerce")
                                years = dates.dt.year.dropna().astype(int).unique()
                                valid_years = sorted([int(y) for y in years if 2020 <= y <= 2030], reverse=True)
                                if valid_years:
                                    year_options = [str(y) for y in valid_years]
                                    break
                            except:
                                continue
        except:
            pass
        
        # 如果没有动态获取到年份，使用默认选项
        if not year_options:
            year_options = ["2026", "2025", "2024"]
        
        # 默认选择最新两个年份
        default_years = year_options[:2] if len(year_options) >= 2 else year_options
        
        all_text = "All" if curr_lang == "EN" else "全部"
        
        selected_year_option = st.sidebar.multiselect(
            "Select Years" if curr_lang == "EN" else "选择年份",
            year_options,
            default=default_years,
            key="year_selector"
        )
        
        if not selected_year_option or all_text in selected_year_option:
            selected_years = None
        else:
            selected_years = [int(y) for y in selected_year_option]

        st.session_state["selected_years"] = selected_years

    # 根据逻辑ID显示对应模块
    render_func = RENDER_FUNCTIONS.get(page_id)
    if render_func:
        # 将当前页面ID存入session_state，供子模块使用
        st.session_state["current_page_id"] = page_id
        render_func()
    elif page_id == "inventory_db":
        inv_msg = "🚧 Inventory Dashboard coming soon..." if curr_lang == "EN" else "🚧 库存看板开发中..."
        st.info(inv_msg)


if __name__ == "__main__":
    main()
