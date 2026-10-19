"""Convert the project's Markdown reports into Word documents.

``pandoc`` is not installed on this machine, so the conversion is done with
``python-docx``.  The converter understands the subset of Markdown the reports
actually use: ATX headings, paragraphs, bold/italic/code spans, superscript
citations, bullet and numbered lists, block quotes, horizontal rules, pipe
tables and fenced code blocks.

Formatting follows Chinese academic convention:

* every run is black — code spans and links are distinguished by typeface, not
  by colour, so the document prints correctly in greyscale;
* tables are three-line tables (三线表): a heavy rule above the header, a light
  rule below it, a heavy rule at the bottom, and no vertical rules at all;
* citations are superscript bracketed numbers (``^[1]^`` in the source), and
  the reference list carries the matching ``[1]`` prefixes with a hanging
  indent.

Chinese text needs an explicit East-Asian font: Word ignores the Latin font for
CJK glyphs unless ``w:eastAsia`` is set, which ``python-docx`` does not expose
directly, so the run properties are patched here.

Usage::

    python -m hallmark_repro.md2docx docs/01_调研报告.md docs/01_调研报告.docx
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, Cm

BODY_FONT_ASCII = "Times New Roman"
BODY_FONT_CJK = "宋体"
HEAD_FONT_CJK = "黑体"
MONO_FONT = "Consolas"

BLACK = "000000"

#: Three-line-table rule weights, in eighths of a point.
RULE_HEAVY = 12        # 1.5 pt
RULE_LIGHT = 6         # 0.75 pt

#: A paragraph beginning with ``[n]`` is a reference entry.
REFERENCE_RE = re.compile(r"^\[\d+\]\s")


def _set_font(run, ascii_font: str, cjk_font: str, size: float | None = None,
              bold: bool | None = None, italic: bool | None = None,
              superscript: bool | None = None) -> None:
    run.font.name = ascii_font
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), ascii_font)
    rfonts.set(qn("w:hAnsi"), ascii_font)
    rfonts.set(qn("w:eastAsia"), cjk_font)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic
    if superscript is not None:
        run.font.superscript = superscript
    # Everything is black; the project's figures and tables are greyscale-safe.
    run.font.color.rgb = None
    color = rpr.find(qn("w:color"))
    if color is not None:
        rpr.remove(color)


INLINE_RE = re.compile(
    r"(\*\*.+?\*\*|`[^`]+`|\^\[[^\]]+\]\^|\*[^*\n]+?\*|\[[^\]]+\]\([^)]+\))",
    re.DOTALL,
)


def _add_inline(paragraph, text: str, *, size: float = 10.5, base_bold: bool = False,
                cjk_font: str = BODY_FONT_CJK) -> None:
    """Render inline Markdown spans into one paragraph."""
    for part in INLINE_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            run = paragraph.add_run(part[2:-2])
            _set_font(run, BODY_FONT_ASCII, cjk_font, size, bold=True)
        elif part.startswith("^[") and part.endswith("]^"):
            # Superscript citation: rendered in the body font so the bracket
            # digits sit on the same baseline grid as the surrounding text.
            run = paragraph.add_run(part[1:-1])
            _set_font(run, BODY_FONT_ASCII, cjk_font, size, superscript=True)
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            run = paragraph.add_run(part[1:-1])
            _set_font(run, MONO_FONT, cjk_font, size - 0.5)
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            run = paragraph.add_run(part[1:-1])
            _set_font(run, BODY_FONT_ASCII, cjk_font, size, italic=True)
        elif part.startswith("[") and "](" in part:
            label = part[1:part.index("](")]
            url = part[part.index("](") + 2:-1]
            run = paragraph.add_run(f"{label} ({url})")
            _set_font(run, BODY_FONT_ASCII, cjk_font, size)
        else:
            run = paragraph.add_run(part)
            _set_font(run, BODY_FONT_ASCII, cjk_font, size, bold=base_bold)


# ---------------------------------------------------------------------------
# Three-line tables
# ---------------------------------------------------------------------------

def _border(element_tag: str, size: int, val: str = "single") -> object:
    from docx.oxml import OxmlElement

    el = OxmlElement(element_tag)
    el.set(qn("w:val"), val)
    el.set(qn("w:sz"), str(size))
    el.set(qn("w:space"), "0")
    el.set(qn("w:color"), BLACK)
    return el


def _three_line_table(table) -> None:
    """Reduce a bordered table to a 三线表: three horizontal rules, no verticals.

    ``Table Grid`` draws a box around every cell.  Academic Chinese tables use
    only the outer top rule, the rule under the header row, and the outer bottom
    rule, with all vertical rules removed.
    """
    from docx.oxml import OxmlElement

    tbl_pr = table._tbl.tblPr
    existing = tbl_pr.find(qn("w:tblBorders"))
    if existing is not None:
        tbl_pr.remove(existing)
    borders = OxmlElement("w:tblBorders")
    for tag, size in (("w:top", RULE_HEAVY), ("w:bottom", RULE_HEAVY),
                      ("w:left", 0), ("w:right", 0),
                      ("w:insideH", 0), ("w:insideV", 0)):
        borders.append(_border(tag, size, "single" if size else "none"))
    tbl_pr.append(borders)

    def set_cell_border(cell, tag: str, size: int, val: str = "single") -> None:
        tc_pr = cell._tc.get_or_add_tcPr()
        tc_borders = tc_pr.find(qn("w:tcBorders"))
        if tc_borders is None:
            tc_borders = OxmlElement("w:tcBorders")
            tc_pr.append(tc_borders)
        old = tc_borders.find(qn(tag))
        if old is not None:
            tc_borders.remove(old)
        tc_borders.append(_border(tag, size, val))

    n_rows = len(table.rows)
    for j in range(len(table.columns)):
        # Heavy top rule on the header row.
        set_cell_border(table.rows[0].cells[j], "w:top", RULE_HEAVY)
        # Light rule under the header, separating it from the body.
        set_cell_border(table.rows[0].cells[j], "w:bottom", RULE_LIGHT)
        # Heavy bottom rule on the last row.
        if n_rows > 1:
            set_cell_border(table.rows[n_rows - 1].cells[j], "w:bottom", RULE_HEAVY)


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    # Split on unescaped pipes.
    cells, cur, esc = [], [], False
    for ch in line:
        if esc:
            cur.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == "|":
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    cells.append("".join(cur).strip())
    return cells


def _new_section(doc, landscape: bool):
    """Start a new section with the given orientation, keeping A4.

    A wide comparison table cannot be read in portrait A4: nine columns force
    the renderer to break words inside cells.  Switching to a landscape section
    for the duration of the table gives each column roughly 2.5x the width.
    """
    from docx.enum.section import WD_ORIENT, WD_SECTION

    section = doc.add_section(WD_SECTION.NEW_PAGE)
    if landscape:
        section.orientation = WD_ORIENT.LANDSCAPE
        section.page_width = Cm(29.7)
        section.page_height = Cm(21.0)
        for attr in ("left_margin", "right_margin"):
            setattr(section, attr, Cm(2.0))
        for attr in ("top_margin", "bottom_margin"):
            setattr(section, attr, Cm(2.0))
    else:
        section.orientation = WD_ORIENT.PORTRAIT
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        for attr in ("left_margin", "right_margin"):
            setattr(section, attr, Cm(2.6))
        for attr in ("top_margin", "bottom_margin"):
            setattr(section, attr, Cm(2.5))
    return section


def convert(md_path: Path, docx_path: Path) -> None:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    doc = Document()

    # Page setup: A4 with normal margins.
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    for attr in ("left_margin", "right_margin"):
        setattr(section, attr, Cm(2.6))
    for attr in ("top_margin", "bottom_margin"):
        setattr(section, attr, Cm(2.5))

    style = doc.styles["Normal"]
    style.font.size = Pt(10.5)
    style.font.name = BODY_FONT_ASCII
    style.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT_CJK)

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # --- blank
        if not stripped:
            i += 1
            continue

        # --- orientation switch for wide tables
        if stripped.startswith("<!--") and stripped.endswith("-->"):
            directive = stripped[4:-3].strip().lower()
            if directive in ("landscape", "portrait"):
                _new_section(doc, directive == "landscape")
            i += 1
            continue

        # --- horizontal rule
        if re.fullmatch(r"-{3,}|\*{3,}", stripped):
            p = doc.add_paragraph()
            pPr = p._p.get_or_add_pPr()
            pbdr = pPr.makeelement(qn("w:pBdr"), {})
            bottom = pbdr.makeelement(qn("w:bottom"), {
                qn("w:val"): "single", qn("w:sz"): "6", qn("w:space"): "1",
                qn("w:color"): "AAAAAA",
            })
            pbdr.append(bottom)
            pPr.append(pbdr)
            i += 1
            continue

        # --- heading
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            sizes = {1: 18, 2: 14, 3: 12, 4: 11, 5: 10.5, 6: 10.5}
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(12 if level <= 2 else 8)
            p.paragraph_format.space_after = Pt(6)
            if level == 1:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _add_inline(p, text, size=sizes[level], base_bold=True, cjk_font=HEAD_FONT_CJK)
            i += 1
            continue

        # --- fenced code block
        if stripped.startswith("```"):
            i += 1
            block: list[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                block.append(lines[i].rstrip("\n"))
                i += 1
            i += 1                                    # consume the closing fence
            for raw in block:
                p = doc.add_paragraph()
                p.paragraph_format.first_line_indent = Cm(0)
                p.paragraph_format.left_indent = Cm(0.6)
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.0
                run = p.add_run(raw if raw.strip() else "\u00a0")
                _set_font(run, MONO_FONT, MONO_FONT, 8.0)
            doc.add_paragraph()
            continue

        # --- table
        if stripped.startswith("|") and i + 1 < n and re.match(r"^\|[\s:\-|]+\|?$", lines[i + 1].strip()):
            header = _split_row(stripped)
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_split_row(lines[i]))
                i += 1
            table = doc.add_table(rows=1 + len(rows), cols=len(header))
            table.style = "Table Grid"
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            for j, h in enumerate(header):
                cell = table.rows[0].cells[j]
                cell.text = ""
                _add_inline(cell.paragraphs[0], h, size=8.5, base_bold=True)
            for r, row in enumerate(rows, start=1):
                for j in range(len(header)):
                    cell = table.rows[r].cells[j]
                    cell.text = ""
                    _add_inline(cell.paragraphs[0], row[j] if j < len(row) else "", size=8.5)
            _three_line_table(table)
            doc.add_paragraph()
            continue

        # --- bullet list
        m = re.match(r"^([-*+])\s+(.*)$", stripped)
        if m:
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_after = Pt(2)
            _add_inline(p, m.group(2))
            i += 1
            continue

        # --- reference entry: ``[n] ...`` with a hanging indent.
        if REFERENCE_RE.match(stripped):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.9)
            p.paragraph_format.first_line_indent = Cm(-0.9)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.2
            _add_inline(p, stripped)
            i += 1
            continue

        # --- numbered list.
        # The number is written out literally rather than handed to Word's
        # automatic numbering: python-docx's ``List Number`` style shares one
        # counter across the whole document, so a reference list would continue
        # from whatever numbered list appeared earlier (the references came out
        # as 5..20 instead of 1..16).  A literal prefix keeps the author's
        # numbering intact.
        m = re.match(r"^(\d+)[.)]\s+(.*)$", stripped)
        if m:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.74)
            p.paragraph_format.first_line_indent = Cm(-0.74)
            p.paragraph_format.space_after = Pt(2)
            _add_inline(p, f"{m.group(1)}. {m.group(2)}")
            i += 1
            continue

        # --- block quote
        if stripped.startswith(">"):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.8)
            _add_inline(p, stripped.lstrip("> ").strip(), size=10)
            i += 1
            continue

        # --- paragraph (join continuation lines)
        buf = [stripped]
        i += 1
        while i < n:
            nxt = lines[i].strip()
            if (not nxt or nxt.startswith("#") or nxt.startswith("|")
                    or nxt.startswith("```")
                    or nxt.startswith("<!--")
                    or re.match(r"^([-*+]|\d+[.)])\s+", nxt)
                    or REFERENCE_RE.match(nxt)
                    or re.fullmatch(r"-{3,}", nxt)):
                break
            buf.append(nxt)
            i += 1
        p = doc.add_paragraph()
        p.paragraph_format.first_line_indent = Cm(0.74)   # 首行缩进两字符
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.35
        _add_inline(p, " ".join(buf))

    docx_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(docx_path))


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(2)
    for src, dst in zip(sys.argv[1::2], sys.argv[2::2]):
        convert(Path(src), Path(dst))
        print(f"{src} -> {dst}")


if __name__ == "__main__":
    main()
