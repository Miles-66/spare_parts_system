# -*- coding: utf-8 -*-
"""
配置中心：存放列名映射（Column Mapping）

设计原则：配置驱动，严禁硬编码。
当Excel表头变动时，只需在此处修改对应映射，代码中引用变量即可。
"""

import os
from pathlib import Path

# ==================== 路径配置 ====================
# 项目根目录
PROJECT_ROOT = Path(__file__).parent

# 数据源根目录
DATA_SOURCE_ROOT = PROJECT_ROOT / "data_source"

# 销售数据目录
SALES_DATA_DIR = DATA_SOURCE_ROOT / "sales"

# 库存数据目录
INVENTORY_DATA_DIR = DATA_SOURCE_ROOT / "inventory"

# 采购数据目录
PROCUREMENT_DATA_DIR = DATA_SOURCE_ROOT / "procurement"

# 物流数据目录
LOGISTICS_DATA_DIR = DATA_SOURCE_ROOT / "logistics"

# 预测缓存目录
FORECAST_CACHE_DIR = PROJECT_ROOT / "cache" / "forecast"

# ==================== 阿里云 OSS 配置 ====================
# 用于云端部署时从 OSS 读取数据
# 本地运行时使用上面的本地路径
import os
import io
import pandas as pd
import oss2

# 尝试从环境变量或 Streamlit secrets 读取 OSS 配置
def get_oss_config(key, default=""):
    """从环境变量或 Streamlit secrets 获取配置"""
    # 首先尝试从环境变量读取
    env_val = os.environ.get(f"OSS_{key.upper()}", None)
    if env_val:
        return env_val
    
    # 然后尝试从 Streamlit secrets 读取
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and st.secrets:
            if 'oss' in st.secrets and key in st.secrets['oss']:
                return st.secrets['oss'][key]
    except:
        pass
    
    return default

# OSS 开关：通过环境变量控制，部署时设置 USE_OSS=true
USE_OSS = get_oss_config("use_oss", "false").lower() == "true"

# OSS 配置
OSS_CONFIG = {
    "access_key_id": get_oss_config("access_key_id", ""),
    "access_key_secret": get_oss_config("access_key_secret", ""),
    "bucket_name": get_oss_config("bucket_name", "xcmg-parts-data"),
    "endpoint": get_oss_config("endpoint", "https://oss-ap-southeast-1.aliyuncs.com"),
    "prefix": "data_source/"  # OSS 中的文件前缀
}

# 调试：打印配置（仅在 Streamlit 环境中）
def debug_oss_config():
    import streamlit as st
    st.write("### OSS 配置调试信息")
    st.write(f"USE_OSS: {USE_OSS}")
    st.write(f"access_key_id: {'已设置' if OSS_CONFIG['access_key_id'] else '未设置'}")
    st.write(f"access_key_secret: {'已设置' if OSS_CONFIG['access_key_secret'] else '未设置'}")
    st.write(f"bucket_name: {OSS_CONFIG['bucket_name']}")
    st.write(f"endpoint: {OSS_CONFIG['endpoint']}")

# OSS Bucket 单例
_oss_bucket = None

def get_oss_bucket():
    """获取 OSS Bucket 对象"""
    import streamlit as st
    global _oss_bucket
    if _oss_bucket is None:
        if not OSS_CONFIG["access_key_id"] or not OSS_CONFIG["access_key_secret"]:
            st.error("OSS credentials 未配置! 请在 Streamlit Cloud secrets 中配置 oss.access_key_id 和 oss.access_key_secret")
            return None
        try:
            auth = oss2.Auth(OSS_CONFIG["access_key_id"], OSS_CONFIG["access_key_secret"])
            _oss_bucket = oss2.Bucket(auth, OSS_CONFIG["endpoint"], OSS_CONFIG["bucket_name"])
            # 测试连接
            _oss_bucket.get_bucket_info()
        except oss2.exceptions.NoSuchBucket:
            st.error(f"Bucket '{OSS_CONFIG['bucket_name']}' 不存在!")
            _oss_bucket = None
            return None
        except oss2.exceptions.AccessDenied:
            st.error(f"AccessKey 无权访问 Bucket '{OSS_CONFIG['bucket_name']}'! 请检查权限设置")
            _oss_bucket = None
            return None
        except oss2.exceptions.InvalidEndpoint:
            st.error(f"Endpoint '{OSS_CONFIG['endpoint']}' 无效! 请检查区域设置")
            _oss_bucket = None
            return None
        except Exception as e:
            st.error(f"OSS 连接失败: {e}")
            _oss_bucket = None
            return None
    return _oss_bucket


