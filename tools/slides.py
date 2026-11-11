"""create_presentation: designed .pptx slide decks (python-pptx).

Layouts: title, cards, split, stats, steps, compare, quote, closing.
Dark title/closing slides + light content slides, one palette per deck,
numbered circles / rounded cards as the visual motif, fade transitions.
"""
import math
from datetime import datetime

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.util import Inches, Pt

from .common import after_create, output_path

W, H, MX = 13.333, 7.5, 0.7
HEAD, BODY = "Cambria", "Calibri"
WHITE = "FFFFFF"
OVAL, RECT, ROUND = MSO_SHAPE.OVAL, MSO_SHAPE.RECTANGLE, MSO_SHAPE.ROUNDED_RECTANGLE

PALETTES = {
    "midnight":   dict(dark="141B41", primary="1E2761", tint="E8EEFC", accent="F5B942", muted="5B6B9A"),
    "forest":     dict(dark="14301A", primary="2C5F2D", tint="EAF3DF", accent="F2A541", muted="587A4C"),
    "coral":      dict(dark="232B5E", primary="E5484D", tint="FFF0EE", accent="F9C74F", muted="6B7280"),
    "terracotta": dict(dark="3B2320", primary="B85042", tint="F7EDE9", accent="A7BEAE", muted="8A6F68"),
    "ocean":      dict(dark="14204F", primary="065A82", tint="E4F1F7", accent="5BC0DE", muted="4F6F85"),
    "charcoal":   dict(dark="1E1E1E", primary="36454F", tint="F2F2F2", accent="FF7A3D", muted="6B7280"),
    "teal":       dict(dark="0B3C49", primary="028090", tint="E3F6F4", accent="02C39A", muted="4B7F86"),
    "berry":      dict(dark="3B1727", primary="6D2E46", tint="F5E9EC", accent="E0A458", muted="8A6070"),
}

TOOLS = [{
    "type": "function",
    "function": {
        "name": "create_presentation",
        "description": "Create a designed PowerPoint (.pptx) deck. First slide layout 'title', last 'closing'; vary layouts in between.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "palette": {"type": "string", "enum": list(PALETTES)},
                "slides": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "layout": {"type": "string", "enum": ["title", "cards", "split", "stats", "steps", "compare", "quote", "closing"]},
                            "title": {"type": "string", "description": "max 7 words, no period"},
                            "subtitle": {"type": "string"},
                            "items": {"type": "array", "description": "cards/steps: 3-4 items",
                                      "items": {"type": "object", "properties": {
                                          "heading": {"type": "string", "description": "max 4 words"},
                                          "text": {"type": "string", "description": "max 18 words"}}}},
                            "bullets": {"type": "array", "items": {"type": "string"}, "description": "split/closing: 3-4 short lines"},
                            "stats": {"type": "array", "items": {"type": "object", "properties": {
                                "value": {"type": "string", "description": "short, e.g. 256-bit, 3x, 99%"},
                                "label": {"type": "string"}}}},
                            "left": {"type": "object", "properties": {"heading": {"type": "string"}, "bullets": {"type": "array", "items": {"type": "string"}}}},
                            "right": {"type": "object", "properties": {"heading": {"type": "string"}, "bullets": {"type": "array", "items": {"type": "string"}}}},
                            "callout": {"type": "string", "description": "split/quote: one punchy sentence"},
                            "callout_label": {"type": "string"},
                            "notes": {"type": "string", "description": "speaker notes"},
                        },
                        "required": ["layout", "title"],
                    },
                },
            },
            "required": ["title", "palette", "slides"],
        },
    },
}]


# ------------------------------------------------------------------ helpers
def _rgb(h):
    return RGBColor.from_string(h)


def _blend(a, b, t):
    ca = [int(a[i:i + 2], 16) for i in (0, 2, 4)]
    cb = [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    return "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(ca, cb))


def _clip(text, n):
    text = " ".join(str(text or "").split())
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0].rstrip(",;:-") + "…"


def _cpl(w, pt, factor=0.48):
    return max(4, int(w / (pt * factor / 72)))


