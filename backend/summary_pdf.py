"""Build a downloadable PDF summary of a saved report.

The PDF is made in memory and sent to the user; it is never saved on the server.
English only: the PDF library cannot shape Malayalam script correctly.
"""

import io
import re
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

DISCLAIMER = (
    "MediXplain AI is an educational tool. This summary is not a diagnosis and does not "
    "replace professional medical advice. Please discuss your results with a qualified "
    "healthcare professional."
)
STATUS_LABEL = {"HIGH": "High", "LOW": "Low", "NORMAL": "Normal"}

INK = colors.HexColor("#1f1f1e")
MUTED = colors.HexColor("#6b6a66")
RULE = colors.HexColor("#d9d8d3")
HEADER_BG = colors.HexColor("#f1f0ec")
FLAG_BG = colors.HexColor("#fdf1e7")


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontSize=18, leading=22,
                                textColor=INK, spaceAfter=2),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"], fontSize=9,
                                   textColor=MUTED, alignment=TA_CENTER, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=13, leading=16,
                             textColor=INK, spaceBefore=10, spaceAfter=6),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontSize=11, leading=14,
                             textColor=INK, spaceBefore=6, spaceAfter=3),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=10, leading=14,
                               textColor=INK, spaceAfter=4),
        "bullet": ParagraphStyle("bullet", parent=base["Normal"], fontSize=10, leading=14,
                                 textColor=INK, leftIndent=12, bulletIndent=2, spaceAfter=2),
        "cell": ParagraphStyle("cell", parent=base["Normal"], fontSize=9, leading=12,
                               textColor=INK),
        "small": ParagraphStyle("small", parent=base["Normal"], fontSize=8, leading=11,
                                textColor=MUTED),
    }


def _inline(text: str) -> str:
    """Escape text for reportlab and turn **bold** / *italic* markdown into tags."""
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", text)
    return text


def markdown_to_flowables(markdown: str, styles: dict) -> list:
    """Very small markdown converter: headings, bullet/numbered lists, paragraphs."""
    flowables, paragraph = [], []

    def flush():
        if paragraph:
            flowables.append(Paragraph(_inline(" ".join(paragraph)), styles["body"]))
            paragraph.clear()

    for raw in (markdown or "").splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        bullet = re.match(r"^[-*•]\s+(.*)$", line)
        numbered = re.match(r"^(\d+)[.)]\s+(.*)$", line)
        if heading:
            flush()
            flowables.append(Paragraph(_inline(heading.group(2)), styles["h3"]))
        elif bullet:
            flush()
            flowables.append(Paragraph(_inline(bullet.group(1)), styles["bullet"], bulletText="•"))
        elif numbered:
            flush()
            flowables.append(Paragraph(_inline(numbered.group(2)), styles["bullet"],
                                       bulletText=f"{numbered.group(1)}."))
        elif re.match(r"^\*\*[^*]+:\*\*", line) or re.match(r"^\*\*[^*]+\*\*:", line):
            # A line starting with a bold label ("**Reason:** ...") stays on its own line.
            flush()
            flowables.append(Paragraph(_inline(line), styles["body"]))
        else:
            paragraph.append(line)
    flush()
    return flowables


def _lab_table(labs: list, styles: dict) -> Table:
    rows = [[Paragraph(f"<b>{h}</b>", styles["cell"])
             for h in ("Test", "Result", "Reference range", "Status")]]
    flagged = []
    for i, lab in enumerate(labs, start=1):
        status = STATUS_LABEL.get(lab.status, lab.status)
        rows.append([
            Paragraph(escape(lab.test), styles["cell"]),
            Paragraph(escape(f"{lab.value_text} {lab.unit}".strip()), styles["cell"]),
            Paragraph(escape(lab.reference_range or "Not printed"), styles["cell"]),
            Paragraph(f"<b>{status}</b>" if lab.status != "NORMAL" else status, styles["cell"]),
        ])
        if lab.status != "NORMAL":
            flagged.append(i)

    table = Table(rows, colWidths=[66 * mm, 34 * mm, 42 * mm, 24 * mm], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    style += [("BACKGROUND", (0, r), (-1, r), FLAG_BG) for r in flagged]
    table.setStyle(TableStyle(style))
    return table


def build_summary_pdf(patient_name: str, report, labs: list, summary: str | None,
                      questions: str | None = None, specialist: str | None = None) -> bytes:
    styles = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"MediXplain summary - {report.title}", author="MediXplain AI",
    )

    story = [
        Paragraph("MediXplain AI — Report Summary", styles["title"]),
        Paragraph(escape(f"{patient_name} · {report.title} · Report date {report.report_date} · "
                         f"Created {date.today().isoformat()}"), styles["subtitle"]),
        Paragraph(escape(DISCLAIMER), styles["small"]),
        Spacer(1, 6),
    ]

    outside = [lab for lab in labs if lab.status != "NORMAL"]
    story.append(Paragraph("Lab values", styles["h2"]))
    if labs:
        story.append(Paragraph(
            f"{len(labs)} values were read from the report; "
            f"<b>{len(outside)}</b> are outside the reference range printed on the report "
            "(highlighted).", styles["body"]))
        story.append(_lab_table(labs, styles))
    else:
        story.append(Paragraph("No lab values with reference ranges were found in this report.",
                               styles["body"]))

    for heading, text in (("Explanation", summary),
                          ("Questions to ask your doctor", questions),
                          ("Specialist guidance", specialist)):
        if text:
            block = [Paragraph(heading, styles["h2"])] + markdown_to_flowables(text, styles)
            story.append(KeepTogether(block[:3]))  # keep a heading with its first lines
            story.extend(block[3:])

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(20 * mm, 10 * mm, "MediXplain AI · educational use only")
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()