from agno.tools import Toolkit


from typing import List, Optional, Any, override
import os
import json

from configs import CreateSubagentConfig
from moma_cli.sandbox import ensure_within_root, sandbox_enabled
from protocol import SubAgentCard, EnVar


class CreateSubagentTools(Toolkit):
    _SUBAGENT_DIR = "subagents"
    _EXTRA_INSTRUCTIONS = """
# 工作目录规范
- 你可以访问工作目录，如果你需要存放文件，必须存放在 `{runspace}` 目录中，保存文件时使用绝对路径
- 存放文件后必须返回制品地址和摘要
"""

    @override
    def __init__(
        self,
        *,
        cfg: CreateSubagentConfig,
        envar: Optional[EnVar] = None,
        include_tools: Optional[List[str]] = None,
    ):

        self.envar = envar or EnVar.from_env()
        # 确保子智能体目录存在
        subagent_dir = f"{self.envar.workspace}/{self._SUBAGENT_DIR}"
        if sandbox_enabled():
            ensure_within_root(subagent_dir)
        os.makedirs(subagent_dir, exist_ok=True)

        self.cfg = cfg
        super().__init__(
            tools=[self.create_subagent], exclude_tools=self.cfg.exclude_tools
        )

    def create_subagent(
        self,
        name: str,
        description: str,
        instructions: str,
        tools: Optional[List[str]],
        skills: Optional[List[str]],
    ) -> dict:
        """
        创建一个子智能体，指定其名称、描述、指令，你可以制定该智能体可以使用的工具和技能
            - 尽可能的抽象通用的子智能体，然后多次调用该子智能体，每次分配不同的任务即可
            - 子智能体的指令必须包含对子智能体任务的指导和输出的要求，在无需存文件的时候，直接让其输出即可，输出文件优先选择 md 格式

        args:
            name (str): 子智能体的名称。
            description (str): 子智能体的简要描述。
            instructions (str): 你对子智能体的指令，包含对子智能体任务的指导和输出的要求
            tools (Optional[List[str]]): 子智能体可使用的工具列表，必须是你可以调用的 tools，可不填。
            skills (Optional[List[str]]): 子智能体具备的技能列表，必须是你可以调用的 skills，可不填。

        """
        # 保存
        self._save_agent(
            name=name,
            description=description,
            instructions=instructions,
            tools=tools or [],
            skills=skills or [],
        )
        return {
            "name": name,
            "description": description,
            "msg": f"创建子智能体{name}成功！你可以通过`assign_task`指令将任务分配给它",
        }

    def _save_agent(
        self,
        name: str,
        description: str,
        instructions: str,
        tools: List[str],
        skills: List[str],
    ):
        """
        保存子智能体的配置信息。

        args:
            name (str): 子智能体的名称。
            description (str): 子智能体的简要描述。
            instructions (str): 子智能体的指令。
            tools (List[str]): 子智能体可使用的工具列表。
            skills (List[str]): 子智能体具备的技能列表。
        """
        subagent_card = SubAgentCard(
            name=name,
            description=description,
            instructions=f"{instructions}\n{self._EXTRA_INSTRUCTIONS.format(runspace=self.envar.runspace)}",
            tools=tools,
            skills=skills,
        )
        target = f"{self.envar.workspace}/{self._SUBAGENT_DIR}/{name}.json"
        if sandbox_enabled():
            ensure_within_root(target)
        with open(target, "w") as f:
            json.dump(
                subagent_card.model_dump(exclude_none=True),
                f,
                indent=4,
                ensure_ascii=False,
            )
