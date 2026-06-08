#!/usr/bin/env python3
"""
Draw.io 节点智能布局脚本 v3.1 (优化顺序版)
修改记录：
- 调整了处理顺序：先执行防重叠(Anti-overlap)，再执行对齐(Alignment)。
- 原因：防重叠操作会移动节点位置，如果先对齐再推开，会导致对齐被破坏。先推开再对齐，可以确保最终结果既不重叠又整齐。
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Tuple


# ============================================================================
# 基础算法模块
# ============================================================================

def _cluster_by_coordinate(nodes: List[Dict], 
                          coord_key: str, 
                          threshold: float) -> List[List[Dict]]:
    """根据某个坐标将节点聚类成组"""
    if not nodes:
        return []
    
    # 按坐标值排序
    sorted_nodes = sorted(nodes, key=lambda n: n[coord_key])
    
    groups = []
    current_group = [sorted_nodes[0]]
    
    for i in range(1, len(sorted_nodes)):
        current_node = sorted_nodes[i]
        prev_node = sorted_nodes[i-1]
        
        # 如果距离小于阈值，归入同一组
        if abs(current_node[coord_key] - prev_node[coord_key]) <= threshold:
            current_group.append(current_node)
        else:
            if len(current_group) > 1:
                groups.append(current_group)
            current_group = [current_node]
    
    if len(current_group) > 1:
        groups.append(current_group)
    
    return groups


def _calculate_median(values: List[float]) -> float:
    """计算中位数"""
    sorted_values = sorted(values)
    n = len(sorted_values)
    if n % 2 == 0:
        return (sorted_values[n//2 - 1] + sorted_values[n//2]) / 2
    else:
        return sorted_values[n//2]


# ============================================================================
# 防重叠模块 (双向推挤)
# ============================================================================

def remove_horizontal_overlaps(nodes: List[Dict], min_dist: int) -> int:
    """
    水平防重叠：检查每一行，如果重叠则【向右】推
    """
    ops = 0
    # 1. 按行分组 (使用 center_y，阈值建议与对齐阈值一致)
    rows = _cluster_by_coordinate(nodes, 'center_y', threshold=60)
    
    for row_nodes in rows:
        if len(row_nodes) < 2:
            continue
        
        # 按 X 轴(从左到右)排序
        row_nodes.sort(key=lambda n: n['x'])
        
        # 记录上一个节点的【右侧】位置
        prev_right = row_nodes[0]['x'] + row_nodes[0]['width']
        
        for i in range(1, len(row_nodes)):
            curr = row_nodes[i]
            # 目标位置 = 上一个右侧 + 最小间距
            target_x = prev_right + min_dist
            
            # 如果当前节点位置 < 目标位置，说明太近或重叠了
            if curr['x'] < target_x:
                new_x = target_x
                curr['geometry'].set('x', str(int(new_x)))
                
                # 实时更新内存数据，保证后续计算准确
                curr['x'] = new_x
                curr['center_x'] = new_x + (curr['width'] / 2)
                ops += 1
            
            # 更新 prev_right
            prev_right = curr['x'] + curr['width']
    return ops


def remove_vertical_overlaps(nodes: List[Dict], min_dist: int) -> int:
    """
    垂直防重叠：检查每一列，如果重叠则【向下】推
    """
    ops = 0
    # 1. 按列分组 (使用 center_x，阈值建议与对齐阈值一致)
    columns = _cluster_by_coordinate(nodes, 'center_x', threshold=60)
    
    for col_nodes in columns:
        if len(col_nodes) < 2:
            continue
        
        # 按 Y 轴(从上到下)排序
        col_nodes.sort(key=lambda n: n['y'])
        
        # 记录上一个节点的【底部】位置
        prev_bottom = col_nodes[0]['y'] + col_nodes[0]['height']
        
        for i in range(1, len(col_nodes)):
            curr = col_nodes[i]
            # 目标位置 = 上一个底部 + 最小间距
            target_y = prev_bottom + min_dist
            
            # 如果当前节点位置 < 目标位置，说明太近或重叠了
            if curr['y'] < target_y:
                new_y = target_y
                curr['geometry'].set('y', str(int(new_y)))
                
                # 实时更新内存数据
                curr['y'] = new_y
                curr['center_y'] = new_y + (curr['height'] / 2)
                ops += 1
            
            # 更新 prev_bottom
            prev_bottom = curr['y'] + curr['height']
    return ops


# ============================================================================
# 核心处理逻辑
# ============================================================================

def intelligent_align_nodes(root: ET.Element, 
                           vertical_threshold: int, 
                           horizontal_threshold: int) -> Tuple[int, List[str]]:
    """
    智能对齐节点：水平防重叠 -> 垂直防重叠 -> 中心对齐
    (先分开，再对齐)
    """
    logs = []
    alignment_operations = 0
    
    # --- 收集节点信息 ---
    nodes_with_position = []
    for cell in root.findall(".//mxCell"):
        geometry = cell.find("mxGeometry")
        if geometry is not None:
            x = geometry.get('x')
            y = geometry.get('y')
            width = geometry.get('width')
            height = geometry.get('height')
            
            if x and y and width and height:
                try:
                    x_val = float(x)
                    y_val = float(y)
                    w_val = float(width)
                    h_val = float(height)
                    
                    nodes_with_position.append({
                        'cell': cell,
                        'geometry': geometry,
                        'x': x_val,
                        'y': y_val,
                        'width': w_val,
                        'height': h_val,
                        'center_x': x_val + (w_val / 2),
                        'center_y': y_val + (h_val / 2),
                        'id': cell.get('id', 'unknown')
                    })
                except (ValueError, TypeError):
                    continue
    
    if len(nodes_with_position) < 2:
        return 0, ["节点过少，跳过处理"]

    # ==========================================
    # 1. 防重叠阶段 (先让它们分开)
    # ==========================================
    
    # 设定最小间距 (像素)
    MIN_DIST_X = 60  # 水平方向最小间距
    MIN_DIST_Y = 40  # 垂直方向最小间距
    
    # 执行水平推挤 (修改 X 坐标)
    h_ops = remove_horizontal_overlaps(nodes_with_position, min_dist=MIN_DIST_X)
    if h_ops > 0:
        alignment_operations += h_ops
        logs.append(f"水平防重叠: 向右推挤了 {h_ops} 个节点")
        
    # 执行垂直推挤 (修改 Y 坐标)
    v_ops = remove_vertical_overlaps(nodes_with_position, min_dist=MIN_DIST_Y)
    if v_ops > 0:
        alignment_operations += v_ops
        logs.append(f"垂直防重叠: 向下推挤了 {v_ops} 个节点")

    # ==========================================
    # 2. 对齐阶段 (再让它们整齐)
    # ==========================================
    
    # 纵列对齐 (基于 X 轴居中)
    # 注意：此时使用的是防重叠调整后的新坐标
    vertical_groups = _cluster_by_coordinate(nodes_with_position, 'center_x', vertical_threshold)
    for group in vertical_groups:
        if len(group) > 1:
            center_x_values = [node['center_x'] for node in group]
            target_center_x = _calculate_median(center_x_values)
            for node in group:
                new_x = target_center_x - (node['width'] / 2)
                # 只有当移动距离明显时才移动，避免微小抖动
                if abs(new_x - node['x']) > 1:
                    node['geometry'].set('x', str(int(new_x)))
                    # 更新内存数据
                    node['x'] = new_x
                    node['center_x'] = target_center_x 
                    alignment_operations += 1
            logs.append(f"纵列对齐: 统一了 {len(group)} 个节点的中心X坐标")
    
    # 横列对齐 (基于 Y 轴居中)
    horizontal_groups = _cluster_by_coordinate(nodes_with_position, 'center_y', horizontal_threshold)
    for group in horizontal_groups:
        if len(group) > 1:
            center_y_values = [node['center_y'] for node in group]
            target_center_y = _calculate_median(center_y_values)
            for node in group:
                new_y = target_center_y - (node['height'] / 2)
                if abs(new_y - node['y']) > 1:
                    node['geometry'].set('y', str(int(new_y)))
                    # 更新内存数据
                    node['y'] = new_y
                    node['center_y'] = target_center_y
                    alignment_operations += 1
            logs.append(f"横列对齐: 统一了 {len(group)} 个节点的中心Y坐标")

    if alignment_operations > 0:
        logs.append(f"总计执行了 {alignment_operations} 次位置调整")
    
    return alignment_operations, logs


def align_drawio_file(file_path: str, 
                     vertical_threshold: int = 60,
                     horizontal_threshold: int = 60) -> dict: 
    result = {'success': False, 'aligned': False, 'operations': 0, 'logs': [], 'issues': []}
    path = Path(file_path)
    
    if not path.exists():
        result['issues'].append(f"文件不存在: {file_path}")
        return result
        
    try:
        content = path.read_text(encoding='utf-8')
        root = ET.fromstring(content)
        
        ops, logs = intelligent_align_nodes(root, vertical_threshold, horizontal_threshold)
        result['operations'] = ops
        result['logs'] = logs
        result['aligned'] = ops > 0
        
        if result['aligned']:
            new_content = ET.tostring(root, encoding='unicode', method='xml')
            if not new_content.startswith('<?xml'):
                new_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + new_content
            path.write_text(new_content, encoding='utf-8')
            
        result['success'] = True
        
    except Exception as e:
        result['issues'].append(f"处理失败: {e}")
        
    return result


def main():
    if len(sys.argv) != 2:
        print("用法: python align_drawio_nodes.py <file_path>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    result = align_drawio_file(file_path)
    
    print(f"\n{'='*60}")
    print(f"Draw.io 节点智能布局 v3.1 (先防重叠 -> 后对齐)")
    print(f"{'='*60}\n")
    
    if result['logs']:
        for log in result['logs']:
            print(f"  {log}")
    
    if result['issues']:
        print("⚠️  发现问题:")
        for issue in result['issues']:
            print(f"  {issue}")
    
    if result['success'] and result['aligned']:
        print(f"\n✅ 成功！执行了 {result['operations']} 次调整")
    else:
        print("\n✅ 文件无需调整或处理失败")

if __name__ == '__main__':
    main()