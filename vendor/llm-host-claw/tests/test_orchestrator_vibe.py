import pytest
from protocol import ExtraInfo
from core.orchestrator import Orchestrator
import os

def tree_workspace():
    #shell tree打印一下workspace路径结构
    import platform
    if platform.system() == "Windows":
        os.system('tree /A /F "{}"'.format(os.environ["WORKSPACE"]))
    else:
        os.system('tree -a "{}"'.format(os.environ["WORKSPACE"]))

@pytest.fixture
def custom_vibe_orchestrator(workspace_prepare):
    from configs import OrchestratorConfig
    import yaml
    
    with open("tests/test_config.yaml", 'r', encoding='utf-8') as f:
        test_config = yaml.safe_load(f)
        
    # test_config["model"] = {
    #     "id": "qwen3.5-plus",  
    #     "base_url": "https://example.com/v1",
    #     "api_key": "TEST_API_KEY"
    # }
    
    if "toolkits" in test_config:
        test_config["toolkits"] = [
            tk for tk in test_config["toolkits"]
            if "jt_tools" not in tk.get("target", "")
        ]

    config = OrchestratorConfig.model_validate(test_config)
    config.to_env()
    
    # 因为 Orchestrator 内部强制读取 os.environ["AUTHORIZATION"] 作为 api_key
    # 所以要让它不报错，我们也可以顺手覆盖一下环境变量
    os.environ["AUTHORIZATION"] = test_config["model"].get("api_key", "123")
    
    orch = Orchestrator()
    
    # 因为用户要求不接入 jt_model，而 Orchestrator() 的 __init__ 是写死初始化 JtOpenAILike 的
    # 这里我们暴力把创建好之后的 orchestrator 内部模型替换成原生的 OpenAILike
    from agno.models.openai import OpenAILike
    pure_model = OpenAILike(
        id=test_config["model"].get("id", "qwen3.5-397B-fp8"),
        base_url=test_config["model"].get("base_url", "https://example.com/v1"),
        api_key=test_config["model"].get("api_key", "TEST_API_KEY")
    )
    
    orch.model = pure_model
    orch.agent.model = pure_model
    
    return orch

@pytest.mark.asyncio
async def test_orchestrator_base(custom_vibe_orchestrator):
    # 测试 Orchestrator 类
    orchestrator: Orchestrator = custom_vibe_orchestrator
    tree_workspace()
    extra = ExtraInfo()
    async for i in orchestrator.run("""
    帮我制作一个商业AI公司的发布会官网项目，该项目需要一个超越苹果官网的前端，以及一个与官网联动的HTML格式的发布会幻灯片。具体的内容和文案等你自行设计，但需要完全超越苹果等竞品，达到令人震撼的视听效果，且图片和
    此外，还需要生成一个极为专业且具备视觉震撼力和表现力的HTML格式的幻灯片。你的所有成品都需要图表、配图、文字、等元素。""", 
    extra=extra):
        if hasattr(i, "metadata") and i.metadata is not None:
            meta_content = getattr(i.metadata, "content", None)
            if meta_content:
                print('='*100)
                print(meta_content)
                print('='*100)
    tree_workspace()
