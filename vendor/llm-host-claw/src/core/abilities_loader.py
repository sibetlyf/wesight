from agno.tools import Toolkit
from agno.tools.mcp import MCPTools
from agno.agent import Agent
from agno.skills import LocalSkills
from lib.extended_local_skills import TurboSkills

from typing import List, Optional
import os
import importlib


from configs.common import ToolkitConfigBase
from protocol import MCPCard, SubAgentCard, EnVar


def _load_core_tools(
    *,
    cfgs: list[ToolkitConfigBase],
    envar: Optional[EnVar] = None,
) -> List[Toolkit]:  # type: ignore
    """
    根据传入的配置列表动态加载并实例化对应的 Toolkit 类。

    参数:
        cfgs (list[ToolkitConfigBase]): Toolkit 配置列表，每个元素需包含 target 字段，格式为 "模块路径.类名"。
        envar (Optional[EnVar], optional): 环境变量配置，用于 Toolkit 初始化。

    返回:
        list[Toolkit]: 实例化后的 Toolkit 对象列表。
    """
    envar = envar or EnVar.from_env()

    ability: List[Toolkit] = []
    for tool in cfgs:
        module_path, class_name = tool.target.rsplit(".", 1)
        module = importlib.import_module(module_path)
        instance_hook = getattr(module, class_name)
        ability.append(instance_hook(cfg=tool, envar=envar))
    return ability


def _load_workspace_tools(
    *,
    envar: Optional[EnVar] = None,
) -> List[MCPTools]:
    """
    加载额外的 Toolkit 配置。

    参数:
        envar (Optional[EnVar], optional): 环境变量配置，用于 Toolkit 初始化。
    返回:
        list[MCPTools]: 实例化后的 MCPTools 对象列表。
    """
    tools: List[MCPTools] = []
    # 遍历workspaces/tools 下面的所有 json，实例化 mcptools
    envar = envar or EnVar.from_env()

    tools_dir = os.path.join(envar.workspace, "tools")
    if os.path.exists(tools_dir):
        for cfg_file in os.listdir(tools_dir):
            if cfg_file.endswith(".json"):
                cfg_path = os.path.join(tools_dir, cfg_file)
                with open(cfg_path, "r") as f:
                    cfg: MCPCard = MCPCard.model_validate_json(f.read())
                tools.append(
                    MCPTools(
                        transport=cfg.transport, server_params=cfg.agno_server_params
                    )
                )

    return tools


def load_tools(
    *,
    cfgs: list[ToolkitConfigBase],
    envar: Optional[EnVar] = None,
    exclude_tools: list[str] = [],
) -> List[Toolkit]:
    """
    加载所有工具。

    参数:
        cfgs (list[ToolkitConfigBase]): Toolkit 配置列表，每个元素需包含 target 字段，格式为 "模块路径.类名"。
        envar (Optional[EnVar], optional): 环境变量配置，用于 Toolkit 初始化。
        exclude_tools (list[str]): 要排除的工具名称列表，默认值为空列表。

    返回:
        list[Toolkit]: 实例化后的 Toolkit 对象列表。
    """
    envar = envar or EnVar.from_env()
    core_tools = _load_core_tools(
        cfgs=cfgs,
        envar=envar,
    )
    workspace_tools = _load_workspace_tools(envar=envar)
    all_tools = core_tools + workspace_tools
    # 过滤
    for kit in all_tools:
        kit.exclude_tools = kit.exclude_tools or []
        excludes = list(
            set([kit._get_tool_name(t) for t in kit.tools]) & set(exclude_tools)
        )
        if excludes:
            kit.exclude_tools.extend(excludes)
            kit.functions.clear()
            kit.async_functions.clear()
            if kit.tools:
                kit._register_tools()
            if kit._async_tools:
                kit._register_async_tools()

    return all_tools


def load_skills(
    *,
    envar: Optional[EnVar] = None,
) -> TurboSkills:
    """
    加载额外的 Skill 配置。

    参数:
        envar (Optional[EnVar], optional): 环境变量配置，用于 Skill 初始化。
    返回:
        Skills: 实例化后的 Skill 对象。
    """
    envar = envar or EnVar.from_env()
    # 载入用户传入 skills 及 agents 及工具
    skills_loaders: list[LocalSkills] = [
        LocalSkills("src/core/skills"),
    ]

    # userspace 下面的 skills 目录
    if os.path.exists(os.path.join(envar.userspace, "skills")):
        skills_loaders.append(LocalSkills(os.path.join(envar.userspace, "skills")))
    # 只有当 workspace/skills 目录存在时才添加
    if os.path.exists(os.path.join(envar.workspace, "skills")):
        skills_loaders.append(LocalSkills(os.path.join(envar.workspace, "skills")))

    return TurboSkills(loaders=skills_loaders)  # type: ignore


def _parse_md_agent(cfg_path: str) -> Optional[SubAgentCard]:
    """解析 Markdown 格式的智能体定义文件。"""
    import yaml

    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.startswith("---"):
            return None

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        metadata = yaml.safe_load(parts[1])
        instructions = parts[2].strip()

        # 处理 tools 和 skills，确保它们是列表
        tools = metadata.get("tools", [])
        if isinstance(tools, dict):
            # 如果是字典（如 web_creator.md 中的格式），取 key 为 True 的或全部 key
            tools = [k for k, v in tools.items() if v is True or v == "true"]

        skills = metadata.get("skills", [])
        if not isinstance(skills, list):
            skills = []
        # 过滤掉空的技能项
        skills = [str(s) for s in skills if s is not None]

        raw_mode = metadata.get("mode") or metadata.get("agent_mode") or "subagent"
        agent_mode_init = {"mode": raw_mode} if isinstance(raw_mode, str) else raw_mode

        return SubAgentCard(
            name=metadata.get("name", os.path.splitext(os.path.basename(cfg_path))[0]),
            description=metadata.get("description", ""),
            instructions=instructions,
            tools=tools,
            skills=skills,
            model=metadata.get("model") if metadata.get("model") else None,
            agent_mode=agent_mode_init,
            entrypoint=metadata.get("entrypoint"),
            entrypoint_params=metadata.get("entrypoint_params"),
            extra=metadata,
        )
    except Exception as e:
        print(f"Error parsing agent markdown {cfg_path}: {e}")
        return None


def load_subagent_cards(*, envar: Optional[EnVar] = None) -> List[SubAgentCard]:
    """
    加载额外的 SubAgent 配置。支持多级目录搜索和 .json/.md 格式。

    参数:
        envar (Optional[EnVar], optional): 环境变量配置，用于 SubAgent 初始化。
    返回:
        list[SubAgentCard]: 包含 SubAgent 配置的字典列表。
    """
    envar = envar or EnVar.from_env()
    subagents: List[SubAgentCard] = []

    # 搜索路径：workspace/subagents 和 src/core/agents
    search_dirs = [os.path.join(envar.workspace, "subagents"), "src/core/agents"]

    for base_dir in search_dirs:
        if not os.path.exists(base_dir):
            continue

        for root, _, files in os.walk(base_dir):
            for cfg_file in files:
                cfg_path = os.path.join(root, cfg_file)
                if cfg_file.endswith(".json"):
                    try:
                        with open(cfg_path, "r", encoding="utf-8") as f:
                            cfg = SubAgentCard.model_validate_json(f.read())
                        subagents.append(cfg)
                    except Exception as e:
                        print(f"Error loading agent json {cfg_path}: {e}")
                elif cfg_file.endswith(".md"):
                    card = _parse_md_agent(cfg_path)
                    if card:
                        subagents.append(card)

    return subagents
