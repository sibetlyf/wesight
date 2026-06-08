from pydantic import BaseModel, Field
import os
from typing import Any, Optional


class EnVar(BaseModel):
    """
    - 将 /.../<userspace> 路径写到 env 中的 USERSPACE 中
    - 将 /.../<userspace>/sessions/ 路径写到 env 中的 SESSIONSPACE 中
    - 将 /.../<userspace>/sessions/<session_id>/ 路径写到 env 中的 WORKSPACE 中
    - 将 /.../<userspace>/sessions/<session_id>/runs/ 路径写到 env 中的 RUNSPACE 中
    - 将 `{"user_id", "record_id", "authorization", "api_key"}` 分别存入 env 中的 USER_ID, RECORD_ID, AUTHORIZATION, API_KEY 中
    """

    userspace: str = Field(
        default_factory=lambda: os.environ["USERSPACE"], serialization_alias="USERSPACE"
    )
    sessionspace: str = Field(
        default_factory=lambda: os.environ["SESSIONSPACE"],
        serialization_alias="SESSIONSPACE",
    )
    workspace: str = Field(
        default_factory=lambda: os.environ["WORKSPACE"], serialization_alias="WORKSPACE"
    )
    runspace: str = Field(
        default_factory=lambda: os.environ["RUNSPACE"], serialization_alias="RUNSPACE"
    )

    user_id: str = Field(
        default_factory=lambda: os.environ["USER_ID"], serialization_alias="USER_ID"
    )
    record_id: str = Field(
        default_factory=lambda: os.environ["RECORD_ID"], serialization_alias="RECORD_ID"
    )
    authorization: str = Field(
        default_factory=lambda: os.environ["AUTHORIZATION"],
        serialization_alias="AUTHORIZATION",
    )
    api_key: Optional[str] = Field(
        default_factory=lambda: os.environ.get("API_KEY"),
        serialization_alias="API_KEY",
    )

    # post_init后校验路径
    def model_post_init(self, context: Any, /):
        """
        - 确保 sessionspace 在 userspace 下
        - 确保 workspace 在 sessionspace 下
        - 确保 runspace 在 workspace 下
        """
        assert self.sessionspace.startswith(self.userspace)
        assert self.workspace.startswith(self.sessionspace)
        assert self.runspace.startswith(self.workspace)

    @classmethod
    def from_env(cls) -> "EnVar":
        return cls()

    def to_env(self):
        for key, value in self.model_dump(by_alias=True).items():
            os.environ[key] = value

    def mkdirs(self):
        os.makedirs(self.userspace, exist_ok=True)
        os.makedirs(self.sessionspace, exist_ok=True)
        os.makedirs(self.workspace, exist_ok=True)
        os.makedirs(self.runspace, exist_ok=True)
