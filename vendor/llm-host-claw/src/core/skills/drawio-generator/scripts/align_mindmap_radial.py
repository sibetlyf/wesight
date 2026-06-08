#!/usr/bin/env python3
"""
思维导图放射状布局防重叠脚本 v3.0
功能：
  1. 从内向外（根节点→叶节点）逐层处理
  2. 检测所有方向的重叠和紧贴
  3. 向外推开重叠节点（远离中心方向）
  4. 确保所有节点之间保持最小间距
适用：放射状思维导图（根节点居中，分支向四周发散）
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Tuple
from collections import defaultdict
import math


def find_root_node(nodes: List[Dict]) -> Dict:
    """
    查找根节点（最接近画布中心的节点）
    """
    if not nodes:
        return None
    
    # 计算几何中心
    x_coords = [n['center_x'] for n in nodes]
    y_coords = [n['center_y'] for n in nodes]
    center_x = sum(x_coords) / len(x_coords)
    center_y = sum(y_coords) / len(y_coords)
    
    # 找到最接近中心的节点
    root = min(nodes, key=lambda n: 
        math.sqrt((n['center_x'] - center_x)**2 + (n['center_y'] - center_y)**2))
    return root


def calculate_angle(root: Dict, node: Dict) -> float:
    """
    计算节点相对于根节点的角度（弧度）
    """
    dx = node['center_x'] - root['center_x']
    dy = node['center_y'] - root['center_y']
    return math.atan2(dy, dx)


def calculate_distance(node1: Dict, node2: Dict) -> float:
    """
    计算两个节点中心点之间的距离
    """
    dx = node1['center_x'] - node2['center_x']
    dy = node1['center_y'] - node2['center_y']
    return math.sqrt(dx * dx + dy * dy)


def check_rectangles_overlap(node1: Dict, node2: Dict, min_gap: int = 0) -> bool:
    """
    检查两个矩形节点是否重叠或距离过近
    
    参数:
        node1, node2: 节点字典
        min_gap: 最小间距（像素）
    
    返回: True如果重叠或距离<min_gap
    """
    # 矩形边界（考虑最小间距）
    left1 = node1['x'] - min_gap
    right1 = node1['x'] + node1['width'] + min_gap
    top1 = node1['y'] - min_gap
    bottom1 = node1['y'] + node1['height'] + min_gap
    
    left2 = node2['x']
    right2 = node2['x'] + node2['width']
    top2 = node2['y']
    bottom2 = node2['y'] + node2['height']
    
    # 检查是否有重叠
    horizontal_overlap = not (right1 < left2 or left1 > right2)
    vertical_overlap = not (bottom1 < top2 or top1 > bottom2)
    
    return horizontal_overlap and vertical_overlap


def classify_nodes_by_level(nodes: List[Dict], root: Dict, edges: List[Dict]) -> Dict:
    """
    按层级分类节点（BFS从根节点开始）
    
    返回: {
        'levels': {level: [nodes]},
        'level_map': {node_id: level},
        'children_map': {parent_id: [child_ids]},
        'parent_map': {child_id: parent_id},
        'max_level': int
    }
    """
    # 构建父子关系
    children_map = defaultdict(list)
    parent_map = {}
    
    for edge in edges:
        source = edge.get('source')
        target = edge.get('target')
        if source and target:
            children_map[source].append(target)
            parent_map[target] = source
    
    # 按ID建立索引
    node_by_id = {n['id']: n for n in nodes}
    
    # BFS计算层级
    level_map = {root['id']: 0}
    levels = defaultdict(list)
    levels[0].append(root)
    
    queue = [(root['id'], 0)]
    visited = {root['id']}
    max_level = 0
    
    while queue:
        node_id, level = queue.pop(0)
        for child_id in children_map[node_id]:
            if child_id not in visited and child_id in node_by_id:
                visited.add(child_id)
                child_level = level + 1
                level_map[child_id] = child_level
                levels[child_level].append(node_by_id[child_id])
                max_level = max(max_level, child_level)
                queue.append((child_id, child_level))
    
    return {
        'levels': levels,
        'level_map': level_map,
        'children_map': children_map,
        'parent_map': parent_map,
        'max_level': max_level
    }


def push_node_outward(node: Dict, root: Dict, distance: float):
    """
    将节点向外推（远离根节点方向）
    
    参数:
        node: 要推开的节点
        root: 根节点
        distance: 推开的距离（像素）
    """
    # 计算当前节点相对于根节点的方向
    dx = node['center_x'] - root['center_x']
    dy = node['center_y'] - root['center_y']
    current_dist = math.sqrt(dx * dx + dy * dy)
    
    if current_dist < 1:  # 避免除以0
        # 如果节点就在根节点位置，随机推开
        dx, dy = 1, 0
        current_dist = 1
    
    # 归一化方向向量
    direction_x = dx / current_dist
    direction_y = dy / current_dist
    
    # 计算新位置（向外推）
    push_x = direction_x * distance
    push_y = direction_y * distance
    
    new_x = node['x'] + push_x
    new_y = node['y'] + push_y
    
    # 更新节点位置
    node['geometry'].set('x', str(int(new_x)))
    node['geometry'].set('y', str(int(new_y)))
    node['x'] = new_x
    node['y'] = new_y
    node['center_x'] = new_x + (node['width'] / 2)
    node['center_y'] = new_y + (node['height'] / 2)


def resolve_overlaps_radial(nodes: List[Dict], root: Dict, min_gap: int = 20) -> int:
    """
    解决放射状布局中的重叠和紧贴问题
    
    算法：
    1. 检测所有重叠的节点对
    2. 对于每对重叠节点，将离根节点更远的那个向外推
    3. 迭代直到没有重叠
    
    参数:
        nodes: 当前层的节点列表
        root: 根节点
        min_gap: 最小间距
    
    返回: 调整的节点数量
    """
    if len(nodes) < 2:
        return 0
    
    ops = 0
    max_iterations = 20
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        has_overlap = False
        
        # 检测所有节点对
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                node_a = nodes[i]
                node_b = nodes[j]
                
                # 检查是否重叠或距离过近
                if check_rectangles_overlap(node_a, node_b, min_gap):
                    has_overlap = True
                    
                    # 计算两个节点到根节点的距离
                    dist_a = calculate_distance(node_a, root)
                    dist_b = calculate_distance(node_b, root)
                    
                    # 推开离根节点更远的节点
                    if dist_a > dist_b:
                        push_node_outward(node_a, root, min_gap)
                        ops += 1
                    else:
                        push_node_outward(node_b, root, min_gap)
                        ops += 1
        
        if not has_overlap:
            break
    
    return ops


def align_mindmap_radial_file(file_path: str, min_gap: int = 20) -> dict:
    """处理放射状思维导图文件"""
    result = {
        'success': False, 
        'adjusted': False, 
        'operations': 0, 
        'logs': [], 
        'issues': []
    }
    
    path = Path(file_path)
    
    if not path.exists():
        result['issues'].append(f"文件不存在: {file_path}")
        return result
    
    try:
        content = path.read_text(encoding='utf-8')
        xml_root = ET.fromstring(content)
        
        # 收集节点
        nodes = []
        for cell in xml_root.findall(".//mxCell"):
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
                        
                        nodes.append({
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
        
        # 收集边（连接关系）
        edges = []
        for cell in xml_root.findall(".//mxCell"):
            if cell.get('edge') == '1':
                edges.append({
                    'source': cell.get('source'),
                    'target': cell.get('target')
                })
        
        if len(nodes) < 2:
            result['logs'].append("节点数量少于2个，无需处理")
            result['success'] = True
            return result
        
        # 查找根节点
        root_node = find_root_node(nodes)
        result['logs'].append(f"识别根节点: {root_node['id']} (中心点: x={root_node['center_x']:.0f}, y={root_node['center_y']:.0f})")
        
        # 按层级分类节点
        classified = classify_nodes_by_level(nodes, root_node, edges)
        
        result['logs'].append(f"层级分析: 共{classified['max_level'] + 1}层")
        for level in range(classified['max_level'] + 1):
            count = len(classified['levels'][level])
            result['logs'].append(f"  第{level}层: {count}个节点")
        
        total_ops = 0
        
        # 从内向外处理（从第1层开始，第0层是根节点）
        result['logs'].append(f"\n开始处理重叠，最小间距: {min_gap}px")
        for level in range(1, classified['max_level'] + 1):
            level_nodes = classified['levels'][level]
            if len(level_nodes) < 2:
                continue
            
            ops = resolve_overlaps_radial(level_nodes, root_node, min_gap)
            if ops > 0:
                result['logs'].append(f"  第{level}层: 调整了{ops}次")
                total_ops += ops
        
        result['operations'] = total_ops
        result['adjusted'] = total_ops > 0
        
        if total_ops > 0:
            result['logs'].append(f"\n✓ 总计调整: {total_ops} 次")
            result['logs'].append(f"✓ 最小间距: {min_gap}px")
            
            # 保存
            new_content = ET.tostring(xml_root, encoding='unicode', method='xml')
            if not new_content.startswith('<?xml'):
                new_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + new_content
            path.write_text(new_content, encoding='utf-8')
        else:
            result['logs'].append("\n未发现重叠，无需调整")
        
        result['success'] = True
        
    except Exception as e:
        import traceback
        result['issues'].append(f"处理失败: {str(e)}")
        result['issues'].append(traceback.format_exc())
    
    return result


def main():
    if len(sys.argv) < 2:
        print("用法: python align_mindmap_radial_v3.py <file_path> [min_gap]")
        print("  file_path: Draw.io XML 文件路径")
        print("  min_gap: 节点之间的最小间距（可选，默认20px）")
        sys.exit(1)
    
    file_path = sys.argv[1]
    min_gap = 20
    
    if len(sys.argv) >= 3:
        try:
            min_gap = int(sys.argv[2])
        except ValueError:
            print(f"⚠️  警告: 无效的间距值，使用默认值 20px")
    
    result = align_mindmap_radial_file(file_path, min_gap)
    
    print(f"\n{'='*60}")
    print(f"思维导图放射状布局防重叠脚本 v3.0")
    print(f"{'='*60}\n")
    
    if result['logs']:
        for log in result['logs']:
            print(f"  {log}")
    
    if result['issues']:
        print("\n⚠️  发现问题:")
        for issue in result['issues']:
            print(f"  {issue}")
    
    if result['success']:
        if result['adjusted']:
            print(f"\n✅ 成功！总计调整 {result['operations']} 次")
        else:
            print(f"\n✅ 完成！无需调整")
    else:
        print("\n❌ 处理失败")
        sys.exit(1)


if __name__ == '__main__':
    main()