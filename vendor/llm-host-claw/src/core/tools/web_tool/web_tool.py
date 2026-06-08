from agno.run.base import RunContext
from agno.run.agent import RunOutputEvent, RunOutput
from agno.agent import Agent
from typing import Optional, AsyncIterator, override
from loguru import logger
import os
import re
from configs.web_tool import WebToolConfig
from lib import get_agno_agent_context_str
from agno.tools.toolkit import Toolkit
from protocol import ExternalAgentRunResponseContentEvent, EnVar
from agno.skills import Skills, LocalSkills
from core.tools.jt_tools import JtTools
from configs.jt_tools import JtToolsConfig


class WebTool(Toolkit):
    @override
    def __init__(
        self,
        cfg: WebToolConfig = WebToolConfig(),
        envar: Optional[EnVar] = None,
    ):
        self.envar = envar or EnVar.from_env()

        self.cfg = cfg
        self.user = self.envar.user_id
        self.record_id = self.envar.record_id
        self.api_key = self.envar.api_key

        super().__init__(
            tools=[self.web_generate],
            exclude_tools=self.cfg.exclude_tools,
        )

    def __initialize_agent(self, run_context: RunContext) -> Agent:

        # 模型初始化
        model = self.cfg.model.get_model(
            api_key=self.api_key,
        )

        # 创建智能体
        return Agent(
            name="webifier",
            model=model,
            skills=(
                None
                if not self.cfg.add_skill
                else Skills(
                    loaders=[
                        LocalSkills(
                            "src/core/tools/web_tools/skills/chart-visualization-web-generator/"
                        )
                    ]
                )
            ),
            id=f"webifier-{run_context.session_id}",
            user_id=run_context.user_id,
            session_id=f"webifier-{run_context.session_id}",
            description=self.cfg.description,
            instructions=(
                self.cfg.instructions
                if not self.cfg.add_skill
                else [
                    "用户需求是生成图表或者网页时，需要使用chart-visualization-web-generator来加载完整的生成指南，输出以markdown格式，直接给出完整单文件 `.html`源码，不省略任何技术细节，输出必须有```html     ```"
                ]
            ),
            expected_output=self.cfg.expected_output,
            tool_call_limit=self.cfg.tool_call_limit,
            # 写死配置项
            dependencies=None,  # 计划放文件上传等，跟随到用户输入下
            add_dependencies_to_context=True,
            telemetry=False,
        )

    async def __run(
        self,
        agent: Agent,
        run_context: RunContext,
        message: str,
        data: Optional[str] = None,
    ) -> AsyncIterator[RunOutputEvent]:
        if data:
            dependencies = f"<dependencies>网页制作的参考信息:\n{data}</dependencies>"
            message = f"{message}\n{dependencies}"
        async for event in agent.arun(
            input=message,
            stream=True,
            yield_run_output=True,
        ):
            yield event  # type: ignore

    def extract_html_content_re(self, raw_str):
        """
        用正则提取被```html和```包裹的HTML代码（兼容分隔符前后的空白）
        """
        # 正则匹配规则：忽略```html前后的空白，捕获中间所有内容直到```
        pattern = r"```html\s*(.*?)\s*```"
        # re.DOTALL 让.匹配换行符，re.S是re.DOTALL的简写
        match = re.search(pattern, raw_str, re.S)

        if match:
            return match.group(1).strip()  # group(1)是捕获的中间内容
        else:
            return ""  # 无匹配时返回空字符串

    def save_html(self, html_content: str, output_path: str, output_name: str):
        """
        保存HTML文件
        Args:
            html_content: HTML内容
            output_path: 输出路径
            output_name: 输出文件名
        """
        # 如果没有先创建文件夹
        if not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)

        html_content = self.extract_html_content_re(html_content)
        full_path = os.path.join(output_path, output_name)
        # print("文件保存路径",full_path)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(html_content)

    async def web_generate(
        self, run_context: RunContext, web_name: str, requirements: str
    ):
        """
        根据用户输入的网页生成需求，结合上下文信息设计网页内容并最终生成html网页至用户，支持基于用户提供或上下文中的数据进行网页构建。同时支持图表可视化，包含柱状图、折线图等以及mermaid图表。
        Args:
           web_name (str):网页名称，用于html文件的命名
           requirements  (str):网页设计需求、功能模块、UI组件、页面布局、视觉风格、色彩搭配等设计要素，使用文本描述即可，不要使用特殊字符。
        Returns:
            网页生成任务结果、生成的HTML文件路径
        """

        agent = self.__initialize_agent(run_context)
        if self.cfg.add_external_tools:
            jt_tool = JtTools(
                cfg=JtToolsConfig(), envar=self.envar, include_tools=["search_picture"]
            )
            agent.add_tool(jt_tool)

        data = (
            get_agno_agent_context_str(messages=run_context.messages or [])
            or None  # type: ignore
        )

        try:
            full_content = ""  # event收集
            async for event in self.__run(
                agent=agent,
                message=f"网页名称:{web_name}\n{requirements}",
                data=data,
                run_context=run_context,
            ):
                if isinstance(event, RunOutputEvent):
                    if event.content:
                        full_content += event.content
                    yield ExternalAgentRunResponseContentEvent(
                        type="content",
                        agent_id=run_context.session_id,
                        agent_name=run_context.session_id,
                        run_id=run_context.run_id,
                        session_id=run_context.session_id,
                        content="",
                        metadata=event,
                    )
            if full_content == "":  # 如果full_content为空，raise
                raise Exception("网页内容为空")

            output_path = self.envar.runspace
            output_name = f"{web_name}.html"
            self.save_html(full_content, output_path, output_name)

            yield ExternalAgentRunResponseContentEvent(
                type="content",
                agent_id=run_context.session_id,
                agent_name=run_context.session_id,
                run_id=run_context.run_id,
                session_id=run_context.session_id,
                content=f"代码已生成，文件保存至 {os.path.join(output_path, output_name)}。",
            )
            return
        except Exception as e:
            logger.exception(e)
            raise Exception(f"抱歉，网页生成遇到了错误:{e}")


