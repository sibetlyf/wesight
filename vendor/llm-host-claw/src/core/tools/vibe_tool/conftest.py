"""conftest.py - 自动将 src 目录加入 Python 路径，供该目录下的所有测试文件使用"""
import sys
from pathlib import Path

# src 目录：parents[0] = vibe_tool, [1] = tools, [2] = core, [3] = src
src_dir = str(Path(__file__).resolve().parents[3])
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
