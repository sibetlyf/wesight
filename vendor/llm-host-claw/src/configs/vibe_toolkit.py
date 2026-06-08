from configs.common import ModelConfig, ToolkitConfigBase
from typing import Literal, Optional, List
import os
import shutil
import json
import socket
import subprocess
from pathlib import Path
from moma_cli.sandbox import current_sandbox_manager



def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def find_available_port(start_port: int) -> int:
    port = start_port
    while is_port_in_use(port):
        port += 1
    return port


def get_ccr_status():
    """执行 ccr status 并返回输出内容"""
    try:
        prepared = current_sandbox_manager().prepare_spawn(
            argv=["cmd.exe", "/d", "/c", "ccr status"] if os.name == "nt" else ["/bin/bash", "-lc", "ccr status"],
            cwd=os.getcwd(),
            env=os.environ.copy(),
        )
        result = subprocess.run(prepared.argv, cwd=prepared.cwd, env=prepared.env, capture_output=True, text=True, encoding='utf-8')
        return result.stdout.lower()
    except Exception:
        return ""


def run_ccr_restart():
    try:
        print("🔄 正在执行 ccr restart 以确保配置加载成功...")
        prepared = current_sandbox_manager().prepare_spawn(
            argv=["cmd.exe", "/d", "/c", "ccr restart"] if os.name == "nt" else ["/bin/bash", "-lc", "ccr restart"],
            cwd=os.getcwd(),
            env=os.environ.copy(),
        )
        subprocess.run(prepared.argv, cwd=prepared.cwd, env=prepared.env, capture_output=True, text=True, encoding='utf-8')
        print("🚀 ccr 服务重启指令已发送")
    except Exception as e:
        print(f"❌ ccr restart 执行失败: {e}")


def ensure_claude_directory():
    """如果 ~/.claude 不存在，则从项目根目录复制 .claude"""
    claude_home = Path("~/.claude").expanduser()
    if not claude_home.exists():
        project_claude = Path('./claude')
        if project_claude.exists() and project_claude.is_dir():
            try:
                shutil.copytree(project_claude, claude_home)
            except Exception as e:
                print(f"❌ 复制 .claude 目录失败: {e}")


