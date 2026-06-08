#!/usr/bin/env python3
"""
Draw.io 架构图智能布局脚本 v1.0
处理父子节点关系，确保无重叠无溢出
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Tuple


# ============================================================================
# 配置参数
# ============================================================================
LAYER_GAP = 70          # 层容器间距
CHILD_GAP = 40          # 子节点最小间距
PADDING = 30            # 容器内边距
TITLE_HEIGHT = 40       # 容器标题预留高度
MAX_ITERATIONS = 10     # AABB推挤最大迭代次数


# ============================================================================
# AABB碰撞检测与推挤
# ============================================================================

def aabb_collision(A: Dict, B: Dict) -> bool:
    """AABB碰撞检测"""
    return (A['x'] < B['x'] + B['width'] and
            A['x'] + A['width'] > B['x'] and
            A['y'] < B['y'] + B['height'] and
            A['y'] + A['height'] > B['y'])


def resolve_all_overlaps(nodes: List[Dict], min_gap: int) -> int:
    """
    迭代推挤，解决所有节点重叠
    返回推挤次数
    """
    operations = 0
    
    for iteration in range(MAX_ITERATIONS):
        has_overlap = False
        
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                A = nodes[i]
                B = nodes[j]
                
                if aabb_collision(A, B):
                    # 计算重叠量
                    overlap_x = min(A['x'] + A['width'], B['x'] + B['width']) - \
                               max(A['x'], B['x'])
                    overlap_y = min(A['y'] + A['height'], B['y'] + B['height']) - \
                               max(A['y'], B['y'])
                    
                    # 选择重叠更小的方向推开
                    if overlap_x < overlap_y:
                        # 水平推开
                        if B['x'] > A['x']:
                            new_x = A['x'] + A['width'] + min_gap
                            B['geometry'].set('x', str(int(new_x)))
                            B['x'] = new_x
                        else:
                            new_x = B['x'] + B['width'] + min_gap
                            A['geometry'].set('x', str(int(new_x)))
                            A['x'] = new_x
                    else:
                        # 垂直推开
                        if B['y'] > A['y']:
                            new_y = A['y'] + A['height'] + min_gap
                            B['geometry'].set('y', str(int(new_y)))
                            B['y'] = new_y
                        else:
                            new_y = B['y'] + B['height'] + min_gap
                            A['geometry'].set('y', str(int(new_y)))
                            A['y'] = new_y
                    
                    has_overlap = True
                    operations += 1
        
        if not has_overlap:
            break
    
    return operations


# ============================================================================
# 核心处理逻辑
# ============================================================================

def parse_node_info(cell: ET.Element) -> Dict:
    """解析节点信息"""
    geometry = cell.find("mxGeometry")
    if geometry is None:
        return None
    
    x = geometry.get('x')
    y = geometry.get('y')
    width = geometry.get('width')
    height = geometry.get('height')
    
    if not all([x, y, width, height]):
        return None
    
    try:
        return {
            'cell': cell,
            'geometry': geometry,
            'id': cell.get('id', 'unknown'),
            'parent': cell.get('parent', '1'),
            'x': float(x),
            'y': float(y),
            'width': float(width),
            'height': float(height)
        }
    except (ValueError, TypeError):
        return None


def build_hierarchy(root: ET.Element) -> Tuple[List[Dict], Dict[str, List[Dict]]]:
    """
    构建父子关系树
    返回: (容器列表, {容器ID: [子节点列表]})
    """
    all_nodes = []
    
    # 收集所有节点
    for cell in root.findall(".//mxCell"):
        node_info = parse_node_info(cell)
        if node_info:
            all_nodes.append(node_info)
    
    # 分类：容器 vs 子节点
    containers = []
    children_map = {}
    
    for node in all_nodes:
        parent_id = node['parent']
        
        if parent_id in ['0', '1']:
            # 根节点（容器）
            containers.append(node)
            children_map[node['id']] = []
        else:
            # 子节点
            if parent_id not in children_map:
                children_map[parent_id] = []
            children_map[parent_id].append(node)
    
    return containers, children_map


def process_container_children(container: Dict, children: List[Dict]) -> Tuple[int, List[str]]:
    """
    处理容器内的子节点
    返回: (操作次数, 日志)
    """
    if not children:
        return 0, []
    
    logs = []
    operations = 0
    
    # 步骤1：子节点避开标题区
    title_adjusted = 0
    for child in children:
        if child['y'] < TITLE_HEIGHT:
            child['y'] = TITLE_HEIGHT
            child['geometry'].set('y', str(int(TITLE_HEIGHT)))
            title_adjusted += 1
    
    if title_adjusted > 0:
        logs.append(f"  - 标题避让: {title_adjusted} 个子节点下移")
        operations += title_adjusted
    
    # 步骤2：AABB迭代推挤（解决所有重叠）
    overlap_ops = resolve_all_overlaps(children, CHILD_GAP)
    if overlap_ops > 0:
        logs.append(f"  - 防重叠: 推挤了 {overlap_ops} 次")
        operations += overlap_ops
    
    # 步骤3：边界检查（左上推回）
    boundary_adjusted = 0
    for child in children:
        if child['x'] < PADDING:
            child['x'] = PADDING
            child['geometry'].set('x', str(int(PADDING)))
            boundary_adjusted += 1
        
        if child['y'] < TITLE_HEIGHT:
            child['y'] = TITLE_HEIGHT
            child['geometry'].set('y', str(int(TITLE_HEIGHT)))
            boundary_adjusted += 1
    
    if boundary_adjusted > 0:
        logs.append(f"  - 边界校正: {boundary_adjusted} 个子节点推回边界内")
        operations += boundary_adjusted
    
    # 步骤4：检查溢出并扩容器
    rightmost = max([c['x'] + c['width'] for c in children])
    bottommost = max([c['y'] + c['height'] for c in children])
    
    original_width = container['width']
    original_height = container['height']
    
    need_expand = False
    
    if rightmost + PADDING > container['width']:
        new_width = rightmost + PADDING
        container['width'] = new_width
        container['geometry'].set('width', str(int(new_width)))
        need_expand = True
    
    if bottommost + PADDING > container['height']:
        new_height = bottommost + PADDING
        container['height'] = new_height
        container['geometry'].set('height', str(int(new_height)))
        need_expand = True
    
    if need_expand:
        logs.append(f"  - 容器扩展: {int(original_width)}x{int(original_height)} → " +
                   f"{int(container['width'])}x{int(container['height'])}")
        operations += 1
    
    return operations, logs


def align_architecture(root: ET.Element) -> Tuple[int, List[str]]:
    """
    架构图智能布局主流程
    """
    logs = []
    total_operations = 0
    
    # ========== 步骤1：构建父子关系 ==========
    containers, children_map = build_hierarchy(root)
    
    if not containers:
        return 0, ["未找到容器节点"]
    
    logs.append(f"识别到 {len(containers)} 个容器，{sum(len(c) for c in children_map.values())} 个子节点")
    
    # ========== 步骤2：处理每个容器内部 ==========
    logs.append("\n【处理容器内部】")
    
    for container in containers:
        container_id = container['id']
        children = children_map.get(container_id, [])
        
        if not children:
            continue
        
        ops, child_logs = process_container_children(container, children)
        
        if ops > 0:
            logs.append(f"\n容器 [{container_id}] ({len(children)} 个子节点):")
            logs.extend(child_logs)
            total_operations += ops
    
    # ========== 步骤3：处理容器之间碰撞 ==========
    logs.append("\n【处理容器碰撞】")
    
    container_ops = resolve_all_overlaps(containers, LAYER_GAP)
    
    if container_ops > 0:
        logs.append(f"容器防重叠: 推挤了 {container_ops} 次")
        total_operations += container_ops
    else:
        logs.append("容器无重叠")
    
    return total_operations, logs


# ============================================================================
# 文件处理
# ============================================================================

def align_drawio_file(file_path: str) -> dict:
    """
    处理Draw.io文件
    """
    result = {
        'success': False,
        'aligned': False,
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
        
        ops, logs = align_architecture(root)
        
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
        print("用法: python align_drawio_architecture.py <file_path>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    result = align_drawio_file(file_path)
    
    print(f"\n{'='*60}")
    print(f"Draw.io 架构图智能布局 v1.0")
    print(f"{'='*60}\n")
    
    if result['logs']:
        for log in result['logs']:
            print(log)
    
    if result['issues']:
        print("\n⚠️  发现问题:")
        for issue in result['issues']:
            print(f"  {issue}")
    
    if result['success'] and result['aligned']:
        print(f"\n✅ 成功！执行了 {result['operations']} 次调整")
    elif result['success']:
        print("\n✅ 文件无需调整")
    else:
        print("\n❌ 处理失败")


if __name__ == '__main__':
    main()
