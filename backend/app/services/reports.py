"""
Generic PDF report generation service.

Renders a Jinja2 HTML template with the given context, then converts
the rendered HTML to PDF bytes using xhtml2pdf.

Every module (finance, HR, admin) reuses generate_pdf() below —
only the template and the data passed in differ per report.
"""

from io import BytesIO
from pathlib import Path
from decimal import Decimal
from datetime import datetime

from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa

TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "reports"

env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))

# Currency formatting filter, usable in any template as {{ value | lkr }}
env.filters["lkr"] = lambda v: f"Rs. {Decimal(v):,.2f}"


class PDFGenerationError(Exception):
    """Raised when xhtml2pdf fails to render the PDF."""
    pass


def generate_pdf(template_name: str, context: dict) -> bytes:
    """
    Render `template_name` (a file inside app/templates/reports/)
    with `context`, and return the resulting PDF as bytes.

    Example:
        pdf_bytes = generate_pdf("finance_summary.html", {
            "summary": [...],
            "period": "2026-01-01 to 2026-01-31",
        })
    """
    context.setdefault("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M"))
    context.setdefault("org_name", "Vets For Future")

    template = env.get_template(template_name)
    html_content = template.render(**context)

    result = BytesIO()
    pisa_status = pisa.CreatePDF(src=html_content, dest=result)

    if pisa_status.err:
        raise PDFGenerationError(
            f"Failed to generate PDF from template '{template_name}' "
            f"({pisa_status.err} error(s) reported by xhtml2pdf)."
        )

    return result.getvalue()