class VibeCodingToolkitConfig(ToolkitConfigBase):
    target: Literal[
        "core.tools.vibe_tool.vibe_toolkit.VibeCodingToolkit",
        "core.tools.vibe_tool.vibe_toolkit_v2.VibeCodingToolkit",
    ] = "core.tools.vibe_tool.vibe_toolkit.VibeCodingToolkit"
    agent_type: Literal["ccr", "opencode"] = "ccr"
    model: Optional[List[str]] = None
    actual_port: Optional[int] = None

    def model_post_init(self, __context) -> None:
        if self.agent_type == "ccr":
            self.generate_strict_config()
        elif self.agent_type == "opencode":
            self.generate_opencode_config()

    def generate_opencode_config(self):
        # 测试环境下跳过配置写入
        if os.getenv("TESTING") == "1":
            print("测试环境下跳过 opencode 配置写入")
            return

        jiutian_api_key = os.getenv("AUTHORIZATION")
        user_id = os.getenv("USER_ID")
        record_id = os.getenv("RECORD_ID")

        if not jiutian_api_key or not user_id or not record_id:
            print("❌ opencode 自动配置写入失败: 缺少环境变量")
            raise ValueError(f"缺少 opencode 自动配置环境变量: AUTHORIZATION={jiutian_api_key}, USER_ID={user_id}, RECORD_ID={record_id}")

        target_path = Path("~/.config/opencode/opencode.json").expanduser()
        if target_path.exists():
            return

        # 获取并处理 base_url，移除结尾的 /chat/completions 或 /chat
        base_url = os.getenv("JIUTIAN_BASE_URL", "https://jiutian.10086.cn/largemodel/moma/api/v3")
        base_url = base_url.rstrip("/")
        if base_url.endswith("/chat/completions"):
            base_url = base_url[:-17]
        elif base_url.endswith("/chat"):
            base_url = base_url[:-5]
        base_url = base_url.rstrip("/")

        config_dict = {
            "$schema": "https://opencode.ai/config.json",
            "plugin": [
                "oh-my-opencode"
            ],
            "provider": {
                "MOMA": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "JIUTIAN MOMA",
                    "options": {
                        "baseURL": base_url,
                        "apiKey": jiutian_api_key
                    },
                    "models": {
                        "qwen3.5-397B-fp8": {
                            "name": "qwen3.5",
                            "options": {
                                "sourceType": "klbase",
                                "auditSwitch": False,
                                "recordId": record_id,
                                "user":user_id
                            }
                        },
                        "jiutian-lan-35b": {
                            "name": "jiutian-lan",
                            "options": {
                                "sourceType": "klbase",
                                "auditSwitch": False,
                                "recordId": record_id,
                                "user":user_id
                            }
                        },
                        "glm-5-fp8": {
                            "name": "GLM5",
                                "options": {
                                "sourceType": "klbase",
                                "auditSwitch": False,
                                "recordId": record_id,
                                "user":user_id
                            }
                        },
                        "kimi-k2-5-thinking": {
                            "name": "kimi-k2.5",
                            "options": {
                                "sourceType": "klbase",
                                "auditSwitch": False,
                                "recordId": record_id,
                                "user":user_id
                            }
                        }
                    }
                }
            },
            "model": "MOMA/qwen3.5-397B-fp8"
        }

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
            print(f"✅ opencode 配置文件已自动初始化: {target_path}")
        except Exception as e:
            print(f"❌ opencode 自动配置写入失败: {e}")

    def generate_strict_config(self):
        # 测试环境下跳过配置写入
        if os.getenv("TESTING") == "1":
            print("测试环境下跳过配置写入") 
            return

        # 确保 .claude 目录存在
        ensure_claude_directory()

        jiutian_api_key = os.getenv("AUTHORIZATION")
        if not jiutian_api_key:
            return

        target_path = Path("~/.claude-code-router/config.json").expanduser()

        # 处理 models 列表
        models_env = os.getenv("JIUTIAN_MODELS", "qwen3.5-397B-fp8")
        models_list = [m.strip() for m in models_env.split(",")]

        if self.model:
            models_list = self.model
            router_default = f"jiutian, {self.model[0]}"
        else:
            router_default = os.getenv("ROUTER_DEFAULT", "jiutian,qwen3.5-397B-fp8")

        # 端口决策逻辑：检测 ccr status
        base_port = int(os.getenv("PORT", 3459))
        ccr_status = get_ccr_status()

        if "running" in ccr_status and is_port_in_use(base_port):
            self.actual_port = base_port
            print(f"ℹ️ 检测到 ccr 已在运行，继续沿用端口: {self.actual_port}")
        else:
            self.actual_port = find_available_port(base_port)
            if self.actual_port != base_port:
                print(f"⚠️ 端口 {base_port} 未激活或被占用，已自动切换至新端口: {self.actual_port}")

        config_dict = {
            "PORT": self.actual_port,
            "LOG": os.getenv("LOG", "true").lower() == "true",
            "LOG_LEVEL": os.getenv("LOG_LEVEL", "trace"),
            "Providers": [
                {
                    "name": "jiutian",
                    "api_base_url": os.getenv("JIUTIAN_BASE_URL",
                                              "https://jiutian.10086.cn/largemodel/moma/api/v3/chat/completions"),
                    "api_key": jiutian_api_key,
                    "models": models_list,
                    "transformer": {
                        "use": ["openrouter"]
                    }
                }
            ],
            "Router": {
                "default": router_default,
                "longContextThreshold": int(os.getenv("LONG_CONTEXT_THRESHOLD", 200000)),
            }
        }

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)

            print(f"✅ 配置文件已根据 VibeCodingToolkitConfig 实例化自动更新: {target_path}")
            run_ccr_restart()

        except Exception as e:
            print(f"❌ 自动配置写入失败: {e}")
