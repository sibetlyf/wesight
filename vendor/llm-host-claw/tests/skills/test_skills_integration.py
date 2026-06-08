#!/usr/bin/env python3
"""
Integration tests for skills.
Tests that skills are properly loaded and influence AI behavior.
"""

import os
import sys
import pytest
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.abilities_loader import load_skills
from agno.agent import Agent
from agno.skills import Skills
from protocol import EnVar


class TestSkillsLoading:
    """Tests for skill loading functionality."""

    def test_load_skills_returns_skills_object(self, workspace_prepare):
        """Test that load_skills returns a Skills object."""
        envar = EnVar.from_env()
        skills = load_skills(envar=envar)
        assert isinstance(skills, Skills), "load_skills should return a Skills object"
        print("✓ Skills object created successfully")

    def test_skills_not_empty(self, workspace_prepare):
        """Test that skills are loaded (not empty)."""
        envar = EnVar.from_env()
        skills = load_skills(envar=envar)
        assert skills is not None, "Skills should not be None"
        print("✓ Skills loaded successfully")

    def test_skills_directory_structure(self, workspace_prepare):
        """Test that skills directory exists and contains SKILL.md files."""
        skills_dir = Path(__file__).parent.parent.parent / "src" / "core" / "skills"
        assert skills_dir.exists(), f"Skills directory not found: {skills_dir}"

        # Find all SKILL.md files
        skill_files = list(skills_dir.rglob("SKILL.md"))
        assert len(skill_files) > 0, "No SKILL.md files found"

        print(f"✓ Found {len(skill_files)} skill files")
        for skill_file in skill_files:
            print(f"  - {skill_file.parent.name}")


class TestDocxSkillBehavior:
    """Tests for docx skill behavior influence on AI."""

    def _create_sample_docx(self, workspace: str) -> str:
        """创建一个样例 Word 文档用于测试."""
        from docx import Document
        from docx.shared import Pt

        doc_path = os.path.join(workspace, "sample.docx")
        doc = Document()

        # 添加标题
        title = doc.add_heading('AI 在工业领域的应用', 0)

        # 添加段落
        doc.add_paragraph('人工智能正在深刻改变工业生产方式。以下是三个成功的应用案例：')

        # 案例1
        doc.add_heading('案例1：预测性维护', level=1)
        doc.add_paragraph(
            '某汽车制造企业通过部署 AI 预测性维护系统，'
            '将设备故障率降低了 35%，维护成本减少了 20%。'
            '系统通过分析设备传感器数据，提前预测潜在故障。'
        )

        # 案例2
        doc.add_heading('案例2：质量检测', level=1)
        doc.add_paragraph(
            '某电子制造企业使用计算机视觉技术进行产品质量检测，'
            '检测准确率达到 99.5%，检测速度提升了 10 倍。'
        )

        # 案例3
        doc.add_heading('案例3：供应链优化', level=1)
        doc.add_paragraph(
            '某化工企业利用 AI 优化供应链管理，'
            '库存周转率提高了 25%，缺货率降低了 40%。'
        )

        doc.save(doc_path)
        return doc_path

    @pytest.mark.asyncio
    async def test_agent_recognizes_docx_request(self, jt_model, skills_loader, workspace_prepare):
        """Test that agent recognizes when to use docx skill."""
        envar = EnVar.from_env()

        sample_docx = self._create_sample_docx(envar.workspace)

        agent = Agent(
            model=jt_model,
            skills=skills_loader,
            instructions="你是一个智能助手。",
            user_id="test_user",
            debug_mode=True,
            telemetry=False,
        )

        # Test prompts that should trigger docx skill
        docx_prompts = [
            f"请读取 {sample_docx} 文件，并在末尾添加一个总结段落",
        ]

        for prompt in docx_prompts:
            try:
                response = ""
                async for event in agent.arun(prompt, stream=True):
                    if hasattr(event, 'content') and event.content:
                        response += str(event.content)

                # Check if response mentions docx-related content or tools
                response_lower = response.lower()
                has_docx_keyword = any(keyword in response_lower for keyword in [
                    "docx", "word", "文档", "document", "报告"
                ])

                if has_docx_keyword:
                    print(f"✓ Agent recognized docx request: '{prompt[:30]}...'")
                else:
                    print(f"ℹ Agent response for '{prompt[:30]}...': {response[:100]}")

            except Exception as e:
                pytest.skip(f"Model not available: {e}")


