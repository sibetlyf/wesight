#!/usr/bin/env python3
"""
Draw.io XML自动修正脚本 v2.0
采用混合修复策略：正则预处理 + DOM重构 + lxml兜底
修正常见的XML格式错误，确保文件可以在Draw.io中正确渲染
"""

import re
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Tuple, List, Dict, Optional


# ============================================================================
# Level 1: 正则预处理（快速清洗明显错误）
# ============================================================================

def level1_regex_cleanup(content: str) -> Tuple[str, List[str]]:
    """
    Level 1: 正则预处理
    目标：快速修复明显的文本错误，提高后续DOM解析成功率
    """
    fixes = []
    
    # --- 修复0: Style属性引号错误 ---
    style_fixes_count = 0
    
    # 0.1 修复 style 分裂
    split_pattern = r'style="([^"]*?)";(\w+)="([^"]*?;?)"'
    while re.search(split_pattern, content):
        def fix_split(match):
            nonlocal style_fixes_count
            style_fixes_count += 1
            style_val = match.group(1)
            attr_name = match.group(2)
            attr_val = match.group(3).rstrip(';').lstrip('#')
            if attr_name.endswith('Color') and re.match(r'^[0-9a-fA-F]{6}$', attr_val):
                attr_val = '#' + attr_val
            return f'style="{style_val};{attr_name}={attr_val};"'
        
        new_content = re.sub(split_pattern, fix_split, content, count=1)
        if new_content == content: break
        content = new_content

    # 0.2 修复 style 内部引号
    inner_quote_pattern = r'(style="[^"]*?)(\w+)="([^"]*?)"([^"]*?")'
    iteration = 0
    while iteration < 20 and re.search(inner_quote_pattern, content):
        def fix_inner(match):
            nonlocal style_fixes_count
            style_fixes_count += 1
            prefix = match.group(1)
            key = match.group(2)
            value = match.group(3).lstrip('#')
            suffix = match.group(4)
            if key.endswith('Color') and re.match(r'^[0-9a-fA-F]{6}$', value):
                value = '#' + value
            return f'{prefix}{key}={value}{suffix}'
        
        new_content = re.sub(inner_quote_pattern, fix_inner, content, count=1)
        if new_content == content: break
        content = new_content
        iteration += 1

    # 0.3 修复行尾未闭合引号
    unclosed_pattern = r'style="([^"]*?);?\s*$'
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'style=' in line and line.count('"') % 2 == 1:
            if re.search(unclosed_pattern, line):
                lines[i] = re.sub(unclosed_pattern, r'style="\1"', line)
                style_fixes_count += 1
    content = '\n'.join(lines)
    
    if style_fixes_count > 0:
        fixes.append(f"修复了 {style_fixes_count} 处style属性引号错误")
    
    # --- 修复1: XML实体转义 ---
    before_count = content.count('&')
    content = re.sub(r'&(?!(amp|lt|gt|quot|apos|#\d+);)', '&amp;', content)
    after_count = content.count('&amp;')
    if after_count > before_count:
        fixes.append(f"转义了 {after_count - before_count} 个未转义的&符号")
    
    # --- 修复2 (关键修改): Value内容清洗 ---
    # 这里处理 \n 转真实换行
    def cleanup_value_content(match):
        attr_value = match.group(1)
        modified = False
        
        # A. 修复换行符: \n -> &#10;
        if '\\n' in attr_value:
            attr_value = attr_value.replace('\\n', '&#10;')
            modified = True
            
        # B. 转义特殊字符
        if '<' in attr_value or '>' in attr_value:
            attr_value = attr_value.replace('<', '&lt;').replace('>', '&gt;')
            modified = True
            
        if modified:
            return f'value="{attr_value}"'
        return match.group(0)
    
    value_pattern = r'value="([^"]*)"'
    before_value = content
    content = re.sub(value_pattern, cleanup_value_content, content)
    
    if before_value != content:
        if '&#10;' in content and '\\n' in before_value:
            fixes.append("修复了文本中的换行符 (\\n -> 真实换行)")
        else:
            fixes.append("转义了value属性中的特殊字符")
    
    # --- 修复3: 空的自闭合标签 ---
    empty_tag_pattern = r'<(mxCell|mxGeometry)\s+([^>]*?)>\s*</\1>'
    if len(re.findall(empty_tag_pattern, content)) > 0:
        content = re.sub(empty_tag_pattern, r'<\1 \2/>', content)
        fixes.append("修正了空的自闭合标签")
        
    # --- 修复4: 补全缺失的闭合标签 ---
    if content.strip().startswith('<mxfile') or content.strip().startswith('<?xml'):
        if '</mxfile>' not in content:
            missing_tags = []
            if '<mxGraphModel' in content and '</mxGraphModel>' not in content: missing_tags.append('</mxGraphModel>')
            if '<diagram' in content and '</diagram>' not in content: missing_tags.append('</diagram>')
            if '<mxfile' in content: missing_tags.append('</mxfile>')
            if missing_tags:
                content = content.rstrip() + ''.join(missing_tags)
                fixes.append(f"补充了缺失的闭合标签: {', '.join(missing_tags)}")
    
    return content, fixes



