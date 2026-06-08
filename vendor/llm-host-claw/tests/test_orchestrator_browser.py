from agno.models.openai import OpenAILike
import os
import pytest

from core.orchestrator import Orchestrator
from protocol import ExtraInfo


def tree_workspace():
    # shell tree打印一下workspace路径结构
    import platform
    if platform.system() == "Windows":
        os.system('tree /A /F "{}"'.format(os.environ["WORKSPACE"]))
    else:
        os.system('tree -a "{}"'.format(os.environ["WORKSPACE"]))


@pytest.fixture
def custom_browser_orchestrator(workspace_prepare):
    from configs import OrchestratorConfig
    import yaml

    with open("tests/test_config.yaml", 'r', encoding='utf-8') as f:
        test_config = yaml.safe_load(f)

    test_config["model"] = {
        "id": "qwen3.5-397B-fp8",
        "base_url": "https://example.com/v1",
        "api_key": "TEST_API_KEY"
    }

    if "toolkits" in test_config:
        test_config["toolkits"] = [
            tk for tk in test_config["toolkits"]
            if "jt_tools" not in tk.get("target", "")
        ]

    config = OrchestratorConfig.model_validate(test_config)
    config.to_env()

    os.environ["AUTHORIZATION"] = test_config["model"].get("api_key")
    orch = Orchestrator()
    model = OpenAILike(
        id=test_config["model"].get("id"),
        base_url=test_config["model"].get("base_url"),
        api_key=test_config["model"].get("api_key")
    )

    orch.model = model
    orch.agent.model = model

    return orch


@pytest.mark.asyncio
async def test_orchestrator_base(custom_browser_orchestrator):
    orchestrator: Orchestrator = custom_browser_orchestrator
    tree_workspace()
    extra = ExtraInfo()
    async for i in orchestrator.run("打开百度搜索张雪峰，告诉我他的生平履历", extra=extra):
        if hasattr(i, "metadata") and i.metadata is not None:
            meta_content = getattr(i.metadata, "content", None)
            if meta_content:
                print('=' * 100)
                print(meta_content)
                print('=' * 100)
    tree_workspace()
