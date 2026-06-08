from itertools import chain
from agno.tools import Toolkit
from agno.agent import Agent
from agno.tools.function import Function
from agno.agent import RunOutputEvent, RunOutput

from typing import List, Dict, Literal, override
from pathlib import Path
from pydantic import BaseModel, Field
import json
import os
import aiofiles
import asyncio
import yaml
from networkx.algorithms.components import connected_components
from networkx.algorithms.dag import topological_sort
from networkx.classes.digraph import DiGraph
from agno.skills import Skills, LocalSkills
from agno.skills.utils import is_safe_path, read_file_safe, run_script


from configs import TodoConfig
from protocol import Plan, Step, ExternalAgentRunResponseContentEvent, EnVar

# 获取本文件路径
current_dir = os.path.dirname(os.path.abspath(__file__))


class SpecialSkills(Skills):
    @override
    def _get_skill_instructions(self, skill_name: str) -> str:
        """获取技能的完整指令

        Args:
            skill_name: 要获取指令的技能名称

        Returns:
            包含技能指令和元数据的 JSON 字符串
        """
        skill = self.get_skill(skill_name)
        if skill is None:
            available = ", ".join(self.get_skill_names())
            return json.dumps(
                {
                    "error": f"技能 '{skill_name}' 未找到",
                    "available_skills": available,
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "skill_name": skill.name,
                "description": skill.description,
                "instructions": skill.instructions,
                "available_scripts": skill.scripts,
                "available_references": skill.references,
            },
            ensure_ascii=False,
        )

    @override
    def _get_skill_reference(self, skill_name: str, reference_path: str) -> str:
        """从技能的参考文档中加载参考文档

        Args:
            skill_name: 技能名称
            reference_path: 参考文档的文件名

        Returns:
            包含参考文档内容的 JSON 字符串
        """
        skill = self.get_skill(skill_name)
        if skill is None:
            available = ", ".join(self.get_skill_names())
            return json.dumps(
                {
                    "error": f"技能 '{skill_name}' 未找到",
                    "available_skills": available,
                },
                ensure_ascii=False,
            )

        if reference_path not in skill.references:
            return json.dumps(
                {
                    "error": f"在技能 '{skill_name}' 中未找到参考文档 '{reference_path}'",
                    "available_references": skill.references,
                },
                ensure_ascii=False,
            )

        # 验证路径以防止路径遍历攻击
        refs_dir = Path(skill.source_path) / "references"
        if not is_safe_path(refs_dir, reference_path):
            return json.dumps(
                {
                    "error": f"无效的参考文档路径: '{reference_path}'",
                    "skill_name": skill_name,
                },
                ensure_ascii=False,
            )

        # 加载参考文档文件
        ref_file = refs_dir / reference_path
        try:
            content = read_file_safe(ref_file)
            return json.dumps(
                {
                    "skill_name": skill_name,
                    "reference_path": reference_path,
                    "content": content,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                {
                    "error": f"读取参考文档文件时出错: {e}",
                    "skill_name": skill_name,
                    "reference_path": reference_path,
                },
                ensure_ascii=False,
            )

    @override
    def get_system_prompt_snippet(self) -> str:
        """生成包含可用技能元数据的系统提示片段。

        这将创建一个 XML 格式的片段，为代理提供有关可用技能的信息，
        而不包含完整的指令。

        Returns:
            包含技能元数据的 XML 格式字符串。
        """
        if not self._skills:
            return ""

        lines = [
            "<skills_system>",
            "",
            "## 什么是技能？",
            "技能是扩展您能力的领域专业知识包。每个技能包含：",
            "- **指令**：关于技能的详细指导",
            "- **参考**：案例及示例",
            "",
            "## 重要：如何使用技能",
            "**技能名称不是可调用的函数。** 您不能直接通过技能名称调用技能。",
            "相反，您必须使用提供的技能访问工具：",
            "",
            "1. `get_skill_instructions(skill_name)` - 加载技能的完整指令",
            "2. `get_skill_reference(skill_name, reference_path)` - 访问特定文档",
            "",
            "## 渐进式发现工作流程",
            "1. **判断**：根据任务描述，判断该技能是否有帮助，如果没有帮助不要继续",
            "1. **浏览**：查看下面的技能摘要以了解可用内容",
            "2. **加载**：当任务与技能匹配时，首先调用 `get_skill_instructions(skill_name)`",
            "3. **参考**：根据需要使用 `get_skill_reference` 访问特定文档",
            "",
            "## 可用技能",
        ]
        for skill in self._skills.values():
            lines.append("<skill>")
            lines.append(f"  <name>{skill.name}</name>")
            lines.append(f"  <description>{skill.description}</description>")
            if skill.references:
                ref_names = [
                    r["name"] if isinstance(r, dict) else r for r in skill.references  # type: ignore
                ]
                lines.append(f"  <references>{', '.join(ref_names)}</references>")
            lines.append("</skill>")
        lines.append("")
        lines.append("</skills_system>")

        return "\n".join(lines)

    @override
    def get_tools(self) -> List[Function]:
        """获取用于访问技能的工具。

        Returns:
            代理可以用来访问技能的 Function 对象列表。
        """
        tools: List[Function] = []

        # Tool: get_skill_instructions
        tools.append(
            Function(
                name="get_skill_instructions",
                description="加载技能的完整指令。当您需要遵循技能的指导时使用。",
                entrypoint=self._get_skill_instructions,
            )
        )

        # Tool: get_skill_reference
        tools.append(
            Function(
                name="get_skill_reference",
                description="从技能的参考中加载参考文档。使用此工具访问详细文档。",
                entrypoint=self._get_skill_reference,
            )
        )

        return tools


class _OutputSchema(BaseModel):
    steps: List[Step]


class _TitleOutputSchema(BaseModel):
    title: str = Field(description="你给出的任务标题")


class TodoTools(Toolkit):
    _TODO_DIR = "todo"

    @override
    def __init__(
        self,
        *,
        cfg: TodoConfig,
        envar: EnVar,
    ):
        # 确保 todo 目录存在
        os.makedirs(f"{envar.workspace}/{self._TODO_DIR}", exist_ok=True)

        self.cfg = cfg
        self.envar = envar

        self.__todo_space = f"{envar.workspace}/{self._TODO_DIR}"

        # 池子
        self.plans: Dict[int, Plan] = self.__recover_plans()

        # 创建submit_todo
        submit_todo_tool = Function(
            name="submit_todo",
            description="提交规划结果，用于完成任务规划并写入待办事项",
            entrypoint=self._submit_todo,
            stop_after_tool_call=True,
        )

        model = cfg.model.get_model(
            api_key=self.envar.api_key,
        )
        self.__planner = Agent(
            model=model,
            name="planner",
            session_id=self.envar.record_id,
            description=cfg.description,
            instructions=cfg.instructions,
            # 写死配置项
            dependencies=None,
            add_history_to_context=True,
            parse_response=False,
            telemetry=False,
            tools=[submit_todo_tool],
            skills=SpecialSkills(loaders=[LocalSkills(path=f"{current_dir}/skills")]),
        )

        self.__title_generator = Agent(
            model=model,
            description=cfg.title_agent.description,
            instructions=cfg.title_agent.instructions,
            use_json_mode=True,
            output_schema=_TitleOutputSchema,
            telemetry=False,
            debug_mode=False,
        )

        super().__init__(
            tools=[self.write_todo, self.update_todo, self.modify_todo],
            exclude_tools=self.cfg.exclude_tools,
        )

    async def _submit_todo(self, steps: List[dict]):
        """
        提交规划结果，用于完成任务规划并写入待办事项

        Args:
            steps (List[dict]): 规划的步骤列表
        """
        # 任务拓扑
        tasks: list[list[Step]] = self.__organize_tasks(
            _OutputSchema.model_validate({"steps": steps})
        )

        _current_plan_num = len(self.plans) + 1
        for i, tg in enumerate(tasks):
            # 工具去重关联ability
            related_ability: list[str] = list(
                set(chain.from_iterable([i.tools or [] for i in tg]))
            )
            p = Plan.from_step(
                mission_id=i + _current_plan_num,
                title=await self.__get_task_title(tg),
                steps=tg,
                tools=related_ability,
            )
            self.plans[p.mission_id] = p

            # 同步写入计划，确保文件创建成功
            await self.__write_plan(p)
        return "Done!"

    def __organize_tasks(self, tasks: _OutputSchema) -> List[List[Step]]:
        """
        组织任务：按关联性分组，组内按依赖顺序排序

        参数:
            tasks: 任务列表，每个任务需包含"title"和可选的"dependencies"字段

        返回:
            分组排序后的任务列表: [[任务1, 任务2], [任务3], ...]
        """
        # 创建有向图
        G = DiGraph()

        # 添加所有节点（任务）
        for t in tasks.steps:
            # content去掉句号
            t.content = t.content.strip("。")
            title = t.title
            # 添加节点并存储完整任务对象
            G.add_node(title, task=t)
            # 存在依赖
            if t.dependencies:
                for dep in t.dependencies:
                    G.add_edge(dep, title)

        # 转换为无向图进行分组
        undirected_G = G.to_undirected()

        # 分组并排序
        organized_tasks = []
        for component in connected_components(undirected_G):
            # 处理组内任务排序
            subgraph = G.subgraph(component)  # type: ignore

            # 拓扑排序确保依赖顺序
            sorted_nodes = list(topological_sort(subgraph))  # type: ignore
            # 提取排序后的任务
            group = [G.nodes[node]["task"] for node in sorted_nodes]  # type: ignore
            organized_tasks.append(group)

        return organized_tasks

    async def __get_task_title(self, tasks: List[Step]) -> str:
        """
        获取任务标题
        """
        if len(tasks) > 1:
            try:
                steps = "\n".join(
                    [f"{i + 1}. {t.title}: {t.content}" for i, t in enumerate(tasks)]
                )
                message = [
                    {"role": "user", "content": f"以下是任务具体步骤：\n{steps}"}
                ]
                response: RunOutput = await self.__title_generator.arun(
                    message, stream=False
                )
                return response.content.title  # type: ignore
            except:
                return tasks[0].title
        else:
            return tasks[0].title

    def __recover_plans(self) -> Dict[int, Plan]:
        """
        从文件中恢复待办事项
        """
        plans: Dict[int, Plan] = {}
        for file in os.listdir(self.__todo_space):
            if file.endswith(".json"):
                with open(os.path.join(self.__todo_space, file), "r") as f:
                    plan = Plan(**json.load(f))
                    plans[plan.mission_id] = plan
        return plans

    async def __write_plan(self, plan: Plan):
        """
        写入文件
        Args:
            plan (Plan): 待办Object
        """
        import json

        async with aiofiles.open(
            os.path.join(self.__todo_space, f"{plan.title}.json"), "w"
        ) as f:
            await f.write(json.dumps(plan.model_dump(), ensure_ascii=False, indent=4))

    def __get_exist_yaml(self):
        return_plans = [
            plan.model_dump() for plan in self.plans.values() if not plan.done
        ]
        content = yaml.safe_dump_all(
            return_plans, default_flow_style=False, allow_unicode=True
        )
        # 确保返回非空字符串
        return content or "当前暂无计划生成或已完成所有计划"

    def __extract_tools_and_skills_from_agent(self, agent: Agent) -> str:
        """
        从agent中提取tools和skills
        """
        abilities: Dict[str, str] = {}
        for t in agent.tools:  # type: ignore
            for k, tool in t.functions.items():  # type: ignore
                tool.process_entrypoint(strict=True)
                abilities.update({tool.name: tool.description})  # type: ignore
            for k, tool in t.async_functions.items():  # type: ignore
                tool.process_entrypoint(strict=True)
                abilities.update({tool.name: tool.description})
        if agent.skills:
            for skill in agent.skills._skills.values():  # type: ignore
                abilities.update({skill.name: skill.description})  # type: ignore

        # 过滤掉未授权工具
        abilities = {
            k: v for k, v in abilities.items() if k not in self.cfg.unauthorization_tool
        }
        return "<可关联工具>\n{tools}\n</可关联工具>".format(
            tools="\n".join(
                [
                    f"  <{k.strip()}>{v.strip()}</{k.strip()}>"
                    for k, v in abilities.items()
                ]
            )
        )

    async def write_todo(self, agent: Agent, target: str, background: str = ""):
        """
        面对复杂需求时，使用此工具，为需求制定详细计划，并写入待办事项

        Args:
            target (str): 用户需求(目标)的描述，可以包含你的初步想法
            background (str): 背景信息，用于上下文,可选
        """
        if background:
            target = f"{target}\n背景介绍: {background}"
        target = (
            f"{target}\n\n"
            "你当前是任务规划器，不负责执行。"
            "你可调用的只有三类工具：`get_skill_instructions`、`get_skill_reference`、`submit_todo`。"
            "其中前两个仅用于按需加载经验，`submit_todo`必须作为最终动作且只调用一次。"
            "`available_tools`中的名称只能写入步骤的tools字段作为关联信息，绝不能直接调用。"
        )

        abilities: str = self.__extract_tools_and_skills_from_agent(agent)

        async for response in self.__planner.arun(
            input=target,
            stream=True,
            yield_run_output=True,
            session_state={"tools": abilities},
        ):
            if isinstance(response, RunOutputEvent):
                yield ExternalAgentRunResponseContentEvent(metadata=response)
        yield ExternalAgentRunResponseContentEvent(content=self.__get_exist_yaml())

    async def update_todo(
        self,
        mission_id: int,
        step_id: int,
        status: Literal["completed", "failed", "running"],
        summary: str,
    ):
        """
        更新已创建的 todo 列表

        Args:
            mission_id (int): 任务ID
            step_id (int): 步骤ID
            status (str): 更新后的状态，可选 completed, failed, running
            summary (str): 任务当前状态的概括
        """
        if mission_id in self.plans:
            p = self.plans[mission_id]
            for step in p.steps:
                if step.step_id == step_id:
                    step.status = status
                    break
            # 更新文件
            await self.__write_plan(p)
        # 返回所有未完成的计划
        result = self.__get_exist_yaml()
        return result

    async def modify_todo(
        self,
        mission_id: int,
        action: Literal["modify", "delete"] = "modify",
        modified_mission: str = "",
    ):
        """
        修改或删除单个mission，使用本工具你可以直接修改已经存在的mission

        Args:
            mission_id (int): 任务ID
            action (str): 操作类型，可选 "modify" 或 "delete"，默认为 "modify"
            modified_mission (str): 修改后的任务，你应该按照原始 yaml 格式输入所有步骤，例如：
                ```
                steps:
                - content: <修改后的内容>
                  dependencies:null
                  status:pending
                  step_id:1
                  title: <原始标题或者修改后的标题>
                  tools: null
                ```
        """
        if action == "delete":
            # 删除 plan
            if mission_id in self.plans:
                plan_to_delete = self.plans[mission_id]
                del self.plans[mission_id]
                # 删除文件
                file_path = os.path.join(
                    self.__todo_space, f"{plan_to_delete.title}.json"
                )
                if os.path.exists(file_path):
                    os.remove(file_path)
        else:
            # 修改 plan
            if mission_id in self.plans:
                existing_plan = self.plans[mission_id]
                _ = existing_plan.model_dump(exclude={"steps"})
                _.update(yaml.safe_load(modified_mission))
                self.plans[mission_id] = existing_plan.model_validate(_)
                # 更新文件
                asyncio.create_task(self.__write_plan(existing_plan))

        # 返回所有未完成的计划
        result = self.__get_exist_yaml()
        return result

    async def submit_todo(self, steps: List[Step]):
        """
        提交规划结果，用于完成任务规划并写入待办事项

        Args:
            steps (List[Step]): 规划的步骤列表
        """
        # 任务拓扑
        tasks: list[list[Step]] = self.__organize_tasks(_OutputSchema(steps=steps))
        _current_plan_num = len(self.plans) + 1
        for i, tg in enumerate(tasks):
            # 工具去重关联ability
            related_ability: list[str] = list(
                set(chain.from_iterable([i.tools or [] for i in tg]))
            )
            p = Plan.from_step(
                mission_id=i + _current_plan_num,
                title=await self.__get_task_title(tg),
                steps=tg,
                tools=related_ability,
            )
            self.plans[p.mission_id] = p

            # 同步写入计划，确保文件创建成功
            await self.__write_plan(p)

        # 返回所有未完成的计划
        return self.__get_exist_yaml()
