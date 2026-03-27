"""PDF 报告输出"""
import logging
from datetime import datetime
from pathlib import Path

from .base import BaseOutput
from ..core.models import Article, ResearchContext

logger = logging.getLogger(__name__)


class PDFOutput(BaseOutput):
    """将报告导出为 PDF 文件"""

    def render(
        self,
        articles: list,
        context: ResearchContext,
        template_name: str,
        output_config: dict,
    ) -> str:
        # 先生成 Markdown
        from .markdown import MarkdownOutput
        md_output = MarkdownOutput(config=self.config)
        md_output._global_config = getattr(self, "_global_config", None)
        report_md = md_output.render(articles, context, template_name, output_config)

        # 转为 PDF
        pdf_path = self._save_pdf(report_md, context, output_config)
        if pdf_path:
            logger.info(f"PDF 报告已保存：{pdf_path}")

        return report_md

    def _save_pdf(self, md_content: str, context: ResearchContext, output_config: dict) -> Path | None:
        output_dir = Path(
            output_config.get("dir") or "~/Documents/research/"
        ).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)

        safe_topic = "".join(c if c.isalnum() or c in "_ -" else "" for c in context.topic)[:30]
        date_str = datetime.now().strftime("%Y%m%d")
        pdf_path = output_dir / f"{date_str}_{safe_topic}.pdf"

        # 优先使用 weasyprint
        try:
            return self._weasyprint_render(md_content, pdf_path)
        except ImportError:
            pass

        # 降级：使用 reportlab 纯文本 PDF
        try:
            return self._reportlab_render(md_content, pdf_path)
        except ImportError:
            pass

        logger.warning("未找到 PDF 渲染库（weasyprint 或 reportlab），跳过 PDF 输出。")
        logger.warning("安装：pip install weasyprint  或  pip install reportlab markdown")
        return None

    def _weasyprint_render(self, md_content: str, pdf_path: Path) -> Path:
        import markdown as md_lib
        from weasyprint import HTML, CSS

        html_body = md_lib.markdown(md_content, extensions=["tables", "fenced_code"])
        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: "PingFang SC", "Noto Sans CJK SC", Arial, sans-serif;
          font-size: 14px; line-height: 1.7; max-width: 800px; margin: 40px auto; color: #333; }}
  h1 {{ font-size: 2em; border-bottom: 2px solid #4a90d9; padding-bottom: 8px; }}
  h2 {{ font-size: 1.5em; border-bottom: 1px solid #ccc; padding-bottom: 4px; }}
  h3 {{ font-size: 1.2em; }}
  a {{ color: #4a90d9; text-decoration: none; }}
  code {{ background: #f5f5f5; padding: 2px 5px; border-radius: 3px; font-size: 0.9em; }}
  pre code {{ display: block; padding: 12px; overflow-x: auto; }}
  blockquote {{ border-left: 4px solid #4a90d9; margin: 0; padding-left: 16px; color: #666; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; }}
  th {{ background: #f0f4ff; }}
</style>
</head>
<body>{html_body}</body>
</html>"""
        HTML(string=html).write_pdf(str(pdf_path))
        return pdf_path

    def _reportlab_render(self, md_content: str, pdf_path: Path) -> Path:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.enums import TA_LEFT

        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )
        styles = getSampleStyleSheet()
        story = []

        for line in md_content.split("\n"):
            line = line.rstrip()
            if line.startswith("# "):
                p = Paragraph(line[2:], styles["Heading1"])
            elif line.startswith("## "):
                p = Paragraph(line[3:], styles["Heading2"])
            elif line.startswith("### "):
                p = Paragraph(line[4:], styles["Heading3"])
            elif line:
                # 处理简单 markdown 加粗/斜体
                text = (line.replace("**", "<b>", 1).replace("**", "</b>", 1)
                            .replace("*", "<i>", 1).replace("*", "</i>", 1))
                p = Paragraph(text, styles["Normal"])
            else:
                story.append(Spacer(1, 6))
                continue
            story.append(p)
            story.append(Spacer(1, 2))

        doc.build(story)
        return pdf_path