def read_excel_from_oss(oss_key: str) -> pd.DataFrame:
    """从 OSS 读取 Excel 文件"""
    bucket = get_oss_bucket()
    file_content = bucket.get_object(oss_key).read()
    return pd.read_excel(io.BytesIO(file_content))


def list_oss_files(prefix: str = "data_source/") -> list:
    """列出 OSS 中的文件"""
    import streamlit as st
    bucket = get_oss_bucket()
    files = []
    try:
        for obj in oss2.ObjectIterator(bucket, prefix=prefix):
            files.append(obj.key)
    except oss2.exceptions.ServerError as e:
        st.error(f"OSS 连接错误: {e}")
        st.error(f"请检查: bucket={OSS_CONFIG['bucket_name']}, endpoint={OSS_CONFIG['endpoint']}")
        return []
    except Exception as e:
        st.error(f"OSS 未知错误: {e}")
        return []
    return files


def get_data_files(data_dir: Path, keyword: str = None) -> list:
    """
    获取数据文件列表（支持本地和 OSS）
    
    Args:
        data_dir: 本地数据目录路径
        keyword: 文件名关键词过滤（可选）
        
    Returns:
        list: 文件路径列表（本地为 Path 对象，OSS 为字符串）
    """
    if not USE_OSS:
        # 本地模式
        if not data_dir.exists():
            return []
        files = []
        for f in data_dir.iterdir():
            if f.name.startswith('~'):
                continue
            if f.is_file() and f.suffix.lower() in ['.xlsx', '.xls', '.csv']:
                if keyword is None or keyword in f.name:
                    files.append(f)
        return sorted(files)
    else:
        # OSS 模式
        # 将本地路径转换为 OSS key 前缀
        folder_name = data_dir.name  # 如 "sales", "inventory" 等
        prefix = f"data_source/{folder_name}/"
        
        bucket = get_oss_bucket()
        files = []
        for obj in oss2.ObjectIterator(bucket, prefix=prefix):
            filename = obj.key.split('/')[-1]
            if filename.startswith('~'):
                continue
            if keyword is None or keyword in filename:
                files.append(obj.key)
        return sorted(files)


def read_excel_file(file_path) -> pd.DataFrame:
    """
    读取 Excel 文件（支持本地和 OSS）
    
    Args:
        file_path: 本地 Path 对象或 OSS key 字符串
        
    Returns:
        pd.DataFrame: Excel 数据
    """
    if not USE_OSS:
        # 本地模式
        return pd.read_excel(file_path)
    else:
        # OSS 模式
        return read_excel_from_oss(file_path)

# ==================== 销售模块列名映射 ====================
# 销售明细表列名映射（根据实际数据调整）
SALES_COL_ORDER_ID = "订单号"  # 订单编号
SALES_COL_PART_NO = "备件号"  # 备件编号（本数据中可能不存在）
SALES_COL_PART_NAME = "备件名称"  # 备件名称（本数据中可能不存在）
SALES_COL_QUANTITY = "数量"  # 销售数量（本数据中可能不存在）
SALES_COL_UNIT_PRICE = "单价"  # 销售单价（本数据中可能不存在）
SALES_COL_AMOUNT = "总金额"  # 销售金额（实际数据中为"总金额"）
SALES_COL_CUSTOMER = "客户"  # 客户名称（实际数据中为"客户"）
SALES_COL_REGION = "区域"  # 销售区域（本数据中可能不存在）
SALES_COL_PROVINCE = "省/州"  # 省份（实际数据中为"省/州"）
SALES_COL_CITY = "城市"  # 城市（本数据中可能不存在）
SALES_COL_DEALER = "经销商"  # 经销商（本数据中可能不存在）
SALES_COL_SALES_DATE = "创建时间"  # 销售日期（实际数据中为"创建时间"）
SALES_COL_OEM = "主机厂"  # 主机厂（本数据中可能不存在）
SALES_COL_SERVICE_LEVEL = "服务水平"  # 服务水平（本数据中可能不存在）