def _lines(text, w, pt, factor=0.46):
    return max(1, math.ceil(len(text) / _cpl(w, pt, factor)))


def _fit(text, w, h, pt, factor=0.48):
    lines = max(1, int(h / (pt * 1.22 / 72)))
    return _clip(text, int(_cpl(w, pt, factor) * lines * 0.9))


def _shape(s, kind, x, y, w, h, fill=None, line=None, line_w=1.0, radius=None):
    sh = s.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.shadow.inherit = False
    for ref in sh._element.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}effectRef'):
        ref.set('idx', '0')  # theme shadow off (LibreOffice/Keynote bhi)
    if fill:
        sh.fill.solid()
        sh.fill.fore_color.rgb = _rgb(fill)
    else:
        sh.fill.background()
    if line:
        sh.line.color.rgb = _rgb(line)
        sh.line.width = Pt(line_w)
    else:
        sh.line.fill.background()
    if radius is not None and kind == ROUND:
        sh.adjustments[0] = radius
    return sh


def _style(tf, anchor):
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor


def _run(p, text, size, color, bold=False, font=BODY, italic=False):
    r = p.add_run()
    r.text = text
    f = r.font
    f.size, f.bold, f.italic, f.name = Pt(size), bold, italic, font
    f.color.rgb = _rgb(color)


def _text(s, x, y, w, h, text, size, color, bold=False, font=BODY,
          align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, italic=False):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    _style(tb.text_frame, anchor)
    p = tb.text_frame.paragraphs[0]
    p.alignment = align
    _run(p, text, size, color, bold, font, italic)
    return tb


def _badge(s, x, y, d, text, fill, color, size=20):
    c = _shape(s, OVAL, x, y, d, d, fill=fill)
    _style(c.text_frame, MSO_ANCHOR.MIDDLE)
    p = c.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    _run(p, text, size, color, bold=True, font=HEAD)
    return c


def _title(s, text, x, y, w, h, size, color, anchor=MSO_ANCHOR.TOP, font=HEAD):
    t = s.shapes.title
    t.left, t.top, t.width, t.height = Inches(x), Inches(y), Inches(w), Inches(h)
    tf = t.text_frame
    tf.clear()
    _style(tf, anchor)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    _run(p, text, size, color, bold=True, font=font)


class _Deck:
    def __init__(self, title, pal):
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(W), Inches(H)
        self.title, self.p = title, pal

    def new(self, dark):
        s = self.prs.slides.add_slide(self.prs.slide_layouts[5])  # Title Only
        bg = s.background.fill
        bg.solid()
        bg.fore_color.rgb = _rgb(self.p["dark"] if dark else WHITE)
        return s


def _bullets(s, items, x, y, w, max_h, pt, color, dot, gap=0.34):
    rows = []
    for it in items:
        it = _clip(it, 110)
        rows.append((it, _lines(it, w - 0.4, pt) * pt * 1.25 / 72))
    while len(rows) > 1 and sum(h + gap for _, h in rows) > max_h:
        rows.pop()
    used = sum(h + gap for _, h in rows) - gap
    cy = y + max(0.0, (max_h - used) / 4)
    for it, h in rows:
        _shape(s, OVAL, x, cy + (pt * 1.25 / 72 - 0.16) / 2, 0.16, 0.16, fill=dot)
        _text(s, x + 0.4, cy, w - 0.4, h + 0.06, it, pt, color)
        cy += h + gap
    return cy


def _head(b, s, spec, w=W - 2 * MX):
    """Light-slide title, same position on every content slide."""
    _title(s, _clip(spec.get("title"), 56 if w < 9 else 80), MX, 0.55, w, 1.1, 34, b.p["dark"])


