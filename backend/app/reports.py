from io import BytesIO
from xml.sax.saxutils import escape

from fastapi.responses import Response
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def pdf(title, fields):
    stream = BytesIO()
    styles = getSampleStyleSheet()
    styles["Heading3"].textColor = HexColor("#12625d")
    story = [
        Paragraph("EcoAudit", styles["Heading3"]),
        Paragraph(escape(title), styles["Title"]),
        Paragraph("Prototipo de investigación · Sin validación clínica", styles["BodyText"]),
        Spacer(1, 12),
    ]
    for label, value in fields:
        story.extend(
            [
                Paragraph(escape(label), styles["Heading3"]),
                Paragraph(escape(str(value)), styles["BodyText"]),
            ]
        )
    SimpleDocTemplate(stream, pagesize=A4, title=title).build(story)
    return Response(
        stream.getvalue(), media_type="application/pdf", headers={"Cache-Control": "no-store"}
    )
