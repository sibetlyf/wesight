from agno.skills import Skills
from agno.tools.function import Function
from typing import List, override


class TurboSkills(Skills):
    """中文版本的 Skills 类，提供中文系统提示词"""

    @override
    def get_system_prompt_snippet(self) -> str:
        """生成中文的系统提示词片段，包含可用技能的元数据。

        这会创建一个 XML 格式的片段，向代理提供有关可用技能的信息，
        而不包含完整的指令。

        返回:
            包含技能元数据的 XML 格式字符串。
        """
        if not self._skills:
            return ""

        lines = [
            "<skills_system>",
            "",
            "## 什么是技能？",
            "技能是扩展您能力的领域专业知识包。每个技能包含：",
            "- **指令**：关于何时以及如何应用技能的详细指导",
            "- **脚本**：您可以使用或改编的可执行代码模板",
            "- **参考资料**：支持文档（指南、备忘单、示例）",
            "",
            "## 重要：如何使用技能",
            "**技能名称不是可调用函数**。您不能直接通过名称调用技能。",
            "相反，您必须`shell`工具进行调用，使用 `shell` 或`read_file`读取关键文档，例如:",
            "",
            "1. `read_file(path='<skill_dir>/SKILL.md')` - 读取skill文档",
            "2. `read_file(path='<skill_dir>/references/<ref_name>')` - 读取参考文档",
            "3. `shell(command='python3 <skill_dir>/scripts/<script_name> <参数>')` - 执行脚本",
            "",
            "## 渐进式发现工作流程",
            "1. **浏览**：查看下面的技能摘要，了解可用的内容",
            "2. **加载**：当任务与技能匹配时，首先调用 `read_file(path='<SKILL.md 绝对路径>')`",
            "3. **参考**：根据需要使用 `read_file` 访问特定文档",
            "4. **脚本**：使用 `shell` 执行技能中的脚本",
            "",
            "## 注意事项",
            "1. 读取或者执行脚本时，必须提供绝对路径。`${SKILL_DIR}`需要替换为技能绝对目录路径",
            "2. skill 的文档直供读取，scripts 仅供执行，素材等需要手动复制使用，请勿修改原始文件",
            "3. 脚本生成的 project 及结果存储在$RUNSPACE目录下",
            "",
            "## 可用技能",
        ]
        for skill in self._skills.values():
            lines.append("<skill>")
            lines.append(f"  <name>{skill.name}</name>")
            lines.append(f"  <description>{skill.description}</description>")
            lines.append(f"  <skill_dir>{skill.source_path}</skill_dir>")
            lines.append("</skill>")
        lines.append("")
        lines.append("</skills_system>")

        return "\n".join(lines)

    @override
    def get_tools(self) -> List[Function]:
        """获取所有可用的工具，不再使用官方工具调用
        返回:
            包含所有工具的列表
        """
        return []