# ------------------------------------------------------------------ layouts
def _lay_title(b, spec):
    p, s = b.p, b.new(True)
    _shape(s, OVAL, 8.6, 0.8, 5.8, 5.8, fill=p["primary"])
    _shape(s, OVAL, 7.6, 4.2, 2.5, 2.5, fill=p["accent"])
    _shape(s, OVAL, 11.1, 0.35, 1.1, 1.1, line=p["accent"], line_w=3)
    title = _clip(spec.get("title") or b.title, 70)
    size = 44 if len(title) <= 28 else 38 if len(title) <= 50 else 32
    tw = 6.6
    th = _lines(title, tw, size, 0.58) * size * 1.2 / 72
    sub = _fit(spec.get("subtitle") or "", tw, 1.0, 20) if spec.get("subtitle") else ""
    sh = (_lines(sub, tw, 20) * 20 * 1.25 / 72) if sub else 0
    block = 0.4 + 0.25 + th + (0.35 + sh if sub else 0)
    y = max(0.9, (H - block) / 2)
    _text(s, 0.9, y, tw, 0.35, datetime.now().strftime("%B %Y").upper(), 14, p["accent"], bold=True)
    _title(s, title, 0.9, y + 0.65, tw, th + 0.1, size, WHITE)
    if sub:
        _text(s, 0.9, y + 0.65 + th + 0.35, tw, sh + 0.1, sub, 20, _blend(p["dark"], p["tint"], 0.8))
    return s, True


def _norm_items(spec):
    out = []
    for it in spec.get("items") or []:
        if isinstance(it, dict):
            out.append((it.get("heading") or "", it.get("text") or ""))
        else:
            out.append((str(it), ""))
    if not out and spec.get("bullets"):
        out = [(_clip(x, 40), "") for x in spec["bullets"]]
    return out


