from typing import List, Literal
from .common import ToolkitConfigBase

class ShellConfig(ToolkitConfigBase):
    """
    Shell toolkit configuration.
    """
    target: Literal["core.tools.shell.Shell"] = "core.tools.shell.Shell" #type: ignore

    max_output: int = 20000

    blocked_commands: List[str] = [
        "rm -rf /",
        "shutdown",
        "reboot",
        ":(){:|:&};:",
    ]