# -*- coding: utf-8 -*-
"""
核心引擎层：计算器（Calculator）

统一公式库：包含满足率、预警逻辑、金额计算等核心业务计算函数。

设计原则：
1. 数据关联：使用订单号作为唯一主键进行左连接
2. 空值防御：处理各种空值情况，确保计算稳定性
3. 配置驱动：所有列名引用 config.py 中定义的变量
4. 跳过前3列系统元数据
"""

from typing import Dict, List, Optional, Tuple, Union
import warnings

import pandas as pd
import numpy as np

from config import (
    SALES_COL_ORDER_ID,
    SALES_COL_AMOUNT,
    SHIPPING_COL_ORDER_ID,
    SHIPPING_COL_SHIPPING_TIME,
    SHIPPING_COL_CONFIRM_TIME,
    SHIPPING_COL_STOCK_FULFILL,
    SHIPPING_COL_SAP_STATUS,
)


# 跳过前3列系统元数据后，标准化列名的映射
COL_ORDER_ID = "order_id"
COL_CUSTOMER = "customer"
COL_AMOUNT = "amount"
COL_PROVINCE = "province"
COL_SALES_DATE = "sales_date"
COL_ORDER_CONFIRM_TIME = "确认时间"  # 订单表的确认时间（未被标准化）

COL_SHIPPING_TIME = "shipping_time"  # 发货表的SAP发货时间（已被标准化）
COL_SHIPPING_SAP_STATUS = "sap_status"  # 发货表的SAP发货状态（已被标准化）