def _lay_cards(b, spec):
    p, s = b.p, b.new(False)
    _head(b, s, spec)
    items = _norm_items(spec)[:6] or [("", "")]
    n = len(items)
    cols = 2 if n == 4 else min(n, 3)
    rows = math.ceil(n / cols)
    x0, y0, aw, ah, gap = MX, 1.95, W - 2 * MX, (4.3 if rows == 1 else 4.75), 0.35
    cw = (aw - gap * (cols - 1)) / cols
    ch = (ah - gap * (rows - 1)) / rows
    for i, (head, body) in enumerate(items):
        cx = x0 + (i % cols) * (cw + gap)
        cy = y0 + (i // cols) * (ch + gap)
        _shape(s, ROUND, cx, cy, cw, ch, fill=p["tint"], radius=0.06)
        if rows == 1:
            _badge(s, cx + 0.4, cy + 0.45, 0.75, str(i + 1), p["primary"], WHITE, 26)
            head = _clip(head, 36)
            hh = _lines(head, cw - 0.8, 22, 0.58) * 22 * 1.2 / 72
            _text(s, cx + 0.4, cy + 1.5, cw - 0.8, hh + 0.05, head, 22, p["dark"],
                  bold=True, font=HEAD)
            tb_y = cy + 1.5 + hh + 0.25
            _text(s, cx + 0.4, tb_y, cw - 0.8, ch - (tb_y - cy) - 0.3,
                  _fit(body, cw - 0.8, ch - (tb_y - cy) - 0.3, 18), 18, p["dark"])
        else:
            _badge(s, cx + 0.3, cy + 0.3, 0.6, str(i + 1), p["primary"], WHITE, 20)
            _text(s, cx + 1.1, cy + 0.3, cw - 1.4, 0.6, _clip(head, 34), 19, p["dark"],
                  bold=True, font=HEAD, anchor=MSO_ANCHOR.MIDDLE)
            _text(s, cx + 0.3, cy + 1.1, cw - 0.6, ch - 1.3,
                  _fit(body, cw - 0.6, ch - 1.3, 16), 16, p["dark"])
    return s, False


def _lay_split(b, spec):
    p, s = b.p, b.new(False)
    _shape(s, ROUND, 8.45, 0.7, 4.18, 6.0, fill=p["primary"], radius=0.05)
    _shape(s, OVAL, 11.05, 5.0, 1.2, 1.2, line=p["accent"], line_w=3)
    _head(b, s, spec, w=7.3)
    bullets = spec.get("bullets") or [h for h, _ in _norm_items(spec)]
    _bullets(s, bullets[:5], MX, 2.0, 7.2, 4.6, 20, p["dark"], p["primary"])
    label = _clip(spec.get("callout_label") or "KEY IDEA", 24).upper()
    _text(s, 8.85, 1.2, 3.4, 0.35, label, 13, p["accent"], bold=True)
    call = _fit(spec.get("callout") or spec.get("subtitle") or "", 3.4, 3.3, 26, 0.58)
    _text(s, 8.85, 1.8, 3.4, 3.3, call, 26, WHITE, bold=True, font=HEAD)
    return s, False


def _lay_stats(b, spec):
    p, s = b.p, b.new(True)
    _title(s, _clip(spec.get("title"), 80), MX, 0.55, W - 2 * MX, 1.1, 34, WHITE)
    stats = [x for x in (spec.get("stats") or []) if isinstance(x, dict)][:4]
    if not stats:
        stats = [{"value": h, "label": t} for h, t in _norm_items(spec)[:4]]
    n = max(len(stats), 1)
    gap = 0.4
    cw = (W - 2 * MX - gap * (n - 1)) / n
    dim = _blend(p["dark"], p["tint"], 0.8)
    for i, st in enumerate(stats):
        cx = MX + i * (cw + gap)
        _shape(s, ROUND, cx, 2.3, cw, 3.6, fill=p["primary"], radius=0.06)
        val = _clip(st.get("value"), 9)
        size = 60 if len(val) <= 5 else 48 if len(val) <= 7 else 38
        _text(s, cx + 0.35, 2.7, cw - 0.7, 1.3, val, size, p["accent"], bold=True,
              font=HEAD, anchor=MSO_ANCHOR.MIDDLE)
        _text(s, cx + 0.35, 4.15, cw - 0.7, 1.5, _fit(st.get("label"), cw - 0.7, 1.5, 20), 20, WHITE)
    return s, True


def _lay_steps(b, spec):
    p, s = b.p, b.new(False)
    _head(b, s, spec)
    items = _norm_items(spec)[:5] or [("", "")]
    n = len(items)
    colw = (W - 2 * MX) / n
    d, cy = 0.95, 2.55
    centers = [MX + colw * (i + 0.5) for i in range(n)]
    if n > 1:
        ln = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(centers[0]), Inches(cy + d / 2),
                                    Inches(centers[-1]), Inches(cy + d / 2))
        ln.line.color.rgb = _rgb(_blend(p["tint"], p["muted"], 0.35))
        ln.line.width = Pt(3)
    for i, (head, body) in enumerate(items):
        c = centers[i]
        _badge(s, c - d / 2, cy, d, str(i + 1), p["primary"], WHITE, 28)
        tw = colw - 0.4
        _text(s, c - tw / 2, cy + d + 0.4, tw, 0.9, _clip(head, 30), 22, p["dark"],
              bold=True, font=HEAD, align=PP_ALIGN.CENTER)
        _text(s, c - tw / 2, cy + d + 1.3, tw, 2.0, _fit(body, tw, 2.0, 17), 17, p["dark"],
              align=PP_ALIGN.CENTER)
    return s, False


def _lay_compare(b, spec):
    p, s = b.p, b.new(False)
    _head(b, s, spec)
    gap, cw, y0, ch = 0.4, (W - 2 * MX - 0.4) / 2, 1.95, 4.75
    for i, key in enumerate(("left", "right")):
        side = spec.get(key) if isinstance(spec.get(key), dict) else {}
        cx = MX + i * (cw + gap)
        dark_card = i == 1
        _shape(s, ROUND, cx, y0, cw, ch, fill=p["primary"] if dark_card else p["tint"], radius=0.05)
        fg = WHITE if dark_card else p["dark"]
        _text(s, cx + 0.45, y0 + 0.4, cw - 0.9, 0.6, _clip(side.get("heading"), 30), 24, fg,
              bold=True, font=HEAD)
        _bullets(s, side.get("bullets") or [], cx + 0.45, y0 + 1.3, cw - 0.9, ch - 1.6, 20, fg,
                 p["accent"] if dark_card else p["primary"])
    return s, False