# 销售明细表默认列名列表（只包含实际存在的列）
SALES_DEFAULT_COLUMNS = [
    SALES_COL_ORDER_ID,
    SALES_COL_CUSTOMER,
    SALES_COL_AMOUNT,
    SALES_COL_PROVINCE,
    SALES_COL_SALES_DATE,
]

# ==================== 发货表列名映射 ====================
# 备件发车明细表列名映射（根据实际数据调整）
SHIPPING_COL_ORDER_ID = "订单号"  # 订单号（关联主键）
SHIPPING_COL_PART_NO = "备件号"  # 备件号（本数据中可能不存在）
SHIPPING_COL_SHIPPING_TIME = "SAP发货时间"  # SAP发货时间（实际数据中为"SAP发货时间"）
SHIPPING_COL_CONFIRM_TIME = "确认时间"  # 确认时间（实际数据中为"确认时间"）
SHIPPING_COL_STOCK_FULFILL = "是否现货满足"  # 是否现货满足（本数据中可能不存在）

# 发货表额外列（实际数据中存在但未在上方映射的列）
SHIPPING_COL_SAP_STATUS = "SAP发货状态"  # SAP发货状态（用于判断是否现货满足）
SHIPPING_COL_APPLICATION_NO = "发车申请单号"  # 发车申请单号

# 发货表默认列名列表（只包含实际存在的列）
SHIPPING_DEFAULT_COLUMNS = [
    SHIPPING_COL_ORDER_ID,
    SHIPPING_COL_SHIPPING_TIME,
    SHIPPING_COL_SAP_STATUS,
]

# ==================== 缓存配置 ====================
# 缓存过期时间（秒）
CACHE_TTL = 3600

# ==================== 支持的文件格式 ====================
# 支持的Excel格式
EXCEL_EXTENSIONS = [".xlsx", ".xls"]

# 支持的CSV格式
CSV_EXTENSIONS = [".csv"]

# 所有支持的数据格式
SUPPORTED_EXTENSIONS = EXCEL_EXTENSIONS + CSV_EXTENSIONS

# ==================== 文件名关键词配置 ====================
# 智能表名识别：使用关键词锁定目标表
# 订单表：识别包含以下关键词的文件
FILE_KEYWORD_ORDERS = "miles可用的子公司备件订单"

# 发货表：识别包含以下关键词的文件
FILE_KEYWORD_SHIPPING = "miles可用的子公司备件发车申请"


def get_sales_columns_dict() -> dict:
    """
    获取销售模块列名字典

    Returns:
        dict: 列名映射字典
    """
    return {
        "order_id": SALES_COL_ORDER_ID,
        "part_no": SALES_COL_PART_NO,
        "part_name": SALES_COL_PART_NAME,
        "quantity": SALES_COL_QUANTITY,
        "unit_price": SALES_COL_UNIT_PRICE,
        "amount": SALES_COL_AMOUNT,
        "customer": SALES_COL_CUSTOMER,
        "region": SALES_COL_REGION,
        "province": SALES_COL_PROVINCE,
        "city": SALES_COL_CITY,
        "dealer": SALES_COL_DEALER,
        "sales_date": SALES_COL_SALES_DATE,
        "oem": SALES_COL_OEM,
        "service_level": SALES_COL_SERVICE_LEVEL,
    }