# ============================================================================
# Level 2: DOM重构（核心修复逻辑）
# ============================================================================

def normalize_style_string(style_str: str) -> Tuple[str, str]:
    """
    Style字符串标准化（修正版）
    
    修正点：
    1. 针对 rhombus 等形状，支持独立 Flag 写法（rhombus; 而非 shape=rhombus;）
    2. 修复了 shape=rhombus 会被强制保留 = 号的问题
    """
    if not style_str:
        return "", "empty"
    
    # 预清洗
    clean = style_str.strip()
    if clean.startswith('style="'):
        clean = clean[7:]
    clean = clean.strip('"').replace('\n', ' ').replace('&quot;', '')
    
    style_dict = {}
    parts = clean.split(';')
    
    # 1. 定义需要特殊处理的属性列表
    
    # Boolean属性：通常需要 =1
    boolean_attrs = {
        'rounded', 'html', 'whiteSpace', 'dashed', 'glass', 'shadow', 
        'sketch', 'curved', 'comic', 'orthogonalLoop'
    }
    
    # 独立形状 Flag：这些词如果出现，应该作为独立单词存在，不带等号
    # 用户特别指出了 rhombus，我们也把其他基础形状加进去以防万一
    standalone_shapes = {
        'rhombus', 'ellipse', 'triangle', 'hexagon', 'cloud', 
        'actor', 'cylinder', 'process', 'step', 'parallelogram',
        'doubleEllipse'
    }

    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        if '=' in part:
            # === 情况A: 标准键值对 (key=value) ===
            key, value = part.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            
            # 核心修正：拦截 shape=rhombus 这种写法
            # 如果 key 是 shape 且 value 是我们已知的独立形状
            if key == 'shape' and value in standalone_shapes:
                # 将其存为 None，表示这是一个无值的 Flag
                style_dict[value] = None
            else:
                # 颜色补全 # 号
                if (key.endswith('Color') or key in ['fill', 'stroke']) and value and value != 'none':
                    if re.match(r'^[0-9a-fA-F]{6}$', value):
                        value = '#' + value
                style_dict[key] = value
            
        else:
            # === 情况B: 孤立单词 (flags/shapes) ===
            
            # 1. 如果是独立形状 (如 rhombus) -> 存为 None (Flag)
            if part in standalone_shapes:
                style_dict[part] = None
            
            # 2. 如果是已知布尔属性 (如 rounded) -> 设为 1 (通常 mxGraph 需要 rounded=1)
            elif part in boolean_attrs:
                style_dict[part] = '1'
            
            # 3. 兜底策略：保留未知单词，设为 None 以保持原样（不加=1）
            elif re.match(r'^[a-zA-Z0-9_]+$', part):
                if part not in style_dict:
                    # 以前是设为 '1'，现在改为 None 以保持它是独立单词
                    # 除非你有把握它一定是布尔值，否则保持原样更安全
                    style_dict[part] = None

    # 重组 (Build String)
    if not style_dict:
        return "", "empty style"
    
    rebuilt_parts = []
    for k, v in style_dict.items():
        if v is None:
            # 如果值为 None，说明是独立 Flag，直接输出 Key (例如 "rhombus")
            rebuilt_parts.append(k)
        else:
            # 否则输出 Key=Value (例如 "rounded=1")
            rebuilt_parts.append(f"{k}={v}")
            
    rebuilt = ';'.join(rebuilt_parts) + ';'
    
    # 生成日志
    log = f"parsed {len(style_dict)} attributes"
    
    return rebuilt, log