def _lay_quote(b, spec):
    p, s = b.p, b.new(True)
    _title(s, _clip(spec.get("title"), 40).upper(), 0.9, 0.9, 9, 0.5, 14, p["accent"], font=BODY)
    _text(s, 0.8, 1.2, 2, 1.8, "“", 160, p["accent"], bold=True, font=HEAD)
    quote = _fit(spec.get("callout") or spec.get("subtitle") or "", 10.5, 3.2, 38, 0.58)
    _text(s, 0.9, 2.8, 10.8, 3.2, quote, 38, WHITE, bold=True, font=HEAD)
    if spec.get("callout_label"):
        _text(s, 0.9, 6.3, 10, 0.4, _clip(spec["callout_label"], 60), 16,
              _blend(p["dark"], p["tint"], 0.7))
    return s, True


def _lay_closing(b, spec):
    p, s = b.p, b.new(True)
    _shape(s, OVAL, -1.2, 4.3, 4.0, 4.0, fill=p["primary"])
    _shape(s, OVAL, 4.3, 0.5, 1.0, 1.0, line=p["accent"], line_w=3)
    title = _clip(spec.get("title"), 50)
    size = 44 if len(title) <= 22 else 36
    _title(s, title, 0.9, 1.5, 5.2, 2.6, size, WHITE)
    lines = spec.get("bullets") or [h or t for h, t in _norm_items(spec)]
    for i, line in enumerate(lines[:4]):
        y = 1.3 + i * 1.35
        _badge(s, 6.9, y, 0.6, str(i + 1), p["accent"], p["dark"], 20)
        _text(s, 7.75, y - 0.1, 4.9, 1.15, _fit(line, 4.9, 1.15, 20), 20, WHITE,
              anchor=MSO_ANCHOR.MIDDLE)
    return s, True


LAYOUTS = {"title": _lay_title, "cards": _lay_cards, "split": _lay_split, "stats": _lay_stats,
           "steps": _lay_steps, "compare": _lay_compare, "quote": _lay_quote, "closing": _lay_closing}


def _footer(b, s, i, total, dark):
    col = _blend(b.p["dark"], b.p["tint"], 0.55) if dark else b.p["muted"]
    _text(s, MX, 7.0, 8, 0.25, _clip(b.title, 60), 10, col)
    _text(s, W - MX - 1.5, 7.0, 1.5, 0.25, f"{i} / {total}", 10, col, align=PP_ALIGN.RIGHT)


def _fade(slide):
    ns = "http://schemas.openxmlformats.org/presentationml/2006/main"
    tr = etree.fromstring(f'<p:transition xmlns:p="{ns}" spd="med"><p:fade/></p:transition>')
    el = slide._element
    anchor = el.find(f"{{{ns}}}clrMapOvr")
    if anchor is None:
        anchor = el.find(f"{{{ns}}}cSld")
    anchor.addnext(tr)


def create_presentation(args):
    title = args.get("title") or "Presentation"
    pal = PALETTES.get(args.get("palette"), PALETTES["midnight"])
    specs = [x for x in (args.get("slides") or []) if isinstance(x, dict)][:15]
    if not specs:
        return "No slides were provided."
    print(f"[Creating deck: {title} ({len(specs)} slides)]")
    if specs[0].get("layout") != "title":
        specs.insert(0, {"layout": "title", "title": title})
    deck = _Deck(title, pal)
    total = len(specs)
    for i, spec in enumerate(specs, 1):
        fn = LAYOUTS.get(spec.get("layout"), _lay_cards if spec.get("items") else _lay_split)
        s, dark = fn(deck, spec)
        if i > 1:
            _footer(deck, s, i, total, dark)
        if spec.get("notes"):
            s.notes_slide.notes_text_frame.text = str(spec["notes"])
        _fade(s)
    path = output_path(title, "pptx")
    deck.prs.save(path)
    opened = after_create(path)
    return f"Saved {path.rsplit('/', 1)[-1]} ({total} slides) in the 'documents' folder.{opened}"


HANDLERS = {"create_presentation": create_presentation}

