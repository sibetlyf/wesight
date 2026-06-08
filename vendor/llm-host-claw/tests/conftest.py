import os
import shutil
import uuid
import sys
from pathlib import Path
from typing import Generator, Optional

import pytest
import yaml
from loguru import logger
from agno.models.openai import OpenAILike

from agno.models.base import Model
from configs import ModelConfig, OrchestratorConfig
from core.orchestrator import Orchestrator
from protocol import EnVar


@pytest.fixture
def workspace_prepare() -> Generator[None, None, None]:
    """
    创建临时工作目录用于测试

    设置以下环境变量:
    - USERSPACE: 用户空间目录
    - SESSIONSPACE: 会话空间目录
    - WORKSPACE: 当前工作空间目录
    - RUNSPACE: 运行空间目录
    - AGNO_DEBUG: 调试模式
    - USER_ID: 测试用户ID
    - RECORD_ID: 记录ID
    - AUTHORIZATION: 认证令牌
    - API_KEY: 模型API密钥

    """
    # 设置基础路径
    userspace = os.path.abspath("./.cache/userspace")

    # 清理上一次测试的结果
    if os.path.exists(userspace):
        shutil.rmtree(userspace)

    # 创建工作目录结构
    os.makedirs(userspace, exist_ok=True)

    sessionspace = os.path.join(userspace, "sessions")
    os.makedirs(sessionspace, exist_ok=True)

    session_id = str(uuid.uuid4())
    session_dir = os.path.join(sessionspace, session_id)
    os.makedirs(session_dir, exist_ok=True)

    runs_dir = os.path.join(session_dir, "runs")
    os.makedirs(runs_dir, exist_ok=True)

    # 设置环境变量
    os.environ.update(
        {
            "USERSPACE": userspace,
            "SESSIONSPACE": sessionspace,
            "WORKSPACE": session_dir,
            "RUNSPACE": runs_dir,
            "AGNO_DEBUG": "true",
            "USER_ID": "test_user",
            "RECORD_ID": str(uuid.uuid4()),
            "AUTHORIZATION": "ONLYUSEDINTOOL",  # 不再作为模型推理的认证凭据，而是作为工具调用的认证凭据
            # "API_KEY": "EMPTY", 全局字段，由于当前推理服务问题较多，无法统一设置API_KEY，改为在test_config.yaml中单独设置，因此这里注释掉了全局的API_KEY环境变量设置，之后上线会采用统一推理服务
        }
    )

    # 加载测试配置
    with open("tests/test_config.yaml", "r", encoding="utf-8") as f:
        test_config = yaml.safe_load(f)
    config = OrchestratorConfig.model_validate(test_config)
    config.to_env()

    # 配置日志
    logger.remove()
    logger.add(sys.stdout, level=os.environ.get("LOGURU_LEVEL", "INFO"))

    yield

    # 清理环境变量(保留测试结果目录)
    for key in ["USER_ID", "RECORD_ID", "AUTHORIZATION"]:
        os.environ.pop(key, None)


@pytest.fixture
def jt_model() -> Model:
    """创建测试模型"""
    return ModelConfig(id="qwen3-next-80b").get_model(api_key="EMPTY")


@pytest.fixture
def skills_loader(workspace_prepare: None) -> dict:
    """
    加载 skills (用于 skills 测试)

    注意: 在这里导入以避免循环依赖问题
    """
    # 添加 src 到路径
    src_path = str(Path(__file__).parent.parent / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    from core.abilities_loader import load_skills

    envar = EnVar.from_env()
    return load_skills(envar=envar)  # type: ignore


@pytest.fixture
def orchestrator_ready(workspace_prepare: None) -> Orchestrator:
    """创建已准备好的 Orchestrator 实例"""
    return Orchestrator()


@pytest.fixture
def test_file(workspace_prepare: None) -> str:
    """在 workspace/runs 下创建测试文件"""
    test_file_path = os.path.join(os.environ["WORKSPACE"], "runs", "mission.txt")
    with open(test_file_path, "w", encoding="utf-8") as f:
        f.write("写一首关于春天的诗,并保存下来")
    return test_file_path


@pytest.fixture
def langfuse_fixture() -> Generator[None, None, None]:
    """
    配置 Langfuse 追踪

    设置 Langfuse 环境变量并配置 OpenTelemetry 追踪
    """
    # 设置 Langfuse 凭据
    os.environ.update(
        {
            "LANGFUSE_SECRET_KEY": "sk-lf-test-secret",
            "LANGFUSE_PUBLIC_KEY": "pk-lf-test-public",
            "LANGFUSE_BASE_URL": "http://127.0.0.1:3000",
        }
    )

    # 导入追踪相关库
    import base64
    from openinference.instrumentation.agno import AgnoInstrumentor
    from opentelemetry import trace as trace_api
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    # 配置 Langfuse 认证
    langfuse_auth = base64.b64encode(
        f"{os.environ['LANGFUSE_PUBLIC_KEY']}:{os.environ['LANGFUSE_SECRET_KEY']}".encode()
    ).decode()

    os.environ.update(
        {
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:3000/api/public/otel",
            "OTEL_EXPORTER_OTLP_HEADERS": f"Authorization=Basic {langfuse_auth}",
        }
    )

    # 配置 Tracer Provider
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter()))
    trace_api.set_tracer_provider(tracer_provider=tracer_provider)

    # 启动 agno 追踪
    AgnoInstrumentor().instrument()  # type: ignore

    yield

    # 清理操作(如需要)
    pass