def get_shipping_columns_dict() -> dict:
    """
    获取发货表列名字典

    Returns:
        dict: 列名映射字典
    """
    return {
        "order_id": SHIPPING_COL_ORDER_ID,
        "part_no": SHIPPING_COL_PART_NO,
        "shipping_time": SHIPPING_COL_SHIPPING_TIME,
        "confirm_time": SHIPPING_COL_CONFIRM_TIME,
        "stock_fulfill": SHIPPING_COL_STOCK_FULFILL,
        "sap_status": SHIPPING_COL_SAP_STATUS,
        "application_no": SHIPPING_COL_APPLICATION_NO,
    }


# ==================== 标准化后的列名常量 ====================
# 注意：这些是数据经过normalize_columns处理后的列名
# 代码中应使用这些常量来引用列

# 销售表标准化列名
COL_ORDER_ID = "order_id"
COL_CUSTOMER = "customer"
COL_AMOUNT = "amount"
COL_PROVINCE = "province"
COL_SALES_DATE = "sales_date"

# 发货表标准化列名
COL_SHIPPING_TIME = "shipping_time"
COL_CONFIRM_TIME = "confirm_time"
COL_STOCK_FULFILL = "stock_fulfill"
COL_SAP_STATUS = "sap_status"

# ==================== 采购模块列名映射 ====================
# 进出口备件需求单明细表列名映射
PROCUREMENT_COL_DEMAND_NO = "需求单号"  # 需求单号
PROCUREMENT_COL_PART_NO = "物料号"  # 物料号
PROCUREMENT_COL_PART_DESC = "物料描述"  # 物料描述
PROCUREMENT_COL_OEM = "主机厂"  # 主机厂
PROCUREMENT_COL_QUANTITY = "数量"  # 采购数量
PROCUREMENT_COL_UNIT_PRICE = "PMS价格"  # PMS价格（单价）
PROCUREMENT_COL_SUBMIT_TIME = "SAP提交时间"  # SAP提交时间
PROCUREMENT_COL_CURRENCY = "币种"  # 币种
PROCUREMENT_COL_STATUS = "状态"  # 订单状态

# 采购表默认列名列表
PROCUREMENT_DEFAULT_COLUMNS = [
    PROCUREMENT_COL_DEMAND_NO,
    PROCUREMENT_COL_PART_NO,
    PROCUREMENT_COL_PART_DESC,
    PROCUREMENT_COL_OEM,
    PROCUREMENT_COL_QUANTITY,
    PROCUREMENT_COL_UNIT_PRICE,
    PROCUREMENT_COL_SUBMIT_TIME,
]

# 采购文件名关键词
FILE_KEYWORD_PROCUREMENT = "miles采购表"

# 采购表标准化列名
COL_DEMAND_NO = "demand_no"
COL_PART_NO = "part_no"
COL_PART_DESC = "part_desc"
COL_OEM = "oem"
COL_QUANTITY = "quantity"
COL_UNIT_PRICE = "unit_price"
COL_SUBMIT_TIME = "submit_time"
COL_TOTAL_PRICE = "total_price"  # 计算列：数量 × 单价


def get_procurement_columns_dict() -> dict:
    """
    获取采购模块列名字典

    Returns:
        dict: 列名映射字典
    """
    return {
        "demand_no": PROCUREMENT_COL_DEMAND_NO,
        "part_no": PROCUREMENT_COL_PART_NO,
        "part_desc": PROCUREMENT_COL_PART_DESC,
        "oem": PROCUREMENT_COL_OEM,
        "quantity": PROCUREMENT_COL_QUANTITY,
        "unit_price": PROCUREMENT_COL_UNIT_PRICE,
        "submit_time": PROCUREMENT_COL_SUBMIT_TIME,
        "currency": PROCUREMENT_COL_CURRENCY,
        "status": PROCUREMENT_COL_STATUS,
    }


