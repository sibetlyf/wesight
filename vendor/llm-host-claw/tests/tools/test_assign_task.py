import pytest
import uuid
import os
from core.tools.assign_task import AssignTaskTools
from core.tools.shell import Shell
from configs.create_subagent import CreateSubagentConfig
from configs import AssignTaskConfig
from configs.shell import ShellConfig
from agno.agent import Agent
from agno.run.agent import ToolCallCompletedEvent
from protocol import EnVar



@pytest.fixture
def create_subagent_tools(workspace_prepare):
    # 创建配置
    cfg = CreateSubagentConfig(default_model="qwen3-next-80b")

    # 创建工具实例
    from core.abilities_loader import _load_core_tools
    yield _load_core_tools(cfgs=[cfg])[0]


@pytest.fixture
def assign_task_tools(workspace_prepare):
    # 创建配置
    cfg = AssignTaskConfig()

    # 创建工具实例
    yield AssignTaskTools(
        cfg=cfg,
        envar=EnVar.from_env(),
    )


@pytest.fixture
def shell_toolkit(workspace_prepare):
    # 创建配置
    cfg = ShellConfig()
    
    # 创建工具实例
    from core.abilities_loader import _load_core_tools
    yield _load_core_tools(cfgs=[cfg])[0]


@pytest.mark.asyncio
async def test_create_and_assign_task(create_subagent_tools, assign_task_tools, shell_toolkit, jt_model):
    """测试先创建诗人智能体，然后使用 assign_task 调用它"""
    # 从环境变量中读取工作空间路径
    workspace_path = EnVar.from_env().workspace
    assert workspace_path is not None, "WORKSPACE environment variable not set"
    
    # 创建 agent，同时包含创建智能体、分配任务和 Shell 工具
    ag = Agent(
        model=jt_model,
        tools=[create_subagent_tools, assign_task_tools, shell_toolkit],
        instructions="你很聪明，能够按照用户的要求创建智能体并分配任务，同时使用 Shell 工具保存文件",
        user_id="user1",
        debug_mode=True,
        add_history_to_context=True,
        stream_events=True,
        telemetry=False,
    )

    session_id = str(uuid.uuid4())
    tool_called_count = 0

    # 运行 agent，先创建诗人智能体，然后分配任务写 5 首诗并保存
    async for event in ag.arun(
        "请先创建一个专门写诗并保存诗的智能体并给它必要的工具，命名为 poet，然后使用 assign_task 工具让这个智能体写 5 首不同主题的诗并且保存，分别是：1. 春天 2. 夏天 3. 秋天 4. 冬天 5. 爱情。保存到 spring.txt、summer.txt、autumn.txt、winter.txt 和 love.txt",
        session_id=session_id,
        stream=True,
        yield_run_output=True,
    ):

        # 检查是否有工具调用完成的事件
        if isinstance(event, ToolCallCompletedEvent):
            tool_called_count += 1
            # 打印工具调用的结果
            print(f"Tool call completed: {event}")

    # 验证至少调用了多次工具（创建智能体、分配任务写 5 首诗、保存文件、读取文件）
    assert tool_called_count >= 6, "工具未被触发足够次数"
    
    # 验证诗人智能体文件是否创建成功
    poet_agent_path = os.path.join(workspace_path, "subagents", "poet.json")
    assert os.path.exists(poet_agent_path), "诗人智能体文件未创建成功"
    
    # 验证所有诗歌文件是否创建成功
    #tree一下目录构成并打印
    import subprocess
    tree_output = subprocess.run(["tree", workspace_path], check=True, capture_output=True, text=True)
    print(tree_output.stdout)

    poem_files = ["spring.txt", "summer.txt", "autumn.txt", "winter.txt", "love.txt"]
    for file_name in poem_files:
        file_path = os.path.join(workspace_path, "runs", file_name)
        assert os.path.exists(file_path), f"诗歌文件 {file_name} 未创建成功"
        # 读取并打印诗歌内容
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            print(f"\n{file_name} 内容：")
            print(content)