def level2_dom_rebuild(content: str) -> Tuple[str, List[str]]:
    """
    Level 2: DOM重构 (增强版 v2.1)
    基于XML DOM解析，深度修复style属性、引用问题及页面定义
    
    新增功能(v2.1):
    1. 强制修复缺失 parent="1" 的孤儿元素（解决不显示问题）
    2. 强制修复缺失 edge="1" 的连线元素
    """
    fixes = []
    
    # 解析XML
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        raise Exception(f"DOM解析失败: {e}")

    # =======================================================
    # 修复 A: 补全 mxfile 版本号 (兼容性保障)
    # =======================================================
    if root.tag == 'mxfile':
        if 'host' not in root.attrib:
            root.attrib['host'] = 'Electron'
        if 'version' not in root.attrib:
            root.attrib['version'] = '24.0.0'
            fixes.append("补全了 mxfile 根节点的 version 属性")

    # =======================================================
    # 修复 B: 补全 mxGraphModel 页面定义 (解决打开空白的核心)
    # =======================================================
    graph_model = root.find(".//mxGraphModel")
    if graph_model is not None:
        default_attrs = {
            "dx": "1422", "dy": "794", "grid": "1", "gridSize": "10",
            "guides": "1", "tooltips": "1", "connect": "1", "arrows": "1",
            "fold": "1", "page": "1", "pageScale": "1", 
            "pageWidth": "827", "pageHeight": "1169",
            "math": "0", "shadow": "0"
        }
        model_fixed_count = 0
        for key, default_val in default_attrs.items():
            if key not in graph_model.attrib:
                graph_model.attrib[key] = default_val
                model_fixed_count += 1
        if model_fixed_count > 0:
            fixes.append(f"补全了 mxGraphModel 的 {model_fixed_count} 个页面属性")

    # =======================================================
    # 修复 C: 孤儿元素与连线属性修复 (v2.1 新增核心修复)
    # =======================================================
    all_cells = root.findall(".//mxCell")
    existing_ids = {cell.get('id') for cell in all_cells if cell.get('id')}
    
    parent_fixed_count = 0
    edge_flag_fixed_count = 0
    vertex_flag_fixed_count = 0
    
    for cell in all_cells:
        cell_id = cell.get('id')
        
        # 跳过根节点(0)和图层节点(1)
        if cell_id in ['0', '1']:
            continue
            
        # 1. 强制修复 parent="1"
        # 如果没有parent属性，或者parent属性为空，强制挂载到默认图层1
        if 'parent' not in cell.attrib or not cell.attrib['parent']:
            cell.attrib['parent'] = '1'
            parent_fixed_count += 1
            
        # 2. 智能识别并修复 edge="1"
        # 如果有source/target引用，或者样式里包含edgeStyle，它显然是一条线
        is_edge_logic = (cell.get('source') and cell.get('target')) or \
                        ('edgeStyle' in (cell.get('style') or ''))
        
        if is_edge_logic:
            if 'edge' not in cell.attrib:
                cell.attrib['edge'] = '1'
                edge_flag_fixed_count += 1
            # 确保边没有 vertex 属性 (互斥)
            if 'vertex' in cell.attrib:
                del cell.attrib['vertex']
        
        # 3. 智能识别并修复 vertex="1"
        # 如果不是边，且不是组(group)，通常默认为顶点
        elif 'vertex' not in cell.attrib and 'edge' not in cell.attrib:
            cell.attrib['vertex'] = '1'
            vertex_flag_fixed_count += 1

    if parent_fixed_count > 0:
        fixes.append(f"修复了 {parent_fixed_count} 个孤儿元素 (补全 parent='1')")
    if edge_flag_fixed_count > 0:
        fixes.append(f"修复了 {edge_flag_fixed_count} 个连线定义 (补全 edge='1')")
    if vertex_flag_fixed_count > 0:
        fixes.append(f"修复了 {vertex_flag_fixed_count} 个节点定义 (补全 vertex='1')")

    # =======================================================
    # 修复 D: Cell 样式与引用修复 (原有逻辑)
    # =======================================================
    fixes.append(f"检测到 {len(all_cells)} 个mxCell节点，{len(existing_ids)} 个有效ID")
    style_fixed_count = 0
    ref_removed_count = 0
    
    for cell in all_cells:
        # (1) Style属性标准化
        if 'style' in cell.attrib:
            original_style = cell.attrib['style']
            normalized_style, log = normalize_style_string(original_style)
            if original_style != normalized_style:
                cell.attrib['style'] = normalized_style
                style_fixed_count += 1
                if style_fixed_count <= 3:
                    fixes.append(f"标准化样式: {log}")
        
        # (2) 清理无效引用
        for ref_attr in ['source', 'target']:
            if ref_attr in cell.attrib:
                ref_id = cell.attrib[ref_attr]
                if ref_id not in existing_ids:
                    del cell.attrib[ref_attr]
                    ref_removed_count += 1
                    if ref_removed_count <= 3:
                        fixes.append(f"删除无效引用: {ref_attr}={ref_id}")
    
    if style_fixed_count > 3:
        fixes.append(f"总计标准化了 {style_fixed_count} 个样式属性")
    if ref_removed_count > 3:
        fixes.append(f"总计删除了 {ref_removed_count} 个无效引用")
    
    # 重新序列化
    new_content = ET.tostring(root, encoding='unicode')
    
    if '<?xml' in content and not new_content.startswith('<?xml'):
        new_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + new_content
    elif not new_content.startswith('<?xml'):
        new_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + new_content
        fixes.append("添加了缺失的 XML 头部声明")
    
    return new_content, fixes


