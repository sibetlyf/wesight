from typing import Optional

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    id: str = Field(..., description="模型id")
    provider: str = Field(
        default="openai", description="模型提供商，如 openai / deepseek"
    )
    base_url: str = Field(
        default="https://jiutian.10086.cn/largemodel/moma/api/v3",
        description="模型调用地址",
    )
    api_key: Optional[str] = Field(
        default=None, description="模型 API Key，可为空并在运行时注入"
    )
    extra_body: dict = Field(default_factory=dict, description="额外body")
    timeout: Optional[int] = Field(default=180, description="模型调用超时时间")

    max_tokens: Optional[int] = Field(default=None, description="模型生成内容长度")
    frequency_penalty: Optional[float] = Field(
        default=None, description="模型生成内容重复度，累积惩罚"
    )
    presence_penalty: Optional[float] = Field(
        default=None, description="模型生成内容重复度,一次性惩罚"
    )
    temperature: Optional[float] = Field(default=None, description="模型生成内容随机性")
    top_p: Optional[float] = Field(default=None, description="模型生成内容随机性")

    def _get_openailike_params(self, api_key: Optional[str] = None) -> dict:
        resolved_api_key = api_key or self.api_key or "EMPTY"
        return dict(
            id=self.id,
            api_key=resolved_api_key,
            base_url=self.base_url,
            extra_body=self.extra_body,
            timeout=self.timeout,
            max_tokens=self.max_tokens,
            frequency_penalty=self.frequency_penalty,
            presence_penalty=self.presence_penalty,
            temperature=self.temperature,
            top_p=self.top_p,
        )

    def get_model(
        self,
        *,
        api_key: Optional[str] = None,
    ):

        provider = self.provider.strip().lower()
        if provider == "deepseek":
            from agno.models.deepseek import DeepSeek

            return DeepSeek(**self._get_openailike_params(api_key=api_key))
        elif provider == "moonshot":
            from lib.models import FixMoonShot

            return FixMoonShot(**self._get_openailike_params(api_key=api_key))

        else:
            from agno.models.openai.chat import OpenAIChat

            return OpenAIChat(**self._get_openailike_params(api_key=api_key))