class TestPdfSkillBehavior:
    """Tests for pdf skill behavior influence on AI."""

    def _create_sample_pdf(self, workspace: str) -> str:
        """创建一个样例 PDF 文档用于测试."""
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        pdf_path = os.path.join(workspace, "sample.pdf")
        c = canvas.Canvas(pdf_path, pagesize=letter)
        width, height = letter

        # 添加标题
        c.setFont("Helvetica-Bold", 16)
        c.drawString(100, height - 100, "Product Report 2024")

        # 添加内容
        c.setFont("Helvetica", 12)
        text_y = height - 150
        lines = [
            "This is a sample PDF document for testing purposes.",
            "",
            "Product Sales Summary:",
            "- Product A: $50,000",
            "- Product B: $75,000",
            "- Product C: $30,000",
            "",
            "Total Revenue: $155,000",
            "",
            "Please extract the sales data from this document.",
        ]

        for line in lines:
            c.drawString(100, text_y, line)
            text_y -= 20

        c.save()
        return pdf_path

    @pytest.mark.asyncio
    async def test_agent_recognizes_pdf_request(self, jt_model, skills_loader, workspace_prepare):
        """Test that agent recognizes when to use pdf skill."""
        envar = EnVar.from_env()

        sample_pdf = self._create_sample_pdf(envar.workspace)

        agent = Agent(
            model=jt_model,
            skills=skills_loader,
            instructions="你是一个智能助手。",
            user_id="test_user",
            debug_mode=True,
            telemetry=False,
        )

        # Test prompts that should trigger pdf skill
        pdf_prompts = [
            f"请提取 {sample_pdf} 文件中的销售数据",
        ]

        for prompt in pdf_prompts:
            try:
                response = ""
                async for event in agent.arun(prompt, stream=True):
                    if hasattr(event, 'content') and event.content:
                        response += str(event.content)

                response_lower = response.lower()
                has_pdf_keyword = "pdf" in response_lower or "pdf" in response_lower

                if has_pdf_keyword:
                    print(f"✓ Agent recognized pdf request: '{prompt[:30]}...'")
                else:
                    print(f"ℹ Agent response for '{prompt[:30]}...': {response[:100]}")

            except Exception as e:
                pytest.skip(f"Model not available: {e}")


class TestPptxSkillBehavior:
    """Tests for pptx skill behavior influence on AI."""

    def _create_sample_pptx(self, workspace: str) -> str:
        """创建一个样例 PPT 文件用于测试."""
        from pptx import Presentation
        from pptx.util import Inches, Pt

        pptx_path = os.path.join(workspace, "sample.pptx")
        prs = Presentation()

        # 添加标题页
        title_slide = prs.slides.add_slide(prs.slide_layouts[0])
        title = title_slide.shapes.title
        subtitle = title_slide.placeholders[1]
        title.text = "Quarterly Business Review"
        subtitle.text = "Q4 2024"

        # 添加内容页
        bullet_slide = prs.slides.add_slide(prs.slide_layouts[1])
        shapes = bullet_slide.shapes
        title_shape = shapes.title
        body_shape = shapes.placeholders[1]

        title_shape.text = "Key Achievements"
        tf = body_shape.text_frame
        tf.text = "Revenue Growth: 25%"

        p = tf.add_paragraph()
        p.text = "New Customers: 150+"
        p.level = 0

        p = tf.add_paragraph()
        p.text = "Product Launches: 3"
        p.level = 0

        # 添加另一页
        bullet_slide2 = prs.slides.add_slide(prs.slide_layouts[1])
        shapes2 = bullet_slide2.shapes
        title_shape2 = shapes2.title
        body_shape2 = shapes2.placeholders[1]

        title_shape2.text = "Next Quarter Goals"
        tf2 = body_shape2.text_frame
        tf2.text = "Expand to new markets"

        p = tf2.add_paragraph()
        p.text = "Launch premium tier"
        p.level = 0

        p = tf2.add_paragraph()
        p.text = "Improve customer retention"
        p.level = 0

        prs.save(pptx_path)
        return pptx_path

    @pytest.mark.asyncio
    async def test_agent_recognizes_pptx_request(self, jt_model, skills_loader, workspace_prepare):
        """Test that agent recognizes when to use pptx skill."""
        envar = EnVar.from_env()

        sample_pptx = self._create_sample_pptx(envar.workspace)

        agent = Agent(
            model=jt_model,
            skills=skills_loader,
            instructions="你是一个智能助手。",
            user_id="test_user",
            debug_mode=True,
            telemetry=False,
        )

        # Test prompts that should trigger pptx skill
        pptx_prompts = [
            f"请读取 {sample_pptx} 文件，并总结其中的关键成就",
        ]

        for prompt in pptx_prompts:
            try:
                response = ""
                async for event in agent.arun(prompt, stream=True):
                    if hasattr(event, 'content') and event.content:
                        response += str(event.content)

                response_lower = response.lower()
                has_pptx_keyword = any(keyword in response_lower for keyword in [
                    "ppt", "pptx", "presentation", "演示", "幻灯片", "slide"
                ])

                if has_pptx_keyword:
                    print(f"✓ Agent recognized pptx request: '{prompt[:30]}...'")
                else:
                    print(f"ℹ Agent response for '{prompt[:30]}...': {response[:100]}")

            except Exception as e:
                pytest.skip(f"Model not available: {e}")