# ============================================================================
# Level 3: lxml Recover兜底（可选）
# ============================================================================

def level3_lxml_recover(content: str) -> Tuple[str, List[str]]:
    """
    Level 3: lxml恢复模式
    使用lxml的recover模式处理严重损坏的XML
    
    注意：此功能需要安装lxml库
    pip install lxml
    """
    fixes = []
    
    try:
        from lxml import etree
    except ImportError:
        raise Exception("lxml库未安装，无法使用Level 3修复。请运行: pip install lxml")
    
    try:
        # 使用recover模式，尽可能修复损坏的XML
        parser = etree.XMLParser(
            recover=True,           # 恢复模式
            remove_blank_text=True, # 移除空白文本节点
            remove_comments=True    # 移除注释
        )
        tree = etree.fromstring(content.encode('utf-8'), parser=parser)
        
        # 检查parser的错误日志
        if parser.error_log:
            fixes.append(f"lxml检测到 {len(parser.error_log)} 个问题并尝试恢复")
            # 只显示前3个错误
            for i, error in enumerate(parser.error_log[:3]):
                fixes.append(f"  - {error.message}")
        
        # 重新序列化
        new_content = etree.tostring(
            tree, 
            encoding='unicode', 
            pretty_print=True,
            xml_declaration=True
        )
        
        fixes.append("使用lxml恢复模式成功修复严重损坏")
        return new_content, fixes
        
    except Exception as e:
        raise Exception(f"lxml恢复失败: {e}")


