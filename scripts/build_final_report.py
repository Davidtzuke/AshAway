"""Build the final report (Word and PDF) from docs/final-report/AshAway_Final_Report_Group9.md.

Needs pandoc, LibreOffice (soffice) and python-docx. Run from the repository root:

    python scripts/build_final_report.py

Edit the Markdown and run this again; or edit the .docx directly and export it to PDF.
"""
import subprocess
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

DIR = Path("docs/final-report")
SOURCE = DIR / "AshAway_Final_Report_Group9.md"
DOCX = DIR / "AshAway_Final_Report_Group9.docx"
INK = RGBColor(0x1F, 0x29, 0x33)
ACCENT = RGBColor(0x9A, 0x34, 0x12)
HEAD_FILL = "E6EBF0"
RULE = "B8C2CC"


def reference_doc(path: Path) -> None:
    """Pandoc's default styles, adjusted: Calibri body, Arial headings, each chapter on a new page."""
    subprocess.run(["pandoc", "-o", str(path), "--print-default-data-file", "reference.docx"], check=True)
    doc = Document(path)
    # By exact name: python-docx would turn "Heading 1" into "heading 1", which pandoc's file lacks.
    styles = {s.name: s for s in doc.styles}
    for name in ("Normal", "Body Text", "First Paragraph", "Compact"):
        if name in styles:
            s = styles[name]
            s.font.name, s.font.size, s.font.color.rgb = "Calibri", Pt(11), INK
    for name, size in (("Title", 24), ("Subtitle", 15), ("Heading 1", 17), ("Heading 2", 13), ("Heading 3", 11.5)):
        s = styles[name]
        s.font.name, s.font.size, s.font.bold = "Arial", Pt(size), name != "Subtitle"
        s.font.color.rgb = ACCENT if name in ("Heading 1", "Title") else INK
        s.paragraph_format.space_before = Pt(14 if name.startswith("Heading") else 0)
        s.paragraph_format.space_after = Pt(6)
        s.paragraph_format.keep_with_next = True
    styles["Heading 1"].paragraph_format.page_break_before = True
    for name in ("Author", "Date"):
        if name in styles:
            styles[name].font.name, styles[name].font.size, styles[name].font.color.rgb = "Calibri", Pt(11), INK
    doc.save(path)


def borders(table) -> None:
    """Thin grey lines between rows, a shaded header row, small type, full width."""
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_pr = table._tbl.tblPr
    edges = OxmlElement("w:tblBorders")
    for edge in ("top", "bottom", "insideH"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single"), el.set(qn("w:sz"), "4"), el.set(qn("w:color"), RULE)
        edges.append(el)
    tbl_pr.append(edges)
    width = OxmlElement("w:tblW")
    width.set(qn("w:w"), "5000"), width.set(qn("w:type"), "pct")
    for old in tbl_pr.findall(qn("w:tblW")):
        tbl_pr.remove(old)
    tbl_pr.append(width)
    for r, row in enumerate(table.rows):
        for cell in row.cells:
            if r == 0:
                shade = OxmlElement("w:shd")
                shade.set(qn("w:val"), "clear"), shade.set(qn("w:color"), "auto"), shade.set(qn("w:fill"), HEAD_FILL)
                cell._tc.get_or_add_tcPr().append(shade)
            for p in cell.paragraphs:
                p.paragraph_format.space_after = Pt(1)
                for run in p.runs:
                    run.font.size = Pt(8.5)
                    if r == 0:
                        run.font.bold = True


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ref = Path(tmp) / "reference.docx"
        reference_doc(ref)
        subprocess.run(["pandoc", str(SOURCE), "-o", str(DOCX), "--reference-doc", str(ref), "--resource-path", str(DIR)], check=True)
    doc = Document(DOCX)
    for section in doc.sections:
        section.page_height, section.page_width = Cm(29.7), Cm(21.0)
        section.left_margin = section.right_margin = Cm(2.2)
        section.top_margin = section.bottom_margin = Cm(2.0)
    for table in doc.tables:
        borders(table)
    doc.save(DOCX)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(DIR), str(DOCX)],
                   check=True, capture_output=True)
    print("wrote", DOCX, "and", DOCX.with_suffix(".pdf"))


if __name__ == "__main__":
    main()