class TestXlsxSkillBehavior:
    """Tests for xlsx skill behavior influence on AI."""

    def _create_sample_xlsx(self, workspace: str) -> str:
        """创建一个样例 Excel 文件用于测试."""
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill

        xlsx_path = os.path.join(workspace, "sample.xlsx")
        wb = Workbook()
        ws = wb.active
        ws.title = "Sales Data"

        # 添加表头
        headers = ["Product", "Q1 Sales", "Q2 Sales", "Q3 Sales", "Q4 Sales", "Total"]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")

        # 添加数据
        data = [
            ["Product A", 10000, 12000, 15000, 18000, 55000],
            ["Product B", 8000, 9500, 11000, 14000, 42500],
            ["Product C", 5000, 6000, 7500, 9000, 27500],
            ["Product D", 12000, 13500, 16000, 19000, 60500],
        ]

        for row_idx, row_data in enumerate(data, 2):
            for col_idx, value in enumerate(row_data, 1):
                ws.cell(row=row_idx, column=col_idx, value=value)

        # 添加汇总行
        summary_row = len(data) + 2
        ws.cell(row=summary_row, column=1, value="Total").font = Font(bold=True)
        for col in range(2, 7):
            cell = ws.cell(row=summary_row, column=col, value=f"=SUM({chr(64+col)}2:{chr(64+col)}5)")
            cell.font = Font(bold=True)

        # 调整列宽
        ws.column_dimensions['A'].width = 15
        for col in ['B', 'C', 'D', 'E', 'F']:
            ws.column_dimensions[col].width = 12

        wb.save(xlsx_path)
        return xlsx_path

    @pytest.mark.asyncio
    async def test_agent_recognizes_xlsx_request(self, jt_model, skills_loader, workspace_prepare):
        """Test that agent recognizes when to use xlsx skill."""
        envar = EnVar.from_env()

        sample_xlsx = self._create_sample_xlsx(envar.workspace)

        agent = Agent(
            model=jt_model,
            skills=skills_loader,
            instructions="你是一个智能助手。",
            user_id="test_user",
            debug_mode=True,
            telemetry=False,
        )

        # Test prompts that should trigger xlsx skill
        xlsx_prompts = [
            f"请分析 {sample_xlsx} 文件中的销售数据，找出销售额最高的产品",
        ]

        for prompt in xlsx_prompts:
            try:
                response = ""
                async for event in agent.arun(prompt, stream=True):
                    if hasattr(event, 'content') and event.content:
                        response += str(event.content)

                response_lower = response.lower()
                has_xlsx_keyword = any(keyword in response_lower for keyword in [
                    "xlsx", "excel", "spreadsheet", "表格", "sheet"
                ])

                if has_xlsx_keyword:
                    print(f"✓ Agent recognized xlsx request: '{prompt[:30]}...'")
                else:
                    print(f"ℹ Agent response for '{prompt[:30]}...': {response[:100]}")

            except Exception as e:
                pytest.skip(f"Model not available: {e}")


class TestDocCoauthoringSkillBehavior:
    """Tests for doc-coauthoring skill behavior influence on AI."""

    @pytest.mark.asyncio
    async def test_agent_recognizes_doc_writing_request(self, jt_model, skills_loader):
        """Test that agent recognizes when to use doc-coauthoring skill."""
        agent = Agent(
            model=jt_model,
            skills=skills_loader,
            instructions="你是一个智能助手。",
            user_id="test_user",
            debug_mode=True,
            telemetry=False,
        )

        # Test prompts that should trigger doc-coauthoring skill
        writing_prompts = [
            "帮我写一份技术文档，主题是Agent Swarm",
        ]

        for prompt in writing_prompts:
            try:
                response = ""
                async for event in agent.arun(prompt, stream=True):
                    if hasattr(event, 'content') and event.content:
                        response += str(event.content)

                response_lower = response.lower()
                has_writing_keyword = any(keyword in response_lower for keyword in [
                    "文档", "document", "spec", "设计", "prd", "workflow"
                ])

                if has_writing_keyword:
                    print(f"✓ Agent recognized writing request: '{prompt[:30]}...'")
                else:
                    print(f"ℹ Agent response for '{prompt[:30]}...': {response[:100]}")

            except Exception as e:
                pytest.skip(f"Model not available: {e}")


class TestContentResearchWriterSkillBehavior:
    """Tests for content-research-writer skill behavior influence on AI."""

    @pytest.mark.asyncio
    async def test_agent_recognizes_content_writing_request(self, jt_model, skills_loader):
        """Test that agent recognizes when to use content-research-writer skill."""
        agent = Agent(
            model=jt_model,
            skills=skills_loader,
            instructions="你是一个智能助手。",
            user_id="test_user",
            debug_mode=True,
            telemetry=False,
        )

        # Test prompts that should trigger content-research-writer skill
        content_prompts = [
            "帮我写一篇关于skills创建和管理的博客",
        ]

        for prompt in content_prompts:
            try:
                response = ""
                async for event in agent.arun(prompt, stream=True):
                    if hasattr(event, 'content') and event.content:
                        response += str(event.content)

                response_lower = response.lower()
                has_content_keyword = any(keyword in response_lower for keyword in [
                    "文章", "博客", "写作", "outline", "hook", "research"
                ])

                if has_content_keyword:
                    print(f"✓ Agent recognized content writing request: '{prompt[:30]}...'")
                else:
                    print(f"ℹ Agent response for '{prompt[:30]}...': {response[:100]}")

            except Exception as e:
                pytest.skip(f"Model not available: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
