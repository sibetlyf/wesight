import pytest
import os
from core.tools.shell import Shell
from configs.shell import ShellConfig
from agno.agent import Agent
from agno.run.agent import ToolCallCompletedEvent
from core.abilities_loader import _load_core_tools


@pytest.fixture
def shell_toolkit(workspace_prepare):
    # 创建配置
    cfg = ShellConfig()
    
    
    # 创建工具实例
    yield _load_core_tools(cfgs=[cfg])[0]


@pytest.mark.asyncio
async def test_shell_command_execution(shell_toolkit):
    """测试 shell 命令执行功能"""
    # 执行简单的 ls 命令
    result = await shell_toolkit.shell("ls -la ~")
    print("Shell command output:", result)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_read_file(shell_toolkit):
    """测试文件读取功能"""
    # 先创建一个测试文件
    test_content = "Hello, World!"
    await shell_toolkit.write_file("test.txt", test_content)
    
    # 读取文件内容
    content = await shell_toolkit.read_file("test.txt")
    print("Read file content:", content)
    assert content == test_content


@pytest.mark.asyncio
async def test_write_file(shell_toolkit):
    """测试文件写入功能"""
    # 写入测试文件
    test_content = "Test content"
    result = await shell_toolkit.write_file("test_write.txt", test_content)
    print("Write file result:", result)
    assert result == "file written"
    
    # 验证文件存在且内容正确
    from protocol import EnVar
    full_path = os.path.join(EnVar.from_env().runspace, "test_write.txt")
    assert os.path.exists(full_path)
    with open(full_path, "r", encoding="utf-8") as f:
        file_content = f.read()
        print("File content:", file_content)
        assert file_content == test_content


@pytest.mark.asyncio
async def test_list_dir(shell_toolkit):
    """测试目录列出功能"""
    # 创建一些测试文件和目录
    await shell_toolkit.write_file("file1.txt", "content1")
    await shell_toolkit.write_file("file2.txt", "content2")
    
    # 列出目录内容
    files = await shell_toolkit.list_dir(".")
    print("List directory files:", files)
    assert isinstance(files, list)
    assert "file1.txt" in files
    assert "file2.txt" in files


@pytest.mark.asyncio
async def test_file_tree(shell_toolkit):
    """测试文件树功能"""
    # 创建测试文件和子目录
    await shell_toolkit.write_file("root_file.txt", "root content")
    await shell_toolkit.write_file("file.txt", "subdir content")
    
    # 生成文件树
    tree = await shell_toolkit.file_tree()
    print("File tree:", tree)
    assert isinstance(tree, str)
    assert "root_file.txt" in tree
    assert "file.txt" in tree


@pytest.mark.asyncio
async def test_search(shell_toolkit):
    """测试搜索功能"""
    # 创建包含特定内容的文件
    await shell_toolkit.write_file("search_test.txt", "Hello, this is a test for search functionality")
    
    # 搜索内容
    result = await shell_toolkit.search("search functionality")
    print("Search result:", result)
    assert isinstance(result, str)
    assert "search_test.txt" in result
    assert "search functionality" in result


@pytest.mark.asyncio
async def test_complete_workflow(shell_toolkit):
    """测试完整工作流：先列出文件，再把文件的第一行复制创建一个新的文件"""
    # 创建测试文件
    test_content = "First line\nSecond line\nThird line"
    await shell_toolkit.write_file("source.txt", test_content)
    print("Created source file with content:", test_content)
    
    # 列出文件
    files = await shell_toolkit.list_dir(".")
    print("Files in directory:", files)
    assert "source.txt" in files
    
    # 读取文件内容并获取第一行
    content = await shell_toolkit.read_file("source.txt")
    print("Source file content:", content)
    first_line = content.split("\n")[0]
    print("First line:", first_line)
    
    # 创建新文件并写入第一行
    await shell_toolkit.write_file("first_line.txt", first_line)
    print("Created first_line.txt with content:", first_line)
    
    # 验证新文件内容
    new_content = await shell_toolkit.read_file("first_line.txt")
    print("New file content:", new_content)
    assert new_content == first_line


@pytest.mark.asyncio
async def test_agno_agent_with_shell_tool(shell_toolkit, jt_model):
    """测试 agno agent 能够触发 Shell 工具"""
    # 创建 agent
    ag = Agent(
        model=jt_model,
        tools=[shell_toolkit],
        instructions="你很聪明，能够使用 shell 工具执行命令",
        user_id="user1",
        debug_mode=True,
        add_history_to_context=True,
        stream_events=True,
        telemetry=False,
    )

    tool_called = False

    # 运行 agent 并检查是否触发了工具
    async for event in ag.arun(
        "请列出当前目录的内容",
        stream=True,
        yield_run_output=True,
    ):

        # 检查是否有工具调用完成的事件
        if isinstance(event, ToolCallCompletedEvent):
            tool_called = True
            print("Tool called successfully!")

    # 验证工具被调用
    assert tool_called, "工具未被触发"
