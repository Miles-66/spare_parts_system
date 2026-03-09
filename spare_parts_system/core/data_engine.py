# -*- coding: utf-8 -*-
"""
核心引擎层：数据引擎（Data Engine）

负责多文件夹扫描、自动合并与去重、缓存管理。

设计原则：
1. 缓存优先机制：使用 @st.cache_data 装饰器，只有文件变动时才重新读取
2. 防御性报错：缺失文件时返回空DataFrame并在界面上提示
3. 配置驱动：所有列名引用 config.py 中定义的变量
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import warnings

import pandas as pd
import streamlit as st

from config import (
    PROJECT_ROOT,
    SALES_DATA_DIR,
    PROCUREMENT_DATA_DIR,
    SUPPORTED_EXTENSIONS,
    FILE_KEYWORD_ORDERS,
    FILE_KEYWORD_SHIPPING,
    FILE_KEYWORD_PROCUREMENT,
    get_sales_columns_dict,
    get_shipping_columns_dict,
    get_procurement_columns_dict,
    SALES_COL_ORDER_ID,
    SALES_COL_PART_NO,
    SALES_COL_QUANTITY,
    SALES_COL_AMOUNT,
    SALES_COL_CUSTOMER,
    SALES_COL_REGION,
    SALES_COL_PROVINCE,
    SALES_COL_CITY,
    SALES_COL_DEALER,
    SALES_COL_SALES_DATE,
    SALES_COL_OEM,
    SALES_COL_SERVICE_LEVEL,
    SHIPPING_COL_ORDER_ID,
    SHIPPING_COL_PART_NO,
    SHIPPING_COL_SHIPPING_TIME,
    SHIPPING_COL_CONFIRM_TIME,
    SHIPPING_COL_STOCK_FULFILL,
    SHIPPING_COL_SAP_STATUS,
    SHIPPING_COL_APPLICATION_NO,
    PROCUREMENT_COL_DEMAND_NO,
    PROCUREMENT_COL_PART_NO,
    PROCUREMENT_COL_PART_DESC,
    PROCUREMENT_COL_OEM,
    PROCUREMENT_COL_QUANTITY,
    PROCUREMENT_COL_UNIT_PRICE,
    PROCUREMENT_COL_SUBMIT_TIME,
    PROCUREMENT_COL_CURRENCY,
    PROCUREMENT_COL_STATUS,
    CACHE_TTL,
    USE_OSS,
    read_excel_from_oss,
    list_oss_files,
)


class DataEngine:
    """
    数据引擎类

    负责数据的扫描、读取、合并、去重和缓存管理。
    """

    def __init__(self):
        """
        初始化数据引擎
        """
        self.sales_columns = get_sales_columns_dict()
        self.shipping_columns = get_shipping_columns_dict()

    def get_all_data_files(self, data_dir: Path) -> List:
        """
        获取指定目录下所有支持格式的数据文件（支持本地和OSS）

        Args:
            data_dir: 数据目录路径

        Returns:
            List: 数据文件路径列表（本地为Path对象，OSS为字符串key）
        """
        # OSS模式
        if USE_OSS:
            folder_name = data_dir.name
            prefix = f"data_source/{folder_name}/"
            files = list_oss_files(prefix)
            return files
        
        # 本地模式
        if not data_dir.exists():
            return []

        data_files = []
        for file_path in data_dir.iterdir():
            # 过滤Excel临时文件（以~$开头）
            if file_path.name.startswith('~$'):
                continue
            
            if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                data_files.append(file_path)

        # 按文件名排序，确保读取顺序一致
        data_files.sort(key=lambda x: x.name)
        return data_files

    def match_file_by_keyword(self, file_name: str, keyword: str) -> bool:
        """
        智能表名识别：使用关键词匹配文件名

        Args:
            file_name: 文件名
            keyword: 关键词

        Returns:
            bool: 是否匹配
        """
        # 忽略大小写匹配
        file_name_lower = file_name.lower()
        keyword_lower = keyword.lower()

        # 使用in关键词进行匹配，忽略数字后缀差异
        if keyword_lower in file_name_lower:
            return True

        return False

    def get_files_by_keyword(self, data_dir: Path, keyword: str) -> List[Path]:
        """
        根据关键词获取匹配的文件列表

        Args:
            data_dir: 数据目录路径
            keyword: 匹配关键词

        Returns:
            List[Path]: 匹配的文件路径列表
        """
        all_files = self.get_all_data_files(data_dir)

        matched_files = []
        for file_path in all_files:
            if self.match_file_by_keyword(file_path.name, keyword):
                matched_files.append(file_path)

        return matched_files

    def get_orders_files(self, data_dir: Path) -> List[Path]:
        """
        获取订单表文件列表

        识别包含 FILE_KEYWORD_ORDERS 关键词的文件

        Args:
            data_dir: 数据目录路径

        Returns:
            List[Path]: 订单表文件路径列表
        """
        return self.get_files_by_keyword(data_dir, FILE_KEYWORD_ORDERS)

    def get_shipping_files(self, data_dir: Path) -> List[Path]:
        """
        获取发货表文件列表

        识别包含 FILE_KEYWORD_SHIPPING 关键词的文件

        Args:
            data_dir: 数据目录路径

        Returns:
            List[Path]: 发货表文件路径列表
        """
        return self.get_files_by_keyword(data_dir, FILE_KEYWORD_SHIPPING)

    def get_file_info(self, file_path: Path) -> Dict:
        """
        获取文件信息

        Args:
            file_path: 文件路径

        Returns:
            Dict: 文件信息字典
        """
        return {
            "path": str(file_path),
            "name": file_path.name,
            "size": file_path.stat().st_size,
            "modified_time": file_path.stat().st_mtime,
            "extension": file_path.suffix.lower(),
        }

    def read_excel_file(self, file_path) -> pd.DataFrame:
        """
        读取Excel文件（支持本地和OSS）

        Args:
            file_path: Excel文件路径（本地为Path对象，OSS为字符串key）

        Returns:
            pd.DataFrame: 读取的数据
        """
        # OSS模式：从OSS读取
        if USE_OSS and isinstance(file_path, str):
            try:
                df = read_excel_from_oss(file_path)
                return df
            except Exception as e:
                raise ValueError(f"无法从OSS读取Excel文件 {file_path}：{str(e)}")
        
        # 本地模式：从本地读取
        try:
            # 尝试读取Excel文件
            df = pd.read_excel(file_path, engine="openpyxl")
            return df
        except Exception as e:
            # 如果openpyxl失败，尝试xlrd
            try:
                df = pd.read_excel(file_path, engine="xlrd")
                return df
            except Exception as e2:
                raise ValueError(f"无法读取Excel文件 {file_path.name if hasattr(file_path, 'name') else file_path}：{str(e2)}")

    def read_csv_file(self, file_path: Path) -> pd.DataFrame:
        """
        读取CSV文件

        Args:
            file_path: CSV文件路径

        Returns:
            pd.DataFrame: 读取的数据
        """
        try:
            # 尝试多种编码格式
            for encoding in ["utf-8", "gbk", "gb2312", "utf-8-sig"]:
                try:
                    df = pd.read_csv(file_path, encoding=encoding)
                    return df
                except UnicodeDecodeError:
                    continue

            # 如果所有编码都失败，使用error_bad_lines忽略错误行
            df = pd.read_csv(file_path, encoding="utf-8", on_bad_lines="skip")
            return df
        except Exception as e:
            raise ValueError(f"无法读取CSV文件 {file_path.name}：{str(e)}")

    def read_data_file(self, file_path: Path) -> pd.DataFrame:
        """
        根据文件格式读取数据

        Args:
            file_path: 数据文件路径

        Returns:
            pd.DataFrame: 读取的数据
        """
        extension = file_path.suffix.lower()

        if extension in [".xlsx", ".xls"]:
            return self.read_excel_file(file_path)
        elif extension == ".csv":
            return self.read_csv_file(file_path)
        else:
            raise ValueError(f"不支持的文件格式：{extension}")

    def normalize_columns(self, df: pd.DataFrame, columns_map: Dict[str, str]) -> pd.DataFrame:
        """
        标准化列名：将实际列名映射为标准列名

        Args:
            df: 原始数据框
            columns_map: 列名映射字典

        Returns:
            pd.DataFrame: 标准化后的数据框
        """
        # 创建反向映射：实际列名 -> 标准列名
        reverse_map = {v: k for k, v in columns_map.items()}

        # 重命名列
        rename_dict = {}
        for col in df.columns:
            col_stripped = col.strip()
            if col_stripped in reverse_map:
                rename_dict[col] = reverse_map[col_stripped]
            elif col in reverse_map:
                rename_dict[col] = reverse_map[col]

        if rename_dict:
            df = df.rename(columns=rename_dict)

        return df

    def merge_dataframes(
        self,
        dataframes: List[pd.DataFrame],
        source_info: Optional[List[Dict]] = None,
    ) -> pd.DataFrame:
        """
        合并多个数据框

        Args:
            dataframes: 数据框列表
            source_info: 数据来源信息列表

        Returns:
            pd.DataFrame: 合并后的数据框
        """
        if not dataframes:
            return pd.DataFrame()

        if len(dataframes) == 1:
            df = dataframes[0].copy()
            if source_info and len(source_info) > 0:
                df["_source_file"] = source_info[0].get("name", "unknown")
            return df

        # 添加来源信息
        dfs_with_source = []
        for i, df in enumerate(dataframes):
            df_copy = df.copy()
            if source_info and i < len(source_info):
                df_copy["_source_file"] = source_info[i].get("name", "unknown")
            else:
                df_copy["_source_file"] = f"source_{i}"
            dfs_with_source.append(df_copy)

        # 合并数据
        merged_df = pd.concat(dfs_with_source, ignore_index=True)
        return merged_df

    def deduplicate_data(
        self,
        df: pd.DataFrame,
        key_columns: List[str],
        keep: str = "first",
    ) -> pd.DataFrame:
        """
        数据去重

        Args:
            df: 原始数据框
            key_columns: 用于去重的关键列
            keep: 保留策略：'first'保留第一条，'last'保留最后一条，False删除所有重复

        Returns:
            pd.DataFrame: 去重后的数据框
        """
        if df.empty or not key_columns:
            return df.copy()

        # 检查关键列是否存在
        missing_columns = [col for col in key_columns if col not in df.columns]
        if missing_columns:
            warnings.warn(f"关键列不存在：{missing_columns}")
            return df.copy()

        # 执行去重
        original_count = len(df)
        df_dedup = df.drop_duplicates(subset=key_columns, keep=keep)
        deduplicated_count = original_count - len(df_dedup)

        if deduplicated_count > 0:
            print(f"去重完成：移除 {deduplicated_count} 条重复记录")

        return df_dedup


# ==================== 销售数据专用函数 ====================


def load_orders_data_with_cache() -> Tuple[pd.DataFrame, Dict]:
    """
    读取订单表数据（带缓存，智能识别订单表）

    使用 @st.cache_data 装饰器实现缓存机制。
    识别包含 FILE_KEYWORD_ORDERS 关键词的文件作为订单表。

    Returns:
        Tuple[pd.DataFrame, Dict]: (订单数据DataFrame, 数据源信息字典)
    """
    engine = DataEngine()
    sales_dir = Path(SALES_DATA_DIR)

    # 使用关键词识别订单表
    order_files = engine.get_orders_files(sales_dir)

    if not order_files:
        return pd.DataFrame(), {
            "file_count": 0,
            "files": [],
            "status": "warning",
            "message": f"未找到订单表文件，请检查文件名是否包含关键词：{FILE_KEYWORD_ORDERS}",
        }

    # 读取并处理每个订单文件
    dataframes = []
    file_info_list = []

    for file_path in order_files:
        try:
            df = engine.read_data_file(file_path)
            if not df.empty:
                # 标准化列名
                df = engine.normalize_columns(df, engine.sales_columns)
                dataframes.append(df)
                file_info_list.append(engine.get_file_info(file_path))
        except Exception as e:
            warnings.warn(f"读取订单文件 {file_path.name} 失败：{str(e)}")

    if not dataframes:
        return pd.DataFrame(), {
            "file_count": len(order_files),
            "files": file_info_list,
            "status": "warning",
            "message": "无法读取任何订单数据文件，请检查文件格式是否正确",
        }

    # 合并数据
    merged_df = engine.merge_dataframes(dataframes, file_info_list)

    # 去重（使用订单号和备件号作为关键列）
    deduplicated_df = engine.deduplicate_data(
        merged_df,
        key_columns=[SALES_COL_ORDER_ID, SALES_COL_PART_NO],
        keep="first",
    )

    # 确保日期列是datetime类型
    if SALES_COL_SALES_DATE in deduplicated_df.columns:
        deduplicated_df[SALES_COL_SALES_DATE] = pd.to_datetime(
            deduplicated_df[SALES_COL_SALES_DATE], errors="coerce"
        )

    # 确保数值列是数值类型
    numeric_columns = [SALES_COL_QUANTITY, SALES_COL_AMOUNT]
    for col in numeric_columns:
        if col in deduplicated_df.columns:
            deduplicated_df[col] = pd.to_numeric(deduplicated_df[col], errors="coerce").fillna(0)

    return deduplicated_df, {
        "file_count": len(order_files),
        "files": [info["name"] for info in file_info_list],
        "total_records": len(deduplicated_df),
        "status": "success",
        "message": f"成功读取 {len(file_info_list)} 个订单文件，共 {len(deduplicated_df)} 条记录",
    }


def load_shipping_data_with_cache() -> Tuple[pd.DataFrame, Dict]:
    """
    读取发货表数据（带缓存，智能识别发货表）

    使用 @st.cache_data 装饰器实现缓存机制。
    识别包含 FILE_KEYWORD_SHIPPING 关键词的文件作为发货表。

    Returns:
        Tuple[pd.DataFrame, Dict]: (发货数据DataFrame, 数据源信息字典)
    """
    engine = DataEngine()
    sales_dir = Path(SALES_DATA_DIR)

    # 使用关键词识别发货表
    shipping_files = engine.get_shipping_files(sales_dir)

    if not shipping_files:
        return pd.DataFrame(), {
            "file_count": 0,
            "files": [],
            "status": "warning",
            "message": f"未找到发货表文件，请检查文件名是否包含关键词：{FILE_KEYWORD_SHIPPING}",
        }

    # 读取并处理每个发货文件
    dataframes = []
    file_info_list = []

    for file_path in shipping_files:
        try:
            df = engine.read_data_file(file_path)
            if not df.empty:
                # 标准化列名
                df = engine.normalize_columns(df, engine.shipping_columns)
                dataframes.append(df)
                file_info_list.append(engine.get_file_info(file_path))
        except Exception as e:
            warnings.warn(f"读取发货文件 {file_path.name} 失败：{str(e)}")

    if not dataframes:
        return pd.DataFrame(), {
            "file_count": len(shipping_files),
            "files": file_info_list,
            "status": "warning",
            "message": "无法读取任何发货数据文件，请检查文件格式是否正确",
        }

    # 合并数据
    merged_df = engine.merge_dataframes(dataframes, file_info_list)

    # 去重（使用订单号和备件号作为关键列）
    deduplicated_df = engine.deduplicate_data(
        merged_df,
        key_columns=[SHIPPING_COL_ORDER_ID, SHIPPING_COL_PART_NO],
        keep="first",
    )

    # 确保日期时间列是datetime类型
    datetime_columns = [SHIPPING_COL_SHIPPING_TIME, SHIPPING_COL_CONFIRM_TIME]
    for col in datetime_columns:
        if col in deduplicated_df.columns:
            deduplicated_df[col] = pd.to_datetime(deduplicated_df[col], errors="coerce")

    return deduplicated_df, {
        "file_count": len(shipping_files),
        "files": [info["name"] for info in file_info_list],
        "total_records": len(deduplicated_df),
        "status": "success",
        "message": f"成功读取 {len(file_info_list)} 个发货文件，共 {len(deduplicated_df)} 条记录",
    }


def load_sales_data_with_cache() -> Tuple[pd.DataFrame, Dict]:
    """
    读取销售数据（带缓存）

    使用 @st.cache_data 装饰器实现缓存机制，
    只有当 data_source/sales/ 文件夹内的文件发生变动时才触发重新读取。

    Returns:
        Tuple[pd.DataFrame, Dict]: (销售数据DataFrame, 数据源信息字典)
    """
    # 调用订单数据加载函数（向后兼容）
    return load_orders_data_with_cache()


def get_sales_data_summary() -> Dict:
    """
    获取销售数据摘要信息

    Returns:
        Dict: 数据摘要信息
    """
    engine = DataEngine()
    sales_dir = Path(SALES_DATA_DIR)

    # 检查文件夹是否存在
    if not sales_dir.exists():
        return {
            "exists": False,
            "file_count": 0,
            "status": "error",
            "message": f"销售数据文件夹不存在：{sales_dir}",
        }

    # 获取文件列表
    data_files = engine.get_all_data_files(sales_dir)

    # 获取文件夹修改时间
    folder_mtime = sales_dir.stat().st_mtime if sales_dir.exists() else None

    return {
        "exists": True,
        "file_count": len(data_files),
        "folder_path": str(sales_dir),
        "last_modified": folder_mtime,
        "files": [engine.get_file_info(f) for f in data_files],
        "status": "ready",
        "message": f"销售数据文件夹已就绪，包含 {len(data_files)} 个数据文件",
    }


# ==================== 通用数据加载函数 ====================


def load_generic_data(
    data_dir: Path,
    columns_map: Dict[str, str],
    key_columns: List[str],
) -> Tuple[pd.DataFrame, Dict]:
    """
    通用数据加载函数

    Args:
        data_dir: 数据目录路径
        columns_map: 列名映射字典
        key_columns: 用于去重的关键列

    Returns:
        Tuple[pd.DataFrame, Dict]: (数据DataFrame, 数据源信息字典)
    """
    engine = DataEngine()

    # 获取所有数据文件
    data_files = engine.get_all_data_files(data_dir)

    if not data_files:
        return pd.DataFrame(), {
            "file_count": 0,
            "files": [],
            "status": "warning",
            "message": f"检测到数据文件夹为空：{data_dir}",
        }

    # 读取并处理每个文件
    dataframes = []
    file_info_list = []

    for file_path in data_files:
        try:
            df = engine.read_data_file(file_path)
            if not df.empty:
                # 标准化列名
                df = engine.normalize_columns(df, columns_map)
                dataframes.append(df)
                file_info_list.append(engine.get_file_info(file_path))
        except Exception as e:
            warnings.warn(f"读取文件 {file_path.name} 失败：{str(e)}")

    if not dataframes:
        return pd.DataFrame(), {
            "file_count": len(data_files),
            "files": file_info_list,
            "status": "warning",
            "message": "无法读取任何数据文件，请检查文件格式是否正确",
        }

    # 合并数据
    merged_df = engine.merge_dataframes(dataframes, file_info_list)

    # 去重
    deduplicated_df = engine.deduplicate_data(
        merged_df,
        key_columns=key_columns,
        keep="first",
    )

    return deduplicated_df, {
        "file_count": len(data_files),
        "files": [info["name"] for info in file_info_list],
        "total_records": len(deduplicated_df),
        "status": "success",
        "message": f"成功读取 {len(file_info_list)} 个数据文件，共 {len(deduplicated_df)} 条记录",
    }


def check_data_folders() -> Dict[str, Dict]:
    """
    检查所有数据文件夹状态（支持本地和OSS模式）

    Returns:
        Dict[str, Dict]: 各数据文件夹状态字典
    """
    from config import USE_OSS
    
    folders = {
        "sales": SALES_DATA_DIR,
    }

    status = {}
    for name, path in folders.items():
        engine = DataEngine()
        files = engine.get_all_data_files(path)

        if USE_OSS:
            # OSS模式：检查OSS文件
            if len(files) > 0:
                status[name] = {
                    "exists": True,
                    "file_count": len(files),
                    "status": "ready",
                    "message": f"OSS数据就绪，包含 {len(files)} 个文件",
                }
            else:
                status[name] = {
                    "exists": False,
                    "file_count": 0,
                    "status": "error",
                    "message": "OSS数据文件夹为空或无法连接",
                }
        else:
            # 本地模式：检查本地路径
            if not path.exists():
                status[name] = {
                    "exists": False,
                    "file_count": 0,
                    "status": "error",
                    "message": f"数据文件夹不存在：{path}",
                }
            elif len(files) == 0:
                status[name] = {
                    "exists": True,
                    "file_count": 0,
                    "status": "warning",
                    "message": f"数据文件夹为空：{path}",
                }
            else:
                status[name] = {
                    "exists": True,
                    "file_count": len(files),
                    "status": "ready",
                    "message": f"数据文件夹已就绪，包含 {len(files)} 个文件",
                }

    return status


# ==================== 缓存数据重新加载函数 ====================


def reload_sales_data() -> Tuple[pd.DataFrame, Dict]:
    """
    强制重新加载销售数据（清除缓存后重新读取）

    Returns:
        Tuple[pd.DataFrame, Dict]: (销售数据DataFrame, 数据源信息字典)
    """
    # 清除相关缓存
    st.cache_data.clear()

    # 重新加载数据
    return load_sales_data_with_cache()


# ==================== 采购数据加载函数 ====================


@st.cache_data(ttl=CACHE_TTL)
def load_procurement_data_with_cache() -> Tuple[pd.DataFrame, Dict]:
    """
    加载采购数据（带缓存）

    Returns:
        tuple: (采购DataFrame, info_dict)
    """
    from config import PROCUREMENT_DEFAULT_COLUMNS

    engine = DataEngine()
    sales_dir = Path(PROCUREMENT_DATA_DIR)

    # 读取包含"miles进出口备件需求单明细"关键词的文件
    procurement_files = engine.get_files_by_keyword(sales_dir, FILE_KEYWORD_PROCUREMENT)

    if not procurement_files:
        return pd.DataFrame(), {
            "file_count": 0,
            "files": [],
            "status": "warning",
            "message": "未找到采购需求单文件",
        }

    # 读取并处理文件
    dataframes = []
    file_info_list = []

    for file_path in procurement_files:
        try:
            df = engine.read_data_file(file_path)
            if not df.empty:
                # 跳过前3列系统元数据
                if len(df.columns) > 3:
                    df = df.iloc[:, 3:].copy()
                dataframes.append(df)
                file_info_list.append(engine.get_file_info(file_path))
        except Exception as e:
            import warnings
            warnings.warn(f"读取文件 {file_path.name} 失败：{str(e)}")

    if not dataframes:
        return pd.DataFrame(), {
            "file_count": len(procurement_files),
            "files": file_info_list,
            "status": "warning",
            "message": "无法读取采购需求单文件",
        }

    # 合并数据
    procurement_df = engine.merge_dataframes(dataframes, file_info_list)

    # 标准化列名
    columns_map = get_procurement_columns_dict()
    procurement_df = engine.normalize_columns(procurement_df, columns_map)

    return procurement_df, {
        "file_count": len(procurement_files),
        "files": [info["name"] for info in file_info_list],
        "total_records": len(procurement_df),
        "status": "success",
        "message": f"成功读取 {len(file_info_list)} 个采购需求单文件，共 {len(procurement_df)} 条记录",
    }
