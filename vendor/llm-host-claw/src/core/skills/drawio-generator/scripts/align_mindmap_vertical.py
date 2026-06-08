#!/usr/bin/env python3
"""
思维导图垂直防重叠脚本 v3.0
功能：从右往左、从上到下逐列处理，基于父节点y坐标决定碰撞移动方向
适用：逻辑树思维导图（任意层数）

碰撞逻辑：
- 从右到左按列处理
- 每列内从上到下检测碰撞
- 碰撞时：
  * 如果共享同一父节点：更靠下的节点向下移动
  * 如果父节点不同：父节点y坐标更大的子节点向下移动
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from collections import defaultdict


class MindMapNode:
    """思维导图节点"""
    def __init__(self, cell, geometry, node_id):
        self.cell = cell
        self.geometry = geometry
        self.id = node_id
        self.x = float(geometry.get('x'))
        self.y = float(geometry.get('y'))
        self.width = float(geometry.get('width'))
        self.height = float(geometry.get('height'))
        self.parent_id = None  # 父节点ID
        self.parent_y = float('-inf')  # 父节点y坐标（根节点为负无穷）
    
    @property
    def top(self):
        return self.y
    
    @property
    def bottom(self):
        return self.y + self.height
    
    def move_down(self, shift_y: float):
        """向下移动"""
        self.y += shift_y
        self.geometry.set('y', str(int(self.y)))


def build_parent_child_relationships(root) -> Tuple[Dict[str, List[str]], Dict[str, str]]:
    """
    构建父子关系映射
    返回：(parent_to_children, child_to_parent)
    """
    parent_to_children = defaultdict(list)
    child_to_parent = {}
    
    # 遍历所有连接线
    for edge in root.findall(".//mxCell[@edge='1']"):
        source = edge.get('source')  # 父节点（起点A）
        target = edge.get('target')  # 子节点（终点B）
        
        if source and target:
            parent_to_children[source].append(target)
            child_to_parent[target] = source
    
    return parent_to_children, child_to_parent


def detect_columns(nodes: Dict[str, MindMapNode], x_threshold: int = 50) -> Dict[int, List[MindMapNode]]:
    """
    根据x坐标自动分列
    x坐标差距在threshold内认为同一列
    """
    if not nodes:
        return {}
    
    # 按x坐标排序（从左到右）
    sorted_nodes = sorted(nodes.values(), key=lambda n: n.x)
    
    columns = {}
    current_col = 0
    current_x_range = [sorted_nodes[0].x, sorted_nodes[0].x]
    current_col_nodes = [sorted_nodes[0]]
    
    for node in sorted_nodes[1:]:
        # 如果节点x坐标与当前列的x范围差距小于threshold，归入当前列
        if abs(node.x - current_x_range[1]) < x_threshold:
            current_col_nodes.append(node)
            current_x_range[1] = max(current_x_range[1], node.x)
        else:
            # 保存当前列
            columns[current_col] = current_col_nodes
            
            # 开始新列
            current_col += 1
            current_col_nodes = [node]
            current_x_range = [node.x, node.x]
    
    # 保存最后一列
    if current_col_nodes:
        columns[current_col] = current_col_nodes
    
    return columns


def has_overlap(node1: MindMapNode, node2: MindMapNode) -> bool:
    """检测两个节点是否在垂直方向有重叠"""
    return not (node1.bottom <= node2.top or node2.bottom <= node1.top)


def resolve_collision(node1: MindMapNode, node2: MindMapNode, min_dist: int) -> Optional[MindMapNode]:
    """
    解决两个节点的碰撞，返回需要向下移动的节点
    
    碰撞逻辑：
    - 如果共享同一父节点：更靠下的节点向下移动
    - 如果父节点不同：父节点y坐标更大的子节点向下移动
    """
    # 情况1：共享同一父节点
    if node1.parent_id == node2.parent_id:
        # 靠下的节点向下移动
        if node1.y > node2.y:
            return node1
        else:
            return node2
    
    # 情况2：父节点不同
    else:
        # 父节点y坐标更大的子节点向下移动
        if node1.parent_y > node2.parent_y:
            return node1
        else:
            return node2


def process_column_collisions(column_nodes: List[MindMapNode], min_dist: int = 20) -> int:
    """
    处理一列内的所有碰撞
    从上到下扫描，检测并解决重叠
    返回调整次数
    """
    if len(column_nodes) < 2:
        return 0
    
    operations = 0
    
    # 按y坐标从上到下排序
    sorted_nodes = sorted(column_nodes, key=lambda n: n.y)
    
    # 从上到下检测碰撞
    i = 0
    while i < len(sorted_nodes) - 1:
        current = sorted_nodes[i]
        next_node = sorted_nodes[i + 1]
        
        # 检测是否有重叠
        if has_overlap(current, next_node) or (next_node.top - current.bottom) < min_dist:
            # 决定谁向下移动
            node_to_move = resolve_collision(current, next_node, min_dist)
            
            # 计算需要移动的距离
            if node_to_move == current:
                # current向下移动，需要移到next_node下方
                required_top = next_node.bottom + min_dist
                shift_y = required_top - current.top
            else:
                # next_node向下移动，需要移到current下方
                required_top = current.bottom + min_dist
                shift_y = required_top - next_node.top
            
            if shift_y > 0:
                node_to_move.move_down(shift_y)
                operations += 1
                
                # 重新排序，因为位置已改变
                sorted_nodes = sorted(column_nodes, key=lambda n: n.y)
                # 重新开始检查（从头开始）
                i = 0
                continue
        
        i += 1
    
    return operations


def remove_mindmap_vertical_overlaps_v3(nodes: Dict[str, MindMapNode], 
                                        child_to_parent: Dict[str, str],
                                        min_dist: int = 20) -> Dict:
    """
    思维导图垂直防重叠 v3.0
    从右往左按列处理，从上到下检测碰撞
    """
    result = {
        'operations': 0,
        'columns_processed': 0,
        'nodes_adjusted': 0
    }
    
    if len(nodes) < 2:
        return result
    
    # 设置每个节点的父节点信息
    for node_id, node in nodes.items():
        if node_id in child_to_parent:
            parent_id = child_to_parent[node_id]
            node.parent_id = parent_id
            
            # 获取父节点的y坐标
            if parent_id in nodes:
                node.parent_y = nodes[parent_id].y
            else:
                node.parent_y = float('-inf')  # 父节点不存在，优先级最高
        else:
            # 根节点
            node.parent_id = None
            node.parent_y = float('-inf')
    
    # 检测列
    columns = detect_columns(nodes)
    result['columns_processed'] = len(columns)
    
    if not columns:
        return result
    
    # 从右到左处理每一列
    for col_index in sorted(columns.keys(), reverse=True):
        column_nodes = columns[col_index]
        
        if len(column_nodes) < 2:
            continue
        
        # 处理当前列的碰撞
        adjusted = process_column_collisions(column_nodes, min_dist)
        
        if adjusted > 0:
            result['nodes_adjusted'] += adjusted
            result['operations'] += adjusted
    
    return result


def align_mindmap_file(file_path: str, min_dist: int = 20) -> dict:
    """处理思维导图文件"""
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
        root = ET.fromstring(content)
        
        # 收集所有节点
        nodes = {}
        for cell in root.findall(".//mxCell"):
            geometry = cell.find("mxGeometry")
            node_id = cell.get('id')
            
            if geometry is not None and node_id:
                x = geometry.get('x')
                y = geometry.get('y')
                width = geometry.get('width')
                height = geometry.get('height')
                
                if x and y and width and height:
                    try:
                        node = MindMapNode(cell, geometry, node_id)
                        nodes[node_id] = node
                    except (ValueError, TypeError):
                        continue
        
        if len(nodes) < 2:
            result['logs'].append("节点数量少于2个，无需处理")
            result['success'] = True
            return result
        
        # 构建父子关系
        parent_to_children, child_to_parent = build_parent_child_relationships(root)
        
        # 执行防重叠 v3.0
        process_result = remove_mindmap_vertical_overlaps_v3(nodes, child_to_parent, min_dist)
        
        result['operations'] = process_result['operations']
        result['adjusted'] = process_result['operations'] > 0
        
        if result['adjusted']:
            result['logs'].append(f"检测到 {process_result['columns_processed']} 列")
            result['logs'].append(f"调整了 {process_result['nodes_adjusted']} 次")
            result['logs'].append(f"最小垂直间距: {min_dist}px")
            
            # 保存
            new_content = ET.tostring(root, encoding='unicode', method='xml')
            if not new_content.startswith('<?xml'):
                new_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + new_content
            path.write_text(new_content, encoding='utf-8')
        else:
            result['logs'].append("未发现重叠，无需调整")
        
        result['success'] = True
        
    except Exception as e:
        result['issues'].append(f"处理失败: {str(e)}")
        import traceback
        result['issues'].append(traceback.format_exc())
    
    return result


def main():
    if len(sys.argv) < 2:
        print("用法: python align_mindmap_vertical_v3.py <file_path> [min_distance]")
        print("  file_path: Draw.io XML 文件路径")
        print("  min_distance: 最小垂直间距（可选，默认20px）")
        print("\n新逻辑 v3.0:")
        print("  - 从右往左按列处理")
        print("  - 每列内从上到下检测碰撞")
        print("  - 共享父节点：靠下的向下移动")
        print("  - 不同父节点：父节点y更大的子节点向下移动")
        sys.exit(1)
    
    file_path = sys.argv[1]
    min_dist = 20
    
    if len(sys.argv) >= 3:
        try:
            min_dist = int(sys.argv[2])
        except ValueError:
            print(f"⚠️  警告: 无效的间距值，使用默认值 20px")
    
    result = align_mindmap_file(file_path, min_dist)
    
    print(f"\n{'='*60}")
    print(f"思维导图垂直防重叠脚本 v3.0")
    print(f"{'='*60}\n")
    
    if result['logs']:
        for log in result['logs']:
            print(f"  ✓ {log}")
    
    if result['issues']:
        print("\n⚠️  发现问题:")
        for issue in result['issues']:
            print(f"  {issue}")
    
    if result['success']:
        if result['adjusted']:
            print(f"\n✅ 成功！调整了 {result['operations']} 次")
        else:
            print(f"\n✅ 完成！无需调整")
    else:
        print("\n❌ 处理失败")
        sys.exit(1)


if __name__ == '__main__':
    main()