# ============================================================================
# 主修复函数
# ============================================================================

def fix_drawio_xml_v2(content: str) -> Dict:
    """
    混合策略修复Draw.io XML
    
    三级修复架构：
    - Level 1: 正则预处理（快速清洗）
    - Level 2: DOM重构（核心修复，推荐）
    - Level 3: lxml Recover（终极兜底）
    
    Returns:
        {
            'success': bool,           # 是否成功修复
            'fixed': bool,             # 是否进行了修改
            'content': str,            # 修复后的内容
            'fixes': List[str],        # 修复日志
            'level_used': str,         # 使用的修复级别
            'issues': List[str]        # 无法修复的问题
        }
    """
    result = {
        'success': False,
        'fixed': False,
        'content': content,
        'fixes': [],
        'level_used': None,
        'issues': []
    }
    
    original_content = content
    
    # ===== Level 1: 正则预处理 =====
    try:
        content, l1_fixes = level1_regex_cleanup(content)
        result['fixes'].extend([f"[L1] {fix}" for fix in l1_fixes])
        if l1_fixes:
            result['fixed'] = True
    except Exception as e:
        result['issues'].append(f"Level 1预处理错误: {e}")
        # 继续尝试后续级别
    
    # ===== Level 2: DOM重构（推荐）=====
    try:
        content, l2_fixes = level2_dom_rebuild(content)
        result['fixes'].extend([f"[L2] {fix}" for fix in l2_fixes])
        result['success'] = True
        result['level_used'] = 'DOM'
        result['fixed'] = True
        result['content'] = content
        return result
    except Exception as e:
        result['issues'].append(f"Level 2 DOM修复失败: {e}")
        # 继续尝试Level 3
    
    # ===== Level 3: lxml Recover兜底 =====
    try:
        content, l3_fixes = level3_lxml_recover(content)
        result['fixes'].extend([f"[L3] {fix}" for fix in l3_fixes])
        result['success'] = True
        result['level_used'] = 'LXML_RECOVER'
        result['fixed'] = True
        result['content'] = content
        return result
    except Exception as e:
        result['issues'].append(f"Level 3 lxml恢复失败: {e}")
    
    # ===== 所有修复策略均失败 =====
    result['success'] = False
    result['level_used'] = 'FAILED'
    result['content'] = original_content  # 返回原始内容
    result['issues'].append("所有修复策略均失败，文件可能严重损坏")
    
    return result


# ============================================================================
# 验证函数（从原始代码保留）
# ============================================================================

def validate_cell_ids(content: str) -> Tuple[bool, List[str]]:
    """验证cell ID的唯一性"""
    issues = []
    
    # 提取所有cell ID
    id_pattern = r'<mxCell\s+id="([^"]+)"'
    ids = re.findall(id_pattern, content)
    
    # 检查重复ID
    seen = set()
    duplicates = set()
    for cell_id in ids:
        if cell_id in seen:
            duplicates.add(cell_id)
        seen.add(cell_id)
    
    if duplicates:
        issues.append(f"发现重复的ID: {', '.join(duplicates)}")
        return False, issues
    
    return True, issues


def validate_references(content: str) -> Tuple[bool, List[str]]:
    """验证source/target引用的有效性"""
    issues = []
    
    # 提取所有cell ID
    id_pattern = r'<mxCell\s+id="([^"]+)"'
    valid_ids = set(re.findall(id_pattern, content))
    
    # 检查source引用
    source_pattern = r'source="([^"]+)"'
    sources = re.findall(source_pattern, content)
    invalid_sources = [s for s in sources if s not in valid_ids]
    if invalid_sources:
        issues.append(f"发现 {len(invalid_sources)} 个无效的source引用")
    
    # 检查target引用
    target_pattern = r'target="([^"]+)"'
    targets = re.findall(target_pattern, content)
    invalid_targets = [t for t in targets if t not in valid_ids]
    if invalid_targets:
        issues.append(f"发现 {len(invalid_targets)} 个无效的target引用")
    
    return len(issues) == 0, issues


