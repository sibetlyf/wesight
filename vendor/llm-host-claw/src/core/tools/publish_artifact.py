from agno.tools import Toolkit
from typing import override
import os
from configs import PublishArtifactConfig
from protocol import EnVar


class PublishArtifactTools(Toolkit):
    @override
    def __init__(self, *, cfg: PublishArtifactConfig, envar: EnVar):

        self.envar = envar

        self.cfg = cfg

        super().__init__(
            tools=[self.publish_artifact], exclude_tools=self.cfg.exclude_tools
        )

    async def publish_artifact(self, artifact_path: str):
        """
        将workspace中的文件发布并展示给用户

        参数:
            artifact_path (str): 工件路径
        """

        # TODO 文件怎么转出去？
        return f"http://demo-url/{self.envar.runspace}/{artifact_path}"
