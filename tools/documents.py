"""create_document: Word (.docx) and/or PDF."""
import re
from xml.sax.saxutils import escape

from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from .common import after_create, output_path

TOOLS = [{
    "type": "function",
    "function": {
        "name": "create_document",
        "description": "Create a Word (.docx) and/or PDF document and save it.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string", "description": "Full text. '# ' and '## ' headings, '- ' bullets, blank line between paragraphs."},
                "format": {"type": "string", "enum": ["docx", "pdf", "both"]},
            },
            "required": ["title", "content", "format"],
        },
    },
}]


def _parse_blocks(content):
    blocks = []
    for raw in content.splitlines():
        line = raw.strip().replace("**", "").replace("__", "")
        if not line:
            continue
        if line.startswith("### "):
            blocks.append(("h2", line[4:]))
        elif line.startswith("## "):
            blocks.append(("h2", line[3:]))
        elif line.startswith("# "):
            blocks.append(("h1", line[2:]))
        elif line.startswith(("- ", "* ")):
            blocks.append(("bullet", line[2:]))
        elif re.match(r"\d+[.)] ", line):
            blocks.append(("number", re.sub(r"^\d+[.)] ", "", line)))
        else:
            blocks.append(("p", line))
    return blocks


def _make_docx(path, title, blocks):
    doc = Document()
    doc.add_heading(title, 0)
    for kind, text in blocks:
        if kind == "h1":
            doc.add_heading(text, 1)
        elif kind == "h2":
            doc.add_heading(text, 2)
        elif kind == "bullet":
            doc.add_paragraph(text, style="List Bullet")
        elif kind == "number":
            doc.add_paragraph(text, style="List Number")
        else:
            doc.add_paragraph(text)
    doc.save(path)


def _pdf_text(text):
    text = text.replace("\u2011", "-").replace("\u00a0", " ").replace("\u202f", " ")
    return escape(text.encode("cp1252", "replace").decode("cp1252"))


def _make_pdf(path, title, blocks):
    styles = getSampleStyleSheet()
    bullet_style = ParagraphStyle("b", parent=styles["BodyText"], leftIndent=18, bulletIndent=6)
    story = [Paragraph(_pdf_text(title), styles["Title"]), Spacer(1, 12)]
    n = 0
    for kind, text in blocks:
        t = _pdf_text(text)
        if kind != "number":
            n = 0
        if kind == "h1":
            story.append(Paragraph(t, styles["Heading1"]))
        elif kind == "h2":
            story.append(Paragraph(t, styles["Heading2"]))
        elif kind == "bullet":
            story.append(Paragraph(t, bullet_style, bulletText="\u2022"))
        elif kind == "number":
            n += 1
            story.append(Paragraph(t, bullet_style, bulletText=f"{n}."))
        else:
            story.append(Paragraph(t, styles["BodyText"]))
            story.append(Spacer(1, 4))
    SimpleDocTemplate(path, pagesize=A4, title=title).build(story)


def create_document(args):
    title = args.get("title") or "Document"
    content = args.get("content") or ""
    fmt = (args.get("format") or "docx").lower()
    if fmt not in ("docx", "pdf", "both"):
        fmt = "docx"
    print(f"[Creating {fmt}: {title}]")
    blocks = _parse_blocks(content)
    made, note = [], ""
    if fmt in ("docx", "both"):
        p = output_path(title, "docx")
        _make_docx(p, title, blocks)
        made.append(p)
    if fmt in ("pdf", "both"):
        if re.search(r"[\u0980-\u09FF]", title + content):
            note = " PDF was skipped because Bangla text is not supported in PDF yet."
            if not made:
                p = output_path(title, "docx")
                _make_docx(p, title, blocks)
                made.append(p)
        else:
            p = output_path(title, "pdf")
            _make_pdf(p, title, blocks)
            made.append(p)
    opened = after_create(made[0])
    names = ", ".join(m.rsplit("/", 1)[-1] for m in made)
    return f"Saved {names} in the 'documents' folder.{opened}{note}"


HANDLERS = {"create_document": create_document}

