# -*- coding: utf-8 -*-
import pandas as pd
import sys

# 读取物流成本表
file_path = r"D:\spare_parts_system\data_source\logistics\物流成本表 2026-2-19 10-48-16.xlsx"

# 跳过前3列元数据
df = pd.read_excel(file_path, header=None)
print(f"原始Shape: {df.shape}")
print(f"\n前5行前15列:")
print(df.iloc[:5, :15])

print(f"\n列名行(第0行):")
print(df.iloc[0, :20].tolist())

print(f"\n数据样本(第3-8行):")
print(df.iloc[3:8, :12])