# ============================================================================
# 文件处理函数（兼容原有接口）
# ============================================================================

def fix_drawio_xml(file_path: str) -> dict:
    """
    修正Draw.io XML文件（兼容原有接口）
    
    Args:
        file_path: 文件路径
    
    Returns:
        修正结果字典，包含:
        - success: 是否成功
        - fixed: 是否进行了修正
        - fixes: 修正列表
        - issues: 无法自动修正的问题列表
    """
    result = {
        'success': False,
        'fixed': False,
        'fixes': [],
        'issues': []
    }
    
    path = Path(file_path)
    
    # 检查文件是否存在
    if not path.exists():
        result['issues'].append(f"文件不存在: {file_path}")
        return result
    
    # 读取文件内容
    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        result['issues'].append(f"读取文件失败: {e}")
        return result
    
    # 使用新的修复函数
    repair_result = fix_drawio_xml_v2(content)
    
    # 转换结果格式
    result['success'] = repair_result['success']
    result['fixed'] = repair_result['fixed']
    result['fixes'] = repair_result['fixes']
    result['issues'] = repair_result['issues']
    
    # 如果修复成功，执行最终验证
    if result['success']:
        fixed_content = repair_result['content']
        
        # 验证cell ID
        ids_valid, id_issues = validate_cell_ids(fixed_content)
        if not ids_valid:
            result['issues'].extend(id_issues)
        
        # 验证引用（Level 2已经清理过，这里只是再次验证）
        refs_valid, ref_issues = validate_references(fixed_content)
        if not refs_valid:
            result['issues'].extend(ref_issues)
        
        # 保存修复后的文件
        if result['fixed']:
            try:
                path.write_text(fixed_content, encoding='utf-8')
                result['fixes'].append(f"使用 {repair_result['level_used']} 级别修复")
            except Exception as e:
                result['issues'].append(f"写入文件失败: {e}")
                result['success'] = False
                return result
    
    return result


# ============================================================================
# CLI接口
# ============================================================================

def main():
    if len(sys.argv) != 2:
        print("用法: python fix_drawio_xml.py <file_path>")
        print("\n这是Draw.io XML修复脚本 v2.0")
        print("采用三级修复策略：")
        print("  Level 1: 正则预处理（快速清洗）")
        print("  Level 2: DOM重构（核心修复）")
        print("  Level 3: lxml恢复（需要安装lxml库）")
        sys.exit(1)
    
    file_path = sys.argv[1]
    result = fix_drawio_xml(file_path)
    
    print(f"\n{'='*60}")
    print(f"Draw.io XML修正结果 v2.0")
    print(f"{'='*60}\n")
    
    if result['fixed']:
        print("✅ 已修正以下问题:")
        for fix in result['fixes']:
            print(f"  {fix}")
        print()
    
    if result['issues']:
        print("⚠️  发现以下问题:")
        for issue in result['issues']:
            print(f"  {issue}")
        print()
    
    if result['success']:
        if not result['fixed'] and not result['issues']:
            print("✅ 文件验证通过，无需修正")
        elif result['fixed'] and not result['issues']:
            print("✅ 文件已成功修正并保存")
        elif result['fixed'] and result['issues']:
            print("⚠️  文件已部分修正，但仍存在一些问题")
        print(f"\n文件路径: {file_path}")
    else:
        print("❌ 修正失败")
        print("\n建议：")
        print("  1. 检查XML文件是否严重损坏")
        print("  2. 尝试安装lxml库以启用Level 3修复: pip install lxml")
        print("  3. 如果问题持续，可能需要重新生成XML")
        sys.exit(1)


if __name__ == '__main__':
    main()
