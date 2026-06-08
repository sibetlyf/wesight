import os
import pytest
import json
from agno.agent import Agent

from configs import TodoConfig, ModelConfig
from core.tools.todo_tool import TodoTools
from core.tools.shell import Shell,ShellConfig
from core.abilities_loader import _load_core_tools



@pytest.mark.asyncio
async def test_write_todo(orchestrator_ready):
    """测试 write_todo 方法"""

    agent = orchestrator_ready.agent
    # 创建 todo 工具
    todo_config = TodoConfig(
        model=ModelConfig(id="glm-5.1"),
        # model=ModelConfig(id="glm-5.1",base_url="https://jiutian.10086.cn/largemodel/moma/api/v3"),
        unauthorization_tool=["assign_task", "create_subagent", "publish_artifact"]
    )
    todo_tools = _load_core_tools(cfgs=[todo_config])[0]
    
    # 测试 write_todo

    target = "制定一个51去北京旅游的计划"
    background=""
    
    # 调用 write_todo 方法
    results = []
    async for event in todo_tools.write_todo(agent, target=target, background=background): #type: ignore
        results.append(event)
    print(results[-1])
    
    # 验证 todo 文件是否创建成功
    todo_dir = os.path.join(os.environ["WORKSPACE"], "todo")
    
    # 打印目录内容，查看实际创建的文件
    print(f"Todo 目录路径: {todo_dir}")
    if os.path.exists(todo_dir):
        todo_files = [f for f in os.listdir(todo_dir) if f.endswith('.json')]
        print(f"Todo 目录内容: {os.listdir(todo_dir)}")
        assert len(todo_files) > 0, "Todo 文件未创建"
        
        # 打印输出路径和内容
        for todo_file in todo_files:
            todo_file_path = os.path.join(todo_dir, todo_file)
            print(f"Todo 文件路径: {todo_file_path}")
            
            # 读取并打印 todo 文件内容
            with open(todo_file_path, "r", encoding="utf-8") as f:
                todo_content = json.load(f)
            print(f"Todo 文件内容: {json.dumps(todo_content, ensure_ascii=False, indent=2)}")
    else:
        print("Todo 目录不存在")
        assert False, "Todo 目录未创建"
    


@pytest.mark.asyncio
async def test_update_todo(workspace_prepare):
    """测试 update_todo 方法"""

    
    # 创建 todo 工具
    todo_config = TodoConfig(
        model=ModelConfig(id="qwen3-next-80b"),
        exclude_tools=[],
        unauthorization_tool=["assign_task", "create_subagent", "publish_artifact"]
    )
    from protocol import EnVar

    title = "创建诗歌文件"
    target = "帮我创建 A.txt 和 B.txt，在里面分别写 2 首诗"
    
    # 创建 todo 目录结构
    todo_dir = os.path.join(os.environ["WORKSPACE"], "todo")
    os.makedirs(todo_dir, exist_ok=True)
    
    # 创建 todo 数据
    todo_data = {
        "mission_id": 1,
        "title": title,
        "steps": [
            {
                "step_id": 1,
                "title": "创建 A.txt 文件",
                "content": "创建 A.txt 文件，并在其中写入一首诗歌。",
                "tools": ["shell"],
                "status": "pending"
            },
            {
                "step_id": 2,
                "title": "创建 B.txt 文件",
                "content": "创建 B.txt 文件，并在其中写入一首诗歌。",
                "tools": ["shell"],
                "status": "pending"
            }
        ],
        "tools": ["shell"],
        "done": False
    }
    
    # 写入 todo 文件
    todo_file_path = os.path.join(todo_dir, f"{title}.json")
    with open(todo_file_path, "w", encoding="utf-8") as f:
        json.dump(todo_data, f, ensure_ascii=False, indent=4)

    todo_tools = TodoTools(cfg=todo_config, envar=EnVar.from_env())
    
    # 测试 update_todo
    # 更新第一个步骤为完成
    update_result = await todo_tools.update_todo(
        mission_id=1,  # mission_id 为 1
        step_id=1,     # 第一个步骤的 step_id 为 1
        status="completed",
        summary="已成功创建 A.txt 并写入诗歌"
    )
    assert update_result, "更新任务状态失败"
    
    # 读取更新后的 todo 文件，查看状态
    with open(todo_file_path, "r", encoding="utf-8") as f:
        updated_data = json.load(f)
    print(f"第一次更新后，步骤 1 的状态: {updated_data['steps'][0]['status']}")
    print(f"第一次更新后，步骤 2 的状态: {updated_data['steps'][1]['status']}")
    
    # 更新第二个步骤为完成
    update_result = await todo_tools.update_todo(
        mission_id=1,  # mission_id 为 1
        step_id=2,     # 第二个步骤的 step_id 为 2
        status="completed",
        summary="已成功创建 B.txt 并写入诗歌"
    )
    assert update_result, "更新任务状态失败"
    
    # 读取更新后的 todo 文件，查看状态
    with open(todo_file_path, "r", encoding="utf-8") as f:
        updated_data = json.load(f)
    print(f"第二次更新后，步骤 1 的状态: {updated_data['steps'][0]['status']}")
    print(f"第二次更新后，步骤 2 的状态: {updated_data['steps'][1]['status']}")


@pytest.mark.asyncio
async def test_modify_todo(workspace_prepare):
    """测试 modify_todo 方法"""
    
    # 创建 todo 工具
    todo_config = TodoConfig(
        model=ModelConfig(id="qwen3-next-80b"),
        exclude_tools=[],
        unauthorization_tool=["assign_task", "create_subagent", "publish_artifact"]
    )
    from protocol import EnVar

    
    # 手动创建 todo 文件
    title = "测试任务"
    
    # 创建 todo 目录结构
    todo_dir = os.path.join(os.environ["WORKSPACE"], "todo")
    os.makedirs(todo_dir, exist_ok=True)
    
    # 创建测试用的 plan 数据
    test_plan = {
        "mission_id": 1,
        "title": title,
        "steps": [
            {
                "step_id": 1,
                "title": "步骤1",
                "content": "完成步骤1",
                "tools": ["shell"],
                "status": "pending"
            },
            {
                "step_id": 2,
                "title": "步骤2",
                "content": "完成步骤2",
                "tools": ["shell"],
                "status": "pending"
            }
        ],
        "tools": ["shell"],
        "done": False
    }
    
    # 写入 plan 文件
    plan_file_path = os.path.join(todo_dir, f"{title}.json")
    with open(plan_file_path, "w", encoding="utf-8") as f:
        json.dump(test_plan, f, ensure_ascii=False, indent=4)
    
    todo_tools = TodoTools(cfg=todo_config, envar=EnVar.from_env())
    
    # 测试修改 plan
    modified_mission = """
steps:
- content: 完成步骤1和步骤2的合并任务
  dependencies: null
  status: pending
  step_id: 1
  title: 测试任务
  tools: null
"""
    modify_result = await todo_tools.modify_todo(1, "modify", modified_mission)
    print("修改 plan 结果:")
    print(modify_result)
    assert modify_result, "修改 plan 失败"
    
    # 测试删除 plan
    delete_result = await todo_tools.modify_todo(1, "delete")
    assert delete_result, "删除 plan 失败"
    
    # 验证删除是否成功
    assert not os.path.exists(plan_file_path), "plan 文件未被删除"
    assert len(todo_tools.plans) == 0, "plan 未从内存中删除"
