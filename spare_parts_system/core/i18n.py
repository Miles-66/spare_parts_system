# -*- coding: utf-8 -*-
"""
国际化翻译字典 (i18n)

用于系统UI文本的双语支持。
通过 get_text(key) 函数获取当前语言的文本。

使用方式:
    from core.i18n import get_text
    label = get_text("sales.total_purchase")
"""

# 翻译字典结构: {key: {ZH: 中文, EN: English}}
I18N = {
    # ==================== 通用文本 ====================
    "common": {
        "loading": {"ZH": "正在加载...", "EN": "Loading..."},
        "processing": {"ZH": "正在处理...", "EN": "Processing..."},
        "data_loaded": {"ZH": "数据已加载", "EN": "Data loaded"},
        "no_data": {"ZH": "暂无数据", "EN": "No data available"},
        "error": {"ZH": "错误", "EN": "Error"},
        "warning": {"ZH": "警告", "EN": "Warning"},
        "success": {"ZH": "成功", "EN": "Success"},
        "data_source": {"ZH": "数据源信息", "EN": "Data Source"},
        "available_columns": {"ZH": "可用列列表", "EN": "Available Columns"},
        "year_filter": {"ZH": "年份筛选", "EN": "Year Filter"},
        "all_years": {"ZH": "全部年份", "EN": "All Years"},
        "current_filter": {"ZH": "当前筛选", "EN": "Current Filter"},
        "select_year": {"ZH": "选择年份", "EN": "Select Year"},
    },

    # ==================== 销售模块 ====================
    "sales": {
        # 页面标题
        "page_title": {"ZH": "🚗 销售数据看板", "EN": "🚗 Sales Dashboard"},
        
        # KPI指标
        "kpi_title": {"ZH": "📊 核心指标", "EN": "📊 Key Metrics"},
        "total_sales": {"ZH": "💰 总销售额 (USD)", "EN": "💰 Total Sales ($)"},
        "total_orders": {"ZH": "📦 订单总数", "EN": "📦 Total Orders"},
        "avg_fulfillment": {"ZH": "✅ 平均现货满足率", "EN": "✅ Avg Fulfillment Rate"},
        
        # 趋势分析
        "monthly_trend": {"ZH": "📈 月度趋势分析", "EN": "📈 Monthly Trend"},
        "fulfillment_by_month": {"ZH": "📦 现货满足率（按月份）", "EN": "📦 Fulfillment Rate (by Month)"},
        "no_fulfillment_data": {"ZH": "暂无现货满足率数据", "EN": "No fulfillment data"},
        "month": {"ZH": "月份", "EN": "Month"},
        
        # 客户排行
        "customer_ranking": {"ZH": "🏆 客户排行", "EN": "🏆 Customer Ranking"},
        "customer_name": {"ZH": "客户名称", "EN": "Customer Name"},
        "no_customer_data": {"ZH": "暂无客户数据", "EN": "No customer data"},
        "missing_columns": {"ZH": "无法显示客户排行表：缺少必要的列", "EN": "Cannot display: missing required columns"},
        "total_customers": {"ZH": "共 {count} 个客户", "EN": "{count} customers"},
        
        # 异常分析
        "anomaly_analysis": {"ZH": "🚨 异常样本分析", "EN": "🚨 Anomaly Analysis"},
        "all_satisfied": {"ZH": "✅ 所有有效订单均满足现货条件！", "EN": "✅ All valid orders meet stock requirements!"},
        "no_shipping": {"ZH": "未发货", "EN": "Not shipped"},
        "late_shipping": {"ZH": "发货延迟", "EN": "Late shipping"},
        "slow_response": {"ZH": "响应太慢", "EN": "Slow response"},
        "anomaly_detail": {"ZH": "📋 异常订单明细（前10条）", "EN": "📋 Anomaly Details (Top 10)"},
        "total_anomalies": {"ZH": "共 {count} 条异常订单", "EN": "{count} anomaly orders"},
        
        # 筛选信息
        "filter_all_years": {"ZH": "📅 当前筛选：全部年份（已过滤2024年8月以前的数据）", 
                           "EN": "📅 Current Filter: All Years (data before Aug 2024 excluded)"},
        "filter_selected_years": {"ZH": "📅 当前筛选年份：{years}", "EN": "📅 Current Years: {years}"},
        "filter_selected_year": {"ZH": "📅 当前筛选年份：{year}", "EN": "📅 Current Year: {year}"},
        
        # 数据加载
        "loading_sales": {"ZH": "正在加载销售数据...", "EN": "Loading sales data..."},
        "processing_data": {"ZH": "正在处理数据...", "EN": "Processing data..."},
        "order_table": {"ZH": "订单表", "EN": "Order Table"},
        "shipping_table": {"ZH": "发货表", "EN": "Shipping Table"},
        "data_processing_failed": {"ZH": "❌ 数据处理失败，无法生成看板", "EN": "❌ Data processing failed"},
    },

    # ==================== 需求预测模块 ====================
    "forecasting": {
        # 页面标题
        "page_title": {"ZH": "📈 需求预测", "EN": "📈 Demand Forecast"},
        
        # 侧边栏参数
        "sidebar_params": {"ZH": "🔧 预测参数设置", "EN": "🔧 Forecast Parameters"},
        "backtest_period": {"ZH": "回测周期（月）", "EN": "Backtest Period (Months)"},
        "ma_window": {"ZH": "MA窗口大小", "EN": "MA Window Size"},
        "wma_weight": {"ZH": "WMA近期权重", "EN": "WMA Recent Weight"},
        "es_alpha": {"ZH": "ES平滑系数(α)", "EN": "ES Smoothing (α)"},
        
        # KPI指标
        "kpi_title": {"ZH": "📊 预测概览", "EN": "📊 Forecast Overview"},
        "total_forecast": {"ZH": "💰 下月预测总额", "EN": "💰 Next Month Forecast"},
        "skus_analyzed": {"ZH": "📦 分析SKU数", "EN": "📦 SKUs Analyzed"},
        "avg_accuracy": {"ZH": "🎯 平均准确率", "EN": "🎯 Avg Accuracy"},
        
        # 模型指标
        "model_accuracy": {"ZH": "准确率", "EN": "Accuracy"},
        "model_mae": {"ZH": "MAE误差", "EN": "MAE Error"},
        "stable_model": {"ZH": "稳定型", "EN": "Stable"},
        "trend_model": {"ZH": "趋势型", "EN": "Trend"},
        "next_month_forecast": {"ZH": "下月预测", "EN": "Next Month"},
        
        # 图表
        "forecast_chart": {"ZH": "📈 历史销量与预测对比", "EN": "📈 Historical vs Forecast"},
        "top_skus": {"ZH": "🔝 Top SKU预测", "EN": "🔝 Top SKU Forecast"},
        
        # 详情表
        "detail_table": {"ZH": "📋 物料预测详情", "EN": "📋 SKU Forecast Details"},
        "historical_avg": {"ZH": "历史月均", "EN": "Hist Avg"},
        "best_model": {"ZH": "最优模型", "EN": "Best Model"},
        
        # ABC/XYZ分类
        "abc_class": {"ZH": "ABC类别", "EN": "ABC Class"},
        "xyz_class": {"ZH": "XYZ类别", "EN": "XYZ Class"},
        "suggested_qty": {"ZH": "建议数量", "EN": "Suggested Qty"},
        "suggested_amount": {"ZH": "建议金额", "EN": "Suggested Amount"},
        "price_missing": {"ZH": "价格缺失", "EN": "Price Missing"},
        "active_material": {"ZH": "活跃物料", "EN": "Active Material"},
        
        # KPI新增
        "active_accuracy": {"ZH": "活跃物料平均准确率", "EN": "Active Material Avg Accuracy"},
        "suggested_total": {"ZH": "下月建议总采购金额", "EN": "Next Month Suggested Total"},
        "filter_by_abc": {"ZH": "按ABC类别筛选", "EN": "Filter by ABC Class"},
        "all_classes": {"ZH": "全部类别", "EN": "All Classes"},
        "sales_count": {"ZH": "销售次数", "EN": "Sales Count"},
        "volatility": {"ZH": "波动率", "EN": "Volatility"},
        
        # 状态信息
        "loading_forecast": {"ZH": "正在加载预测数据...", "EN": "Loading forecast data..."},
        "no_data": {"ZH": "暂无足够数据进行预测", "EN": "Insufficient data for forecast"},
        "calculating": {"ZH": "正在计算预测模型...", "EN": "Calculating forecast models..."},
    },

    # ==================== 库存模块 ====================
    "inventory": {
        # 页面标题
        "page_title": {"ZH": "📦 库存管理", "EN": "📦 Inventory Management"},
        
        # Tab标题
        "tab_tracking": {"ZH": "🔄 库存追踪", "EN": "🔄 Inventory Tracking"},
        "tab_health": {"ZH": "💊 库存健康诊断", "EN": "💊 Inventory Health"},
        
        # 侧边栏
        "sidebar_filters": {"ZH": "🔍 筛选条件", "EN": "🔍 Filters"},
        "sidebar_diag_filters": {"ZH": "🔍 诊断筛选", "EN": "🔍 Diagnostic Filters"},
        "start_date": {"ZH": "开始日期", "EN": "Start Date"},
        "refresh_data": {"ZH": "🔄 刷新数据", "EN": "🔄 Refresh Data"},
        "refresh_diag": {"ZH": "🔄 刷新诊断", "EN": "🔄 Refresh"},
        
        # 健康状态筛选
        "health_status_filter": {"ZH": "健康状态筛选", "EN": "Health Status Filter"},
        "all": {"ZH": "全部", "EN": "All"},
        "overstock": {"ZH": "积压", "EN": "Overstock"},
        "stockout": {"ZH": "缺货预警", "EN": "Stockout"},
        "normal": {"ZH": "正常", "EN": "Normal"},
        
        # 搜索
        "search_part": {"ZH": "🔍 物料号/名称搜索", "EN": "🔍 Search Part No/Name"},
        "search_placeholder": {"ZH": "输入物料号或物料名称...", "EN": "Enter part no or name..."},
        
        # 加载信息
        "loading_inventory": {"ZH": "加载库存追踪数据...", "EN": "Loading inventory tracking data..."},
        "loading_health": {"ZH": "正在分析库存健康状态...", "EN": "Analyzing inventory health..."},
        "no_inventory_data": {"ZH": "暂无库存追踪数据", "EN": "No inventory data available"},
        "no_health_data": {"ZH": "暂无健康诊断数据", "EN": "No health diagnostic data"},
        "load_failed": {"ZH": "加载数据失败", "EN": "Failed to load data"},
        "diag_load_failed": {"ZH": "加载诊断数据失败", "EN": "Failed to load diagnostic data"},
        
        # KPI指标
        "kpi_title": {"ZH": "📊 库存健康总览", "EN": "📊 Inventory Health Overview"},
        "total_parts": {"ZH": "总物料数", "EN": "Total SKUs"},
        "total_inventory_value": {"ZH": "总库存价值(K)", "EN": "Total Inventory Value(K)"},
        "normal_value": {"ZH": "正常库存价值(K)", "EN": "Normal Value(K)"},
        "stockout_value": {"ZH": "缺货总价(K)", "EN": "Stockout Value(K)"},
        "overstock_value": {"ZH": "积压总价(K)", "EN": "Overstock Value(K)"},
        
        # 健康比例
        "health_ratio": {"ZH": "库存健康比例", "EN": "Health Ratio"},
        
        # 健康等级分布
        "health_distribution": {"ZH": "🏥 健康等级分布", "EN": "🏥 Health Level Distribution"},
        "health_level": {"ZH": "健康等级占比", "EN": "Health Level Proportion"},
    },

    # ==================== 采购模块 ====================
    "procurement": {
        # 页面标题
        "page_title": {"ZH": "📦 采购看板", "EN": "📦 Procurement Dashboard"},
        
        # KPI指标
        "kpi_title": {"ZH": "📊 核心指标", "EN": "📊 Key Metrics"},
        "total_procurement": {"ZH": "💰 总采购额", "EN": "💰 Total Procurement"},
        "order_count": {"ZH": "📋 订单总数", "EN": "📋 Total Orders"},
        "avg_unit_price": {"ZH": "💵 平均采购单价", "EN": "💵 Avg Unit Price"},
        
        # 趋势分析
        "monthly_procurement": {"ZH": "📈 月度采购趋势", "EN": "📈 Monthly Procurement Trend"},
        
        # OEM分布
        "oem_distribution": {"ZH": "🏭 主机厂分布", "EN": "🏭 OEM Distribution"},
        
        # 物料排行
        "part_ranking": {"ZH": "🔧 物料排行", "EN": "🔧 Part Ranking"},
        "part_no": {"ZH": "物料号", "EN": "Part No"},
        "part_desc": {"ZH": "物料描述", "EN": "Description"},
        "procurement_amount": {"ZH": "采购金额", "EN": "Amount"},
        
        # 筛选信息
        "filter_all_years": {"ZH": "📅 当前筛选：全部年份", "EN": "📅 Current Filter: All Years"},
        
        # 数据加载
        "loading_procurement": {"ZH": "正在加载采购数据...", "EN": "Loading procurement data..."},
        "empty_data": {"ZH": "⚠️ 采购数据为空", "EN": "⚠️ Procurement data is empty"},
        
        # 数据预处理
        "data_preprocessing": {"ZH": "🔧 数据预处理", "EN": "🔧 Data Preprocessing"},
    },

    # ==================== 物流模块 ====================
    "logistics": {
        # 页面标题
        "page_title": {"ZH": "🚚 物流成本分析", "EN": "🚚 Logistics Cost Analysis"},
        
        # KPI指标
        "kpi_title": {"ZH": "📊 核心指标", "EN": "📊 Key Metrics"},
        "freight_2024": {"ZH": "💰 2024年运费总额", "EN": "💰 2024 Freight Total"},
        "freight_2025": {"ZH": "💰 2025年运费总额", "EN": "💰 2025 Freight Total"},
        "total_cost": {"ZH": "📦 总成本", "EN": "📦 Total Cost"},
        
        # 趋势分析
        "freight_trend": {"ZH": "📈 运费趋势", "EN": "📈 Freight Trend"},
        "monthly_freight": {"ZH": "月度运费趋势", "EN": "Monthly Freight Trend"},
        
        # 发运方式分布
        "shipping_method_dist": {"ZH": "🚢 发运方式分布", "EN": "🚢 Shipping Method Distribution"},
        "freight_by_method": {"ZH": "发运方式运费分布", "EN": "Freight by Shipping Method"},
        
        # 成本结构
        "cost_structure": {"ZH": "💵 成本结构", "EN": "💵 Cost Structure"},
        "freight_vs_contract": {"ZH": "运费与合同明细总价比例", "EN": "Freight vs Contract Price"},
        "freight": {"ZH": "运费", "EN": "Freight"},
        "contract_price": {"ZH": "合同明细总价", "EN": "Contract Price"},
        
        # 年度对比
        "yearly_comparison": {"ZH": "📅 年度对比", "EN": "📅 Yearly Comparison"},
        "yearly_freight": {"ZH": "年度运费对比（单位：千美元）", "EN": "Yearly Freight (K USD)"},
        
        # 明细表
        "detail_table": {"ZH": "📋 物流明细数据（前100行）", "EN": "📋 Logistics Details (Top 100)"},
        "create_time": {"ZH": "创建时间", "EN": "Create Time"},
        "shipping_method": {"ZH": "发运方式", "EN": "Shipping Method"},
        "total_price": {"ZH": "总成本", "EN": "Total Cost"},
        
        # 筛选信息
        "logistics_filter": {"ZH": "🔍 物流分析筛选", "EN": "🔍 Logistics Filter"},
        
        # 数据加载
        "loading_logistics": {"ZH": "正在加载物流数据...", "EN": "Loading logistics data..."},
        "empty_data": {"ZH": "⚠️ 物流数据为空", "EN": "⚠️ Logistics data is empty"},
        "no_date_column": {"ZH": "❌ 未找到创建时间列", "EN": "❌ Create time column not found"},
    },

    # ==================== 缺货全链路追踪 ====================
    "backorder": {
        # 页面标题
        "page_title": {"ZH": "🔍 缺货全链路追踪", "EN": "🔍 Backorder Chain Tracking"},
        
        # 状态筛选
        "status_filter": {"ZH": "🔍 状态筛选", "EN": "🔍 Status Filter"},
        "all_status": {"ZH": "全部状态", "EN": "All Status"},
        "confirmed_purchased": {"ZH": "确认为已购", "EN": "Confirmed Purchased"},
        "suspected_purchased": {"ZH": "疑似已购", "EN": "Suspected Purchased"},
        "unrelated_purchase": {"ZH": "存在不相关采购", "EN": "Unrelated Purchase"},
        "not_matched": {"ZH": "未匹配", "EN": "Not Matched"},
        
        # 统计信息
        "total_backorders": {"ZH": "缺货总数量", "EN": "Total Backorders"},
        "matched": {"ZH": "已匹配", "EN": "Matched"},
        "unmatched": {"ZH": "未匹配", "EN": "Unmatched"},
        
        # 链式信息
        "chain_info": {"ZH": "🔗 链式信息", "EN": "🔗 Chain Info"},
        "purchase_info": {"ZH": "采购信息", "EN": "Purchase Info"},
        "shipping_info": {"ZH": "发货信息", "EN": "Shipping Info"},
        "box_info": {"ZH": "箱号信息", "EN": "Box Info"},
        "contract_info": {"ZH": "合同信息", "EN": "Contract Info"},
        
        # 搜索
        "search_placeholder": {"ZH": "搜索备件号、客户订单号...", "EN": "Search part no, customer order no..."},
    },

    # ==================== 采购交付分析 ====================
    "procurement_delivery": {
        "page_title": {"ZH": "📦 采购交付分析", "EN": "📦 Procurement Delivery Analysis"},
    },

    # ==================== 待发货清单 ====================
    "pending_shipment": {
        "page_title": {"ZH": "📋 待发货清单", "EN": "📋 Pending Shipment List"},
    },

    # ==================== 缺货分析 ====================
    "backorder_analysis": {
        "page_title": {"ZH": "📊 缺货分析", "EN": "📊 Backorder Analysis"},
    },

    # ==================== 在途预警 ====================
    "in_transit": {
        "page_title": {"ZH": "🚚 在途预警", "EN": "🚚 In-Transit Alerts"},
    },

    # ==================== 合同未发出 ====================
    "unsent_contract": {
        "page_title": {"ZH": "📄 合同未发出", "EN": "📄 Unsent Contracts"},
    },

    # ==================== 待发木箱 ====================
    "pending_box": {
        "page_title": {"ZH": "📦 待发木箱", "EN": "📦 Pending Boxes"},
    },

    # ==================== 缺货分析 ====================
    "backorder_analysis": {
        "page_title": {"ZH": "📊 缺货分析", "EN": "📊 Backorder Analysis"},
        "order_file_not_found": {"ZH": "未找到订单明细文件", "EN": "Order detail file not found"},
        "shipping_file_not_found": {"ZH": "未找到发货明细文件", "EN": "Shipping detail file not found"},
        "missing_key_columns_order": {"ZH": "订单表缺少关键列", "EN": "Order table missing key columns"},
        "missing_key_columns_shipping": {"ZH": "发货表缺少关键列", "EN": "Shipping table missing key columns"},
        "no_shipped_records": {"ZH": "没有已发货的记录", "EN": "No shipped records found"},
        "all_orders_shipped": {"ZH": "✅ 所有订单都已正常发货，没有缺货记录！", "EN": "✅ All orders shipped, no backorders!"},
        "filtered_records_remaining": {"ZH": "已过滤无效数据，剩余 {count} 条缺货记录", "EN": "Filtered invalid data, {count} backorder records remaining"},
        "backorder_overview": {"ZH": "📊 缺货概况", "EN": "📊 Backorder Overview"},
        "backorder_orders": {"ZH": "📦 缺货订单数", "EN": "📦 Backorder Orders"},
        "avg_backorder_days": {"ZH": "⏱️ 平均缺货天数", "EN": "⏱️ Avg Backorder Days"},
        "monthly_backorder_trend": {"ZH": "📈 月度缺货趋势", "EN": "📈 Monthly Backorder Trend"},
        "monthly_backorder_orders": {"ZH": "📊 每月缺货订单数", "EN": "📊 Monthly Backorder Orders"},
        "backorder_detail": {"ZH": "📋 缺货订单明细", "EN": "📋 Backorder Details"},
        "cannot_display_detail": {"ZH": "无法显示明细表", "EN": "Cannot display detail table"},
        "total_backorder_records": {"ZH": "共 {count} 条缺货记录", "EN": "{count} backorder records"},
    },

    # ==================== 待发货清单 ====================
    "pending_shipment": {
        "page_title": {"ZH": "📋 待发货清单", "EN": "📋 Pending Shipment List"},
        "pending_file_not_found": {"ZH": "未找到待发货清单文件", "EN": "Pending shipment file not found"},
    },

    # ==================== 缺货全链路追踪 ====================
    "backorder_tracker": {
        "page_title": {"ZH": "🔍 缺货全链路追踪", "EN": "🔍 Backorder Chain Tracking"},
        "visual_tracker": {"ZH": "🚚 备件快递进度条", "EN": "🚚 Parts Express Progress"},
        "search_placeholder": {"ZH": "输入 客户订单号 或 物料号 进行搜索", "EN": "Enter customer order no or part no to search"},
        "search_placeholder_eg": {"ZH": "例如: 4623123456", "EN": "e.g., 4623123456"},
        "search_type": {"ZH": "搜索类型", "EN": "Search Type"},
        "search_customer_order": {"ZH": "客户订单号", "EN": "Customer Order No"},
        "search_part_no": {"ZH": "物料号", "EN": "Part No"},
        "enter_search_keyword": {"ZH": "请输入搜索关键词", "EN": "Please enter search keyword"},
        "no_matching_records": {"ZH": "未找到匹配记录", "EN": "No matching records found"},
        "found_records": {"ZH": "找到 {count} 条匹配记录", "EN": "Found {count} matching records"},
        "node1_title": {"ZH": "📦 节点 1: 缺货登记", "EN": "📦 Node 1: Backorder Registration"},
        "status_completed": {"ZH": "状态: ✅ 已完成", "EN": "Status: ✅ Completed"},
        "node2_title": {"ZH": "🏭 节点 2: 采购确认", "EN": "🏭 Node 2: Procurement Confirmation"},
        "node3_title": {"ZH": "📦 节点 3: 仓库装箱", "EN": "📦 Node 3: Warehouse Packing"},
        "node4_title": {"ZH": "📄 节点 4: 合同完成", "EN": "📄 Node 4: Contract Completion"},
        "node5_title": {"ZH": "🚚 节点 5: 物流在途", "EN": "🚚 Node 5: In Transit"},
        "status_in_progress": {"ZH": "⏳ 进行中", "EN": "⏳ In Progress"},
        "sap_order_no": {"ZH": "SAP订单号", "EN": "SAP Order No"},
        "sap_submit_time": {"ZH": "SAP提交时间", "EN": "SAP Submit Time"},
        "eta": {"ZH": "ETA", "EN": "ETA"},
        "waiting_procurement": {"ZH": "等待采购确认...", "EN": "Waiting for procurement confirmation..."},
        "box_no": {"ZH": "箱号", "EN": "Box No"},
        "box_date": {"ZH": "装箱日期", "EN": "Packing Date"},
        "waiting_warehouse": {"ZH": "等待仓库备货...", "EN": "Waiting for warehouse preparation..."},
        "contract_no": {"ZH": "合同号", "EN": "Contract No"},
        "contract_date": {"ZH": "合同日期", "EN": "Contract Date"},
        "waiting_contract": {"ZH": "等待合同制作...", "EN": "Waiting for contract..."},
        "ship_no": {"ZH": "发车号", "EN": "Ship No"},
        "ship_date": {"ZH": "发车日期", "EN": "Ship Date"},
        "eta_arrival": {"ZH": "预计到港日期", "EN": "ETA Arrival"},
        "arrival_location": {"ZH": "到港地点", "EN": "Arrival Location"},
        "creator": {"ZH": "创建人", "EN": "Creator"},
        "waiting_shipment": {"ZH": "等待发车...", "EN": "Waiting for shipment..."},
        "suspect_match_warning": {"ZH": "⚠️ 此为疑似匹配，请人工核对确认", "EN": "⚠️ This is a suspected match, please verify manually"},
        "part_desc": {"ZH": "物料描述", "EN": "Part Description"},
        "backorder_qty": {"ZH": "缺货数量", "EN": "Backorder Qty"},
        "suspected_order_comparison": {"ZH": "🔍 疑似订单穿透对比", "EN": "🔍 Suspected Order Comparison"},
        "no_suspected_orders": {"ZH": "✅ 当前视图中没有疑似已购订单", "EN": "✅ No suspected purchased orders in current view"},
        "select_suspected_order": {"ZH": "选择疑似订单", "EN": "Select Suspected Order"},
        "backorder_detail_title": {"ZH": "📦 缺货需求详情", "EN": "📦 Backorder Demand Details"},
        "closest_procurement": {"ZH": "🏭 最接近的采购记录", "EN": "🏭 Closest Procurement Record"},
        "customer_order_no": {"ZH": "客户订单号", "EN": "Customer Order No"},
        "part_no": {"ZH": "物料号", "EN": "Part No"},
        "unshipped_qty": {"ZH": "未发数量", "EN": "Unshipped Qty"},
        "create_time": {"ZH": "创建时间", "EN": "Create Time"},
        "sap_order_no": {"ZH": "SAP单号", "EN": "SAP Order No"},
        "factory": {"ZH": "主机厂", "EN": "Factory"},
        "responsible_person": {"ZH": "负责人", "EN": "Responsible Person"},
        "procurement_qty": {"ZH": "采购数量", "EN": "Procurement Qty"},
        "suspected_found_info": {"ZH": "📋 发现 {total} 条疑似已购订单（其中 {packed} 条已装箱，{unpacked} 条待装箱），选择一条查看详细对比", 
                               "EN": "📋 Found {total} suspected purchased orders ({packed} packed, {unpacked} pending), select one to view details"},
        "total_records": {"ZH": "共 {current} 条记录（原始总数：{original}）", "EN": "{current} records (original total: {original})"},
        "box_qty": {"ZH": "装箱数量", "EN": "Box Qty"},
    },
}


def get_text(key: str, default: str = None) -> str:
    """
    获取当前语言的翻译文本
    
    Args:
        key: 翻译键，格式为 "模块.key" 或 "common.key"
              例如: "sales.total_purchase", "common.loading"
        default: 默认值，如果key不存在则返回此值
    
    Returns:
        str: 当前语言的翻译文本
    """
    # 获取当前语言
    lang = "ZH"
    try:
        import streamlit as st
        lang = st.session_state.get("lang", "ZH")
    except:
        pass
    
    # 解析key
    if "." in key:
        module, subkey = key.split(".", 1)
    else:
        module = "common"
        subkey = key
    
    # 查找翻译
    if module in I18N and subkey in I18N[module]:
        translations = I18N[module][subkey]
        if isinstance(translations, dict) and lang in translations:
            return translations[lang]
        elif isinstance(translations, str):
            return translations
    
    # 如果没找到，返回default或key
    if default:
        return default
    return key


def get_text_safe(key: str, **kwargs) -> str:
    """
    获取翻译文本，支持格式化
    
    Args:
        key: 翻译键
        **kwargs: 格式化参数，例如: get_text("sales.total_customers", count=10)
    
    Returns:
        str: 格式化后的翻译文本
    """
    text = get_text(key)
    
    # 格式化
    if kwargs:
        try:
            text = text.format(**kwargs)
        except:
            pass
    
    return text