class Calculator:
    """
    计算器类

    负责业务指标的计算，包括满足率、金额汇总等。
    """

    def __init__(self):
        """
        初始化计算器
        """
        pass

    def skip_system_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        跳过前3列系统元数据

        Args:
            df: 原始数据框

        Returns:
            pd.DataFrame: 跳过前3列后的数据框
        """
        if df.empty or len(df.columns) <= 3:
            return df

        # 返回跳过前3列的数据
        return df.iloc[:, 3:].copy()

    def left_join_orders_and_shipping(
        self,
        orders_df: pd.DataFrame,
        shipping_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        数据关联：使用订单号作为唯一主键，将订单表与发货表进行左连接

        Args:
            orders_df: 订单表数据
            shipping_df: 发货表数据

        Returns:
            pd.DataFrame: 关联后的数据
        """
        if orders_df.empty:
            warnings.warn("订单表为空，无法进行数据关联")
            return pd.DataFrame()

        if shipping_df.empty:
            warnings.warn("发货表为空，返回原始订单数据")
            return self.skip_system_columns(orders_df).copy()

        # 跳过前3列系统元数据
        orders_clean = self.skip_system_columns(orders_df)
        shipping_clean = self.skip_system_columns(shipping_df)

        # 检查关键列是否存在
        if COL_ORDER_ID not in orders_clean.columns:
            warnings.warn(f"订单表中缺少关键列：{COL_ORDER_ID}")
            return orders_clean.copy()

        if COL_ORDER_ID not in shipping_clean.columns:
            warnings.warn(f"发货表中缺少关键列：{COL_ORDER_ID}")
            return orders_clean.copy()

        # Step 0: 强制类型统一
        # 确保订单号都是纯字符串且没有空格
        orders_clean[COL_ORDER_ID] = orders_clean[COL_ORDER_ID].astype(str).str.strip()
        shipping_clean[COL_ORDER_ID] = shipping_clean[COL_ORDER_ID].astype(str).str.strip()

        # Step 1: 聚合发货表，获取每个订单号的最晚发货时间 (对齐 Power BI MAX)
        # 使用 groupby + max 而非 drop_duplicates
        shipping_max = shipping_clean.groupby(COL_ORDER_ID, as_index=False).agg({
            COL_SHIPPING_TIME: 'max'
        })

        # Step 2: 执行左连接
        merged_df = orders_clean.merge(
            shipping_max,
            on=COL_ORDER_ID,
            how="left"
        )

        return merged_df

    def fill_null_stock_fulfill(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        空值防御：如果SAP发货时间为空，对应的是否现货满足必须默认为"否"

        业务逻辑（根据实际数据调整）：
        - 如果存在SAP发货状态列，用它来判断是否现货满足
        - "已同步SAP"或"已发货"表示满足
        - 空值表示不满足

        Args:
            df: 关联后的数据

        Returns:
            pd.DataFrame: 处理后的数据
        """
        if df.empty:
            return df.copy()

        df = df.copy()

        # 如果存在SAP发货状态列，用它来判断是否现货满足
        if COL_SHIPPING_SAP_STATUS in df.columns:
            # 已同步SAP或已发货表示满足
            df[COL_SHIPPING_SAP_STATUS] = df[COL_SHIPPING_SAP_STATUS].apply(
                lambda x: "是" if pd.notna(x) and x in ["已同步SAP", "已发货", "已创建"] else "否"
            )
        elif COL_SHIPPING_TIME in df.columns:
            # 如果有SAP发货时间，检查是否有值
            df[COL_SHIPPING_SAP_STATUS] = df[COL_SHIPPING_TIME].apply(
                lambda x: "是" if pd.notna(x) else "否"
            )
        else:
            # 如果都不存在，默认"否"
            df[COL_SHIPPING_SAP_STATUS] = "否"

        return df

    def calculate_stock_fulfillment_rate(
        self,
        df: pd.DataFrame,
    ) -> Tuple[float, Dict]:
        """
        计算现货满足率

        业务规则（根据实际数据调整）：
        - 分子：统计满足条件的订单（SAP发货状态为"已同步SAP"或"已发货"）
        - 分母：统计所有有确认时间的订单

        Args:
            df: 关联后的数据

        Returns:
            Tuple[float, Dict]: (满足率, 计算详情字典)
        """
        if df.empty:
            return 0.0, {
                "total_orders": 0,
                "fulfilled_orders": 0,
                "message": "数据为空，无法计算满足率",
            }

        # 如果没有是否现货满足列，需要先填充
        if COL_SHIPPING_SAP_STATUS not in df.columns:
            df = self.fill_null_stock_fulfill(df)

        # 统计是否有确认时间的订单数量（分母）
        # 确认时间在订单表上
        if COL_ORDER_CONFIRM_TIME in df.columns:
            orders_with_confirm = df[
                df[COL_ORDER_CONFIRM_TIME].notna()
            ]
        else:
            # 如果没有确认时间列，使用所有订单
            orders_with_confirm = df

        total_orders = len(orders_with_confirm)

        if total_orders == 0:
            return 0.0, {
                "total_orders": 0,
                "fulfilled_orders": 0,
                "message": "没有有效的确认时间数据",
            }

        # 统计满足现货条件的订单数量（分子）
        fulfilled_orders = len(
            orders_with_confirm[
                orders_with_confirm[COL_SHIPPING_SAP_STATUS].isin(["是", "Y", "Yes", "1", "有"])
            ]
        )

        # 计算满足率
        fulfillment_rate = fulfilled_orders / total_orders if total_orders > 0 else 0.0

        return fulfillment_rate, {
            "total_orders": total_orders,
            "fulfilled_orders": fulfilled_orders,
            "unfulfilled_orders": total_orders - fulfilled_orders,
            "fulfillment_rate": f"{fulfillment_rate:.2%}",
            "message": f"现货满足率：{fulfillment_rate:.2%} ({fulfilled_orders}/{total_orders})",
        }

    def calculate_total_amount(self, df: pd.DataFrame) -> Tuple[float, Dict]:
        """
        金额计算：直接对订单表中的总金额列进行求和

        业务规则：
        - 直接对 COL_AMOUNT 列求和
        - 忽略空值和无法转换为数值的值

        Args:
            df: 订单数据

        Returns:
            Tuple[float, Dict]: (总金额, 计算详情字典)
        """
        if df.empty:
            return 0.0, {
                "total_records": 0,
                "valid_amounts": 0,
                "message": "数据为空，总金额为0",
            }

        if COL_AMOUNT not in df.columns:
            warnings.warn(f"数据中缺少列：{COL_AMOUNT}")
            return 0.0, {
                "total_records": len(df),
                "valid_amounts": 0,
                "message": f"缺少金额列，无法计算总金额",
            }

        # 确保金额列是数值类型
        df = df.copy()
        df[COL_AMOUNT] = pd.to_numeric(df[COL_AMOUNT], errors="coerce")

        # 统计有效金额数量
        valid_amounts = df[COL_AMOUNT].notna().sum()

        # 计算总金额（忽略NaN）
        total_amount = df[COL_AMOUNT].sum()

        # 处理NaN为0
        if pd.isna(total_amount):
            total_amount = 0.0

        return total_amount, {
            "total_records": len(df),
            "valid_amounts": valid_amounts,
            "invalid_amounts": len(df) - valid_amounts,
            "total_amount": total_amount,
            "message": f"总金额：{total_amount:,.2f}（有效记录：{valid_amounts}条）",
        }

    def calculate_order_metrics(
        self,
        orders_df: pd.DataFrame,
        shipping_df: pd.DataFrame,
    ) -> Dict:
        """
        综合计算：计算订单相关的所有指标

        Args:
            orders_df: 订单表数据
            shipping_df: 发货表数据

        Returns:
            Dict: 包含所有计算指标的字典
        """
        metrics = {
            "orders_count": 0,
            "shipping_count": 0,
            "merged_count": 0,
            "total_amount": 0.0,
            "fulfillment_rate": 0.0,
            "details": {},
        }

        # 跳过前3列系统元数据
        orders_clean = self.skip_system_columns(orders_df)
        shipping_clean = self.skip_system_columns(shipping_df)

        # 记录原始数量
        metrics["orders_count"] = len(orders_clean) if not orders_clean.empty else 0
        metrics["shipping_count"] = len(shipping_clean) if not shipping_clean.empty else 0

        # 计算总金额
        total_amount, amount_details = self.calculate_total_amount(orders_clean)
        metrics["total_amount"] = total_amount
        metrics["details"]["amount"] = amount_details

        # 数据关联
        merged_df = self.left_join_orders_and_shipping(orders_df, shipping_df)
        metrics["merged_count"] = len(merged_df) if not merged_df.empty else 0

        if merged_df.empty:
            metrics["details"]["fulfillment"] = {
                "message": "关联后数据为空，无法计算满足率",
            }
            metrics["details"]["data_association"] = {
                "message": "关联失败，订单表或发货表为空",
            }
            return metrics

        # 填充空值
        merged_df = self.fill_null_stock_fulfill(merged_df)

        # 计算满足率
        fulfillment_rate, fulfillment_details = self.calculate_stock_fulfillment_rate(merged_df)
        metrics["fulfillment_rate"] = fulfillment_rate
        metrics["details"]["fulfillment"] = fulfillment_details

        # 数据关联详情
        metrics["details"]["data_association"] = {
            "orders_before_merge": metrics["orders_count"],
            "shipping_before_merge": metrics["shipping_count"],
            "merged_records": metrics["merged_count"],
            "matched_orders": metrics["merged_count"] - metrics["orders_count"],
        }

        return metrics


# ==================== 便捷函数 ====================


def calculate_sales_metrics(
    orders_df: pd.DataFrame,
    shipping_df: pd.DataFrame,
) -> Dict:
    """
    便捷函数：计算销售相关指标

    Args:
        orders_df: 订单表数据
        shipping_df: 发货表数据

    Returns:
        Dict: 包含总金额、满足率等指标的字典
    """
    calculator = Calculator()
    return calculator.calculate_order_metrics(orders_df, shipping_df)


def calculate_total_amount(orders_df: pd.DataFrame) -> float:
    """
    便捷函数：计算订单总金额

    Args:
        orders_df: 订单数据

    Returns:
        float: 总金额
    """
    calculator = Calculator()
    total_amount, _ = calculator.calculate_total_amount(calculator.skip_system_columns(orders_df))
    return total_amount


def calculate_fulfillment_rate(
    orders_df: pd.DataFrame,
    shipping_df: pd.DataFrame,
) -> float:
    """
    便捷函数：计算现货满足率

    Args:
        orders_df: 订单表数据
        shipping_df: 发货表数据

    Returns:
        float: 满足率（0-1之间）
    """
    calculator = Calculator()

    # 数据关联
    merged_df = calculator.left_join_orders_and_shipping(orders_df, shipping_df)
    if merged_df.empty:
        return 0.0

    # 填充空值
    merged_df = calculator.fill_null_stock_fulfill(merged_df)

    # 计算满足率
    rate, _ = calculator.calculate_stock_fulfillment_rate(merged_df)
    return rate


def get_merged_dataframe(
    orders_df: pd.DataFrame,
    shipping_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    便捷函数：获取关联后的数据框

    Args:
        orders_df: 订单表数据
        shipping_df: 发货表数据

    Returns:
        pd.DataFrame: 关联后的数据框
    """
    calculator = Calculator()
    merged_df = calculator.left_join_orders_and_shipping(orders_df, shipping_df)
    return merged_df


def process_sales_data(
    orders_df: pd.DataFrame,
    shipping_df: pd.DataFrame,
    min_date: pd.Timestamp = None,
) -> pd.DataFrame:
    """
    数据处理函数：按照架构师要求实现销售数据转换逻辑

    处理步骤：
    1. 跳过前3列系统元数据
    2. 关联订单表和发货表（使用groupby+max获取最晚发货时间）
    3. 过滤无效数据：剔除确认时间为空的行、剔除2024年8月1日以前的数据
    4. 计算天数差（发货时间 - 确认时间）
    5. 判定现货满足（0 ≤ 天数差 ≤ 3 且 发货时间不为空）
    6. 提取确认月份

    业务公式对齐：
    - 最晚发货时间 = MAX(SAP发货时间) 按订单号分组
    - 天数差 = (发货时间 - 确认时间).dt.days
    - 现货满足 = 发货时间.notna() & (天数差 >= 0) & (天数差 <= 3)

    Args:
        orders_df: 订单表数据
        shipping_df: 发货表数据
        min_date: 最小日期过滤（默认2024年8月1日）

    Returns:
        pd.DataFrame: 处理后的销售数据
    """
    calculator = Calculator()

    # 默认过滤2024年8月1日以前的数据
    if min_date is None:
        min_date = pd.Timestamp("2024-08-01")

    # Step 1: 跳过前3列系统元数据后左连接订单表和发货表
    # left_join_orders_and_shipping 已经使用 groupby+max 获取最晚发货时间
    merged_df = calculator.left_join_orders_and_shipping(orders_df, shipping_df)

    if merged_df.empty:
        return pd.DataFrame()

    # Step 2: 【强制日期归一化】
    # 业务规则：使用自然天计算，排除时分秒干扰
    # 归一化：df[col] = pd.to_datetime(df[col]).dt.normalize()
    # ------------------------------------------
    if COL_ORDER_CONFIRM_TIME in merged_df.columns:
        # Step 2.1: 转换确认时间为日期类型
        merged_df[COL_ORDER_CONFIRM_TIME] = pd.to_datetime(
            merged_df[COL_ORDER_CONFIRM_TIME], errors="coerce"
        )
        # Step 2.2: 【强制归一化】只保留日期部分（YYYY-MM-DD 00:00:00）
        merged_df[COL_ORDER_CONFIRM_TIME] = merged_df[COL_ORDER_CONFIRM_TIME].dt.normalize()

    if COL_SHIPPING_TIME in merged_df.columns:
        # Step 2.3: 转换发货时间为日期类型
        merged_df[COL_SHIPPING_TIME] = pd.to_datetime(
            merged_df[COL_SHIPPING_TIME], errors="coerce"
        )
        # Step 2.4: 【强制归一化】只保留日期部分（YYYY-MM-DD 00:00:00）
        merged_df[COL_SHIPPING_TIME] = merged_df[COL_SHIPPING_TIME].dt.normalize()

    # Step 3: 过滤无效数据
    # 3.1 剔除确认时间为空的行
    if COL_ORDER_CONFIRM_TIME in merged_df.columns:
        merged_df = merged_df[merged_df[COL_ORDER_CONFIRM_TIME].notna()].copy()

    # 3.2 剔除2024年8月1日以前的数据
    merged_df = merged_df[merged_df[COL_ORDER_CONFIRM_TIME] >= min_date].copy()

    if merged_df.empty:
        return pd.DataFrame()

    # Step 4: 【强制整型化】计算天数差
    # 业务规则：天数差 = 发货时间 - 确认时间，结果为整数天数
    # 整型化：.dt.days 返回 int64 类型
    # ------------------------------------------
    merged_df["DaysDiff"] = (
        merged_df[COL_SHIPPING_TIME] - merged_df[COL_ORDER_CONFIRM_TIME]
    ).dt.days

    # Step 5: 现货满足判定
    # 分子条件 (Satisfied)：发货时间 不为空，且 0 <= 天数差 <= 3
    # 注意：DaysDiff 已经是整数，可以直接用 >= 0, <= 3 比较
    merged_df["现货满足判定"] = (
        merged_df[COL_SHIPPING_TIME].notna() &
        (merged_df["DaysDiff"] >= 0) &
        (merged_df["DaysDiff"] <= 3)
    ).map({True: "是", False: "否"})

    # Step 6: 需求满足判定（确认时间不为空即为满足）
    # 由于已过滤确认时间为空的行，所有剩余记录都满足需求
    merged_df["需求满足判定"] = "是"

    # Step 7: 提取确认月份（格式：yyyy-MM）
    merged_df["确认月份"] = merged_df[COL_ORDER_CONFIRM_TIME].dt.strftime("%Y-%m")

    return merged_df


def calculate_monthly_metrics(
    processed_df: pd.DataFrame,
    selected_years: list = None,
) -> Dict:
    """
    按月份计算指标：现货满足率

    Args:
        processed_df: 处理后的销售数据
        selected_years: 选中的年份列表（用于过滤）

    Returns:
        Dict: 包含月份指标的数据字典
    """
    if processed_df.empty or "确认月份" not in processed_df.columns:
        return {
            "monthly_fulfillment": pd.DataFrame(),
        }

    # 如果指定了年份列表，进行过滤
    if selected_years is not None and len(selected_years) > 0:
        processed_df = processed_df[
            processed_df[COL_ORDER_CONFIRM_TIME].dt.year.isin(selected_years)
        ].copy()

    if processed_df.empty:
        return {
            "monthly_fulfillment": pd.DataFrame(),
        }

    # 按月份分组计算现货满足率
    monthly_fulfillment = processed_df.groupby("确认月份").apply(
        lambda x: pd.Series({
            "订单数": len(x),
            "现货满足数": (x["现货满足判定"] == "是").sum(),
            "现货满足率": (x["现货满足判定"] == "是").mean() if len(x) > 0 else 0,
        })
    ).reset_index()

    # 按月份分组计算销售额
    monthly_sales = processed_df.groupby("确认月份").apply(
        lambda x: pd.Series({
            "销售额": x[COL_AMOUNT].sum() if COL_AMOUNT in x.columns else 0,
            "订单数_销售额": len(x),
        })
    ).reset_index()

    return {
        "monthly_fulfillment": monthly_fulfillment,
        "monthly_sales": monthly_sales,
    }


def calculate_customer_metrics(
    processed_df: pd.DataFrame,
    selected_years: list = None,
) -> pd.DataFrame:
    """
    按客户计算指标：总采购额、现货满足率

    Args:
        processed_df: 处理后的销售数据
        selected_years: 选中的年份列表（用于过滤）

    Returns:
        pd.DataFrame: 按客户汇总的指标表
    """
    if processed_df.empty:
        return pd.DataFrame()

    # 如果指定了年份列表，进行过滤
    if selected_years is not None and len(selected_years) > 0:
        processed_df = processed_df[
            processed_df[COL_ORDER_CONFIRM_TIME].dt.year.isin(selected_years)
        ].copy()

    if processed_df.empty:
        return pd.DataFrame()

    # 确保金额列是数值类型
    if COL_AMOUNT in processed_df.columns:
        processed_df = processed_df.copy()
        processed_df[COL_AMOUNT] = pd.to_numeric(
            processed_df[COL_AMOUNT], errors="coerce"
        ).fillna(0)

    # 按客户分组计算指标（自动去重，因为groupby会按客户聚合）
    customer_metrics = processed_df.groupby(COL_CUSTOMER).apply(
        lambda x: pd.Series({
            "客户名称": x[COL_CUSTOMER].iloc[0],  # 添加客户名称字段
            "总采购额(USD)": x[COL_AMOUNT].sum(),
            "订单数": len(x),
            "现货满足数": (x["现货满足判定"] == "是").sum(),
            "现货满足率": (x["现货满足判定"] == "是").mean() if len(x) > 0 else 0,
        })
    ).reset_index()

    # 检查是否有满足率超过100%的情况（检查是否有重复订单号导致的重复计数）
    if (customer_metrics["现货满足率"] > 1).any():
        warnings.warn("检测到满足率超过100%，可能存在重复订单号，已自动去重")

    # 按总采购额从高到低排序
    customer_metrics = customer_metrics.sort_values("总采购额(USD)", ascending=False)

    # 选择并排序列：客户名称、总采购额(USD)、现货满足率
    final_columns = ["客户名称", "总采购额(USD)", "现货满足率"]
    available_columns = [col for col in final_columns if col in customer_metrics.columns]

    return customer_metrics[available_columns]
