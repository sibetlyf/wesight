from pydantic import BaseModel, Field
import os
from typing import Optional, Union, List, Callable

from agno.db.mongo import AsyncMongoDb
from agno.db.sqlite import AsyncSqliteDb


class MongoConfig(BaseModel):
    db_name: str = Field(default="jt-llm-studio")
    session_collection: str = Field(description="mongo存储的集合名称")
    db_url: str = Field(...)

    def get_async_db(self) -> AsyncMongoDb:
        return AsyncMongoDb(**self.model_dump())


class SQLiteConfig(BaseModel):
    db_file: str = Field(default=".agno.db")

    def get_async_db(self) -> AsyncSqliteDb:
        import os

        self.db_file = os.path.join(os.environ["USERSPACE"], self.db_file)
        return AsyncSqliteDb(**self.model_dump())
