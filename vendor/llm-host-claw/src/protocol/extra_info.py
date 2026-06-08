import uuid
from datetime import datetime

from pydantic import BaseModel, Field
from typing import Optional, Any, List


class Media(BaseModel):
    id: str = Field(
        default_factory=lambda x: f"media-{str(uuid.uuid4())}",
        description="媒体id, 保留",
        exclude=True,
    )
    url: str
    mime_type: Optional[str] = Field(
        default=None, description="媒体类型,若不提供将通过后缀猜测"
    )
    time: str = Field(
        default_factory=datetime.now().isoformat, description="媒体时间,保留"
    )

    def model_post_init(self, context: Any, /) -> None:
        # 根据文件后缀自动填充mime_type
        if self.mime_type is None:
            from xdg import Mime
            import mimetypes

            _mime_type = mimetypes.guess_type(self.url)[0] or str(
                Mime.get_type(self.url)
            )
            if _mime_type:
                self.mime_type = _mime_type
            else:
                from pathlib import Path

                self.mime_type = Path(self.url).suffix


class ExtraInfo(BaseModel):
    """
    额外的信息
    """

    current_time: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S %A"),
        description="当前时间，自动生成",
        serialization_alias="当前时间",
    )
    location: Optional[str] = Field(
        default=None, description="位置信息", serialization_alias="用户定位"
    )
    media: Optional[List[Media]] = Field(
        default=None, description="媒体信息", serialization_alias="用户上传"
    )

    def dump(self) -> Optional[dict]:
        if not self.media:
            self.media = None
        return self.model_dump(exclude_none=True, by_alias=True) or None

    def dump_json(self):
        import json

        return json.dumps(self.dump(), ensure_ascii=False, indent=4)
