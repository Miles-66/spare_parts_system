# -*- coding: utf-8 -*-
"""
阿里云 OSS 数据读取引擎

用于云端部署时从 OSS 读取 Excel 数据文件
"""

import os
import io
from pathlib import Path
import pandas as pd
import oss2
from config import OSS_CONFIG, USE_OSS


class OSSDataEngine:
    """OSS 数据读取引擎"""
    
    _bucket = None
    
    @classmethod
    def get_bucket(cls):
        """获取 OSS Bucket 对象（单例）"""
        if cls._bucket is None:
            access_key_id = OSS_CONFIG.get("access_key_id")
            access_key_secret = OSS_CONFIG.get("access_key_secret")
            bucket_name = OSS_CONFIG.get("bucket_name")
            endpoint = OSS_CONFIG.get("endpoint")
            
            if not access_key_id or not access_key_secret:
                raise ValueError("OSS credentials not configured")
            
            auth = oss2.Auth(access_key_id, access_key_secret)
            cls._bucket = oss2.Bucket(auth, endpoint, bucket_name)
        
        return cls._bucket
    
    @classmethod
    def list_files(cls, prefix: str = "data_source/") -> list:
        """
        列出 OSS 中的文件
        
        Args:
            prefix: 文件前缀
            
        Returns:
            list: 文件路径列表
        """
        if not USE_OSS:
            return []
        
        bucket = cls.get_bucket()
        files = []
        
        for obj in oss2.ObjectIterator(bucket, prefix=prefix):
            files.append(obj.key)
        
        return files
    
    @classmethod
    def read_excel(cls, oss_key: str) -> pd.DataFrame:
        """
        从 OSS 读取 Excel 文件
        
        Args:
            oss_key: OSS 中的文件路径
            
        Returns:
            pd.DataFrame: Excel 数据
        """
        bucket = cls.get_bucket()
        
        # 读取文件内容
        file_content = bucket.get_object(oss_key).read()
        
        # 转换为 DataFrame
        df = pd.read_excel(io.BytesIO(file_content))
        
        return df
    
    @classmethod
    def get_file_url(cls, oss_key: str) -> str:
        """
        获取文件的公开访问 URL（需要 Bucket 设置为公共读）
        
        Args:
            oss_key: OSS 中的文件路径
            
        Returns:
            str: 文件 URL
        """
        bucket = cls.get_bucket()
        return bucket.sign_url('GET', oss_key, 3600)  # 1小时有效期


def load_data_from_oss(file_path: str) -> pd.DataFrame:
    """
    从 OSS 读取数据文件的便捷函数
    
    Args:
        file_path: OSS 中的文件路径（如 "data_source/sales/xxx.xlsx"）
        
    Returns:
        pd.DataFrame: 数据
    """
    if not USE_OSS:
        # 本地模式：从本地读取
        local_path = Path("D:/spare_parts_system") / file_path
        return pd.read_excel(local_path)
    
    # 云端模式：从 OSS 读取
    return OSSDataEngine.read_excel(file_path)


def get_oss_file_list(folder: str = "data_source") -> list:
    """
    获取 OSS 指定文件夹中的所有文件
    
    Args:
        folder: 文件夹路径
        
    Returns:
        list: 文件路径列表
    """
    if not USE_OSS:
        # 本地模式
        local_path = Path("D:/spare_parts_system") / folder
        if not local_path.exists():
            return []
        
        files = []
        for ext in ["*.xlsx", "*.xls"]:
            files.extend([str(f.relative_to(Path("D:/spare_parts_system"))).replace("\\", "/") 
                        for f in local_path.rglob(ext)])
        return files
    
    # 云端模式
    return OSSDataEngine.list_files(prefix=folder + "/")
