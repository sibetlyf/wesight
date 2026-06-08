#!/usr/bin/env python3
"""
PPT Master 图像生成工具 - JtTools 版本
调用 src/core/tools/jt_tools 的 generate_image 方法生成图片
"""

import asyncio
import argparse
import sys
import os
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from core.tools.jt_tools import JtTools
from configs.jt_tools import JtToolsConfig
from protocol import EnVar


def parse_ratio(ratio_str: str) -> tuple[int, int]:
    """解析比例字符串为宽高"""
    ratio_map = {
        "1:1": (1024, 1024),
        "3:4": (768, 1024),
        "4:3": (1024, 768),
        "16:9": (1024, 576),
        "9:16": (576, 1024),
    }
    return ratio_map.get(ratio_str, (1024, 1024))


async def generate_image_jt(
    prompt: str,
    output_dir: str,
    aspect_ratio: str = "16:9",
    n: int = 1,
    style: int = 0,
    enhance: int = 1,
    watermark: int = 0,
) -> list[str]:
    """
    使用 JtTools.generate_image 生成图片
    
    Args:
        prompt: 图片生成提示词
        output_dir: 输出目录
        aspect_ratio: 图片比例 (1:1, 3:4, 4:3, 16:9, 9:16)
        n: 生成图片数量 (1-4)
        style: 风格 (0=base, 1=油画, 2=素描, 3=水彩)
        enhance: 是否扩写 (0=否, 1=是)
        watermark: 水印 (0=无, 1=有, 2=AI水印)
    
    Returns:
        生成的图片路径列表
    """
    # 获取环境变量
    envar = EnVar.from_env()
    
    # 创建 JtTools 实例
    cfg = JtToolsConfig()
    jt_tools = JtTools(cfg=cfg, envar=envar)
    
    # 解析比例
    width, height = parse_ratio(aspect_ratio)
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 调用 generate_image
    result = await jt_tools.generate_image(
        prompt=prompt,
        height=height,
        width=width,
        style_tag=style,
        n=n,
        txt2ImgRatio=aspect_ratio,
        enhance=enhance,
        watermark=watermark,
    )
    
    # 解析结果
    import json
    result_data = json.loads(result)
    
    images = result_data.get("images", [])
    content = result_data.get("content", "")
    
    if not images:
        print(f"警告: 未生成图片 - {content}")
        return []
    
    # 将图片移动到指定输出目录
    output_images = []
    for img_path in images:
        if os.path.exists(img_path):
            # 如果图片已经在目标目录，直接使用
            if os.path.dirname(img_path) == os.path.abspath(output_dir):
                output_images.append(img_path)
            else:
                # 复制到目标目录
                import shutil
                filename = os.path.basename(img_path)
                dest_path = os.path.join(output_dir, filename)
                shutil.copy2(img_path, dest_path)
                output_images.append(dest_path)
    
    return output_images


def main():
    parser = argparse.ArgumentParser(description="使用 JtTools 生成图片")
    parser.add_argument("prompt", help="图片生成提示词")
    parser.add_argument("-o", "--output", default=".", help="输出目录")
    parser.add_argument("--aspect_ratio", default="16:9", 
                        choices=["1:1", "3:4", "4:3", "16:9", "9:16"],
                        help="图片比例 (默认: 16:9)")
    parser.add_argument("-n", type=int, default=1, choices=[1, 2, 3, 4],
                        help="生成图片数量 (默认: 1)")
    parser.add_argument("--style", type=int, default=0, choices=[0, 1, 2, 3],
                        help="风格: 0=base, 1=油画, 2=素描, 3=水彩 (默认: 0)")
    parser.add_argument("--enhance", type=int, default=1, choices=[0, 1],
                        help="是否扩写: 0=否, 1=是 (默认: 1)")
    parser.add_argument("--watermark", type=int, default=0, choices=[0, 1, 2],
                        help="水印: 0=无, 1=有, 2=AI水印 (默认: 0)")
    
    args = parser.parse_args()
    
    # 运行异步生成
    images = asyncio.run(generate_image_jt(
        prompt=args.prompt,
        output_dir=args.output,
        aspect_ratio=args.aspect_ratio,
        n=args.n,
        style=args.style,
        enhance=args.enhance,
        watermark=args.watermark,
    ))
    
    if images:
        print(f"成功生成 {len(images)} 张图片:")
        for img in images:
            print(f"  - {img}")
    else:
        print("图片生成失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
