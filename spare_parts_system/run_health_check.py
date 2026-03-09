# -*- coding: utf-8 -*-
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, "D:/spare_parts_system")

# 运行完整的健康诊断流程
print("=== 运行 run_health_diagnostic() ===")
from core.inventory_health_engine import run_health_diagnostic

result = run_health_diagnostic()

target = '802138302'
df = result['data']

if target in df['_part_no'].values:
    row = df[df['_part_no'] == target].iloc[0]
    print(f"\n物料 {target} 的最终数据:")
    print(f"  inventory_qty: {row.get('inventory_qty')}")
    print(f"  total_inventory: {row.get('total_inventory')}")
    print(f"  _total_value: {row.get('_total_value')}")
    print(f"  _unit_price: {row.get('_unit_price')}")
    print(f"  part_name: {row.get('part_name')}")
else:
    print(f"\n物料 {target} 不在结果中")

# 检查统计
stats = result.get('stats', {})
print(f"\n统计信息:")
print(f"  总物料数: {stats.get('total_parts')}")
print(f"  总库存价值: {stats.get('total_value')}")