# ==================== 采购模块列别名映射（兼容中英文） ====================
# 【架构师指令】建立统一映射表，兼容各种列名变体
# 无论原始数据是中文还是英文，都能正确识别

PROCUREMENT_COL_ALIASES = {
    # 需求单号别名
    "demand_no": [
        "demand_no", "需求单号", "单号", "订单号", 
        "application_no", "申请单号"
    ],
    
    # 物料号别名
    "part_no": [
        "part_no", "物料号", "物料编号", "备件号", 
        "material_no", "material"
    ],
    
    # 物料描述别名
    "part_desc": [
        "part_desc", "物料描述", "物料名称", "备件名称", 
        "description", "名称", "品名"
    ],
    
    # 主机厂别名（兼容中英文）
    "oem": [
        "oem", "主机厂", "OEM厂", "OEM", 
        "品牌", "manufacturer"
    ],
    
    # 数量别名
    "quantity": [
        "quantity", "数量", "qty", "QTY", 
        "采购数量", "order_qty"
    ],
    
    # 单价别名（兼容 PMS价格CNY）
    "unit_price": [
        "pms价格(cny)", "pms价格", "PMS价格", "PMS价格(CNY)", 
        "unit_price", "单价", "price", "Price", 
        "采购单价", "PMS Price"
    ],
    
    # SAP提交时间别名
    "submit_time": [
        "submit_time", "SAP提交时间", "提交时间", 
        "creation_time", "创建时间", "下单时间"
    ],
    
    # 币种别名
    "currency": [
        "currency", "币种", "currency_type"
    ],
    
    # 状态别名
    "status": [
        "status", "状态", "订单状态"
    ],
}


def find_column_by_alias(df_columns: list, standard_name: str) -> str:
    """
    【核心函数】通过别名映射查找实际列名

    Args:
        df_columns: DataFrame的实际列名列表
        standard_name: 标准列名（如 'quantity', 'unit_price'）

    Returns:
        str: 匹配到的实际列名，未找到返回None
    """
    # 获取该标准列名的所有别名
    aliases = PROCUREMENT_COL_ALIASES.get(standard_name, [])
    
    # 遍历所有别名，尝试在DataFrame列中找到匹配
    for alias in aliases:
        for col in df_columns:
            # 忽略大小写匹配
            if col.strip().lower() == alias.strip().lower():
                return col
    
    return None


def get_procurement_columns_with_aliases() -> dict:
    """
    【统一接口】获取采购模块完整列名映射（含别名）

    Returns:
        dict: 标准列名 -> 实际列名（如果已标准化）
              标准列名 -> 别名列表（用于匹配）
    """
    return {
        "demand_no": PROCUREMENT_COL_DEMAND_NO,
        "part_no": PROCUREMENT_COL_PART_NO,
        "part_desc": PROCUREMENT_COL_PART_DESC,
        "oem": PROCUREMENT_COL_OEM,
        "quantity": PROCUREMENT_COL_QUANTITY,
        "unit_price": PROCUREMENT_COL_UNIT_PRICE,
        "submit_time": PROCUREMENT_COL_SUBMIT_TIME,
        "currency": PROCUREMENT_COL_CURRENCY,
        "status": PROCUREMENT_COL_STATUS,
        "_aliases": PROCUREMENT_COL_ALIASES,  # 保留别名映射供外部使用
    }


# ==================== 库存追踪模块配置 ====================
# 排除的SAP订单号（退货单/取消订单等不计入在途）
# 从JSON配置文件加载
import json

def get_excluded_sap_orders() -> set:
    """从JSON文件加载排除的SAP订单号集合"""
    config_path = PROJECT_ROOT / "config" / "excluded_orders.json"
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            orders = json.load(f)
        return set(str(o).strip() for o in orders)
    except Exception as e:
        print(f"Warning: Failed to load excluded orders from {config_path}: {e}")
        return set()


# 保留向后兼容的默认值（如果JSON文件不存在）
EXCLUDED_SAP_ORDERS = get_excluded_sap_orders()