async def web_generate_entrypoint(
    run_context: RunContext, task: str, envar: Optional[EnVar] = None
):
    """
    web_creator.md 的入口函数。
    由于 web_generate 需要 web_name 和 requirements，这里进行简单解析或使用默认值。
    """
    from configs.web_tool import WebToolConfig

    # 实例化 WebTool (使用默认配置)
    envar = envar or EnVar.from_env()
    toolkit = WebTool(cfg=WebToolConfig(), envar=envar)

    # 这里我们简单假设 web_name 为 "web_page"
    web_name = "web_page"
    requirements = task

    async for event in toolkit.web_generate(
        run_context=run_context, web_name=web_name, requirements=requirements
    ):
        yield event


if __name__ == "__main__":
    """测试 web_generate 方法"""
    import asyncio
    from unittest.mock import MagicMock
    import shutil
    from protocol import EnVar

    async def web_generate_test():
        """测试 web_generate 方法"""
        # 使用项目下的 workspace 目录作为工作目录
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(
            os.path.join(current_file_dir, "..", "..", "..", "..")
        )

        # 构建完整的目录结构：userspace/sessions/session_id/runs
        userspace = os.path.join(project_root, "workspace")
        sessionspace = os.path.join(userspace, "sessions")
        session_id = "session-1"
        workspace = os.path.join(sessionspace, session_id)
        runspace = os.path.join(workspace, "runs")

        # 创建测试目录
        if os.path.exists(userspace):
            shutil.rmtree(userspace)
        os.makedirs(runspace, exist_ok=True)

        print(f"工作目录: {workspace}")

        # 构建 EnVar
        envar = EnVar(
            userspace=userspace,
            sessionspace=sessionspace,
            workspace=workspace,
            runspace=runspace,
            user_id="test_user",
            record_id="test_record",
            authorization="test_auth",
        )

        # 将环境变量写入
        envar.to_env()
        envar.mkdirs()

        try:
            # 创建 WebTool 实例
            cfg = WebToolConfig()
            web_tools = WebTool(cfg=cfg, envar=envar)
            print("✓ WebTool 初始化成功")

            # 创建模拟的 RunContext
            run_context = MagicMock(spec=RunContext)
            run_context.session_id = "test_session_123"
            run_context.user_id = "test_user"
            run_context.run_id = "test_run_456"

            # 测试参数
            web_name = "图表"
            requirements = """生成一个空气净化器的网页"""

            # 设置 messages，用于 get_agno_agent_context_str
            from agno.agent import Message

            run_context.messages = [Message(role="user", content=requirements)]

            print(f"\n开始生成网页: {web_name}")
            print(f"需求: {requirements}")
            print("-" * 50)

            # 调用 web_generate
            events = []
            event_count = 0
            async for event in web_tools.web_generate(
                run_context=run_context, web_name=web_name, requirements=requirements
            ):
                events.append(event)
                event_count += 1

            print("-" * 50)
            print(f"✓ 测试完成，共收到 {len(events)} 个事件")

            # 验证生成的文件
            expected_file = os.path.join(runspace, f"{web_name}.html")
            if os.path.exists(expected_file):
                print(f"✓ HTML 文件已生成: {expected_file}")
                with open(expected_file, "r", encoding="utf-8") as f:
                    content = f.read()
                print(f"✓ 文件大小: {len(content)} 字符")
                print(f"\n文件位置: {expected_file}")
            else:
                print(f"✗ HTML 文件未生成: {expected_file}")

        except Exception as e:
            print(f"✗ 测试失败: {e}")
            import traceback

            traceback.print_exc()

        finally:
            print(f"\n工作目录保留在: {workspace}")
            print("(请手动删除该目录以清理)")

            # 清理环境变量
            for key in [
                "USERSPACE",
                "SESSIONSPACE",
                "WORKSPACE",
                "RUNSPACE",
                "USER_ID",
                "RECORD_ID",
                "AUTHORIZATION",
            ]:
                if key in os.environ:
                    del os.environ[key]

    # 运行测试
    asyncio.run(web_generate_test())
