from pydantic import Field
from typing import Literal
from .common import ToolkitConfigBase


class PublishArtifactConfig(ToolkitConfigBase):
    target: Literal["core.tools.publish_artifact.PublishArtifactTools"] = "core.tools.publish_artifact.PublishArtifactTools" #type: ignore
    