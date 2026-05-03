"""Fill the capstone template DOCX with the GreenScale project report.

Loads the original "CAPSTONE PROJECT REPORT.docx", walks paragraphs,
replaces cover-page placeholders, inserts content after each section
heading, and writes the result to frontend/public/report.docx.
This preserves the template's exact styling (Times New Roman, sizes,
bold weights, layout) byte-for-byte except for the parts we add.

Run from project root:  python3 build/generate_report.py
"""
from __future__ import annotations
import json
import re
import sys
import shutil
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "CAPSTONE PROJECT REPORT.docx"
OUT = ROOT / "frontend" / "public" / "report.docx"
CONTENT = json.loads((ROOT / "build" / "report_content.json").read_text())


def set_run_text(run, text: str):
    """Replace a run's text safely."""
    run.text = text


def set_paragraph_text(p, text: str):
    """Set paragraph text while preserving the first run's formatting.

    All other runs are removed. The first run's formatting becomes the
    formatting of the new text.
    """
    runs = list(p.runs)
    if runs:
        runs[0].text = text
        for r in runs[1:]:
            r._element.getparent().remove(r._element)
    else:
        p.add_run(text)


def insert_paragraph_after(paragraph, text: str = "", style: str | None = None,
                           bold: bool | None = None, italic: bool | None = None,
                           font_name: str = "Times New Roman", size_pt: float = 12,
                           align=None) -> "Paragraph":
    """Insert a new paragraph immediately after the given paragraph."""
    from docx.oxml import OxmlElement

    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    from docx.text.paragraph import Paragraph
    p = Paragraph(new_p, paragraph._parent)
    if style:
        try:
            p.style = paragraph.part.document.styles[style]
        except KeyError:
            pass
    if align is not None:
        p.alignment = align
    if text:
        run = p.add_run(text)
        run.font.name = font_name
        rFonts = run._element.rPr.rFonts if run._element.rPr is not None and run._element.rPr.rFonts is not None else None
        # ensure east-asia / cs fonts also set
        from docx.oxml import OxmlElement as _OE
        rPr = run._element.get_or_add_rPr()
        rFonts = rPr.find(qn('w:rFonts'))
        if rFonts is None:
            rFonts = _OE('w:rFonts')
            rPr.insert(0, rFonts)
        rFonts.set(qn('w:ascii'), font_name)
        rFonts.set(qn('w:hAnsi'), font_name)
        rFonts.set(qn('w:cs'), font_name)
        run.font.size = Pt(size_pt)
        if bold is not None:
            run.bold = bold
        if italic is not None:
            run.italic = italic
    return p


# -----------------------------------------------------------------------------
# Cover page replacement table
# -----------------------------------------------------------------------------
COVER_REPLACEMENTS = {
    "Title of Project":
        CONTENT["title"],
    "Name of Student:":
        f"Name of Student: {CONTENT['student_name']}",
    "Registration Number:":
        f"Registration Number: {CONTENT['reg_no']}",
    "Course with Specialization:":
        f"Course with Specialization: {CONTENT['course']}",
    "Semester:":
        f"Semester: {CONTENT['semester']}",
    "Capstone Mentor:":
        f"Capstone Mentor: {CONTENT['mentor']}",
}

# -----------------------------------------------------------------------------
# Section heading -> body paragraphs (in order)
# -----------------------------------------------------------------------------
SECTION_BODY = CONTENT["sections"]
QUESTION_ANSWERS = CONTENT["qa"]   # list of {"q": "...", "a": "..."}
REFERENCES = CONTENT["references"] # list of strings


def main():
    if not TEMPLATE.exists():
        print(f"ERROR: template not found at {TEMPLATE}", file=sys.stderr)
        sys.exit(2)

    doc = Document(str(TEMPLATE))

    def all_paragraphs(d):
        """Yield every paragraph in the doc, including inside tables."""
        for p in d.paragraphs:
            yield p
        for t in d.tables:
            for row in t.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        yield p

    # 1) Cover page exact-match replacements (incl. table cells)
    for p in all_paragraphs(doc):
        txt = p.text.strip()
        if txt in COVER_REPLACEMENTS:
            set_paragraph_text(p, COVER_REPLACEMENTS[txt])

    # 2) Insert content after each known section heading.
    # Use exact heading match. We insert paragraphs *in reverse list* so
    # that we don't disturb later iteration.
    inserted_after = set()

    # Find Acknowledgement and insert acknowledgment text
    for p in list(doc.paragraphs):
        t = p.text.strip()
        if t == "Acknowledgement" and "Acknowledgement" not in inserted_after:
            anchor = p
            for line in CONTENT["acknowledgement"]:
                anchor = insert_paragraph_after(
                    anchor, line, size_pt=12, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                )
            inserted_after.add("Acknowledgement")
        elif t == "Abstract" and "Abstract" not in inserted_after:
            anchor = p
            for line in CONTENT["abstract"]:
                anchor = insert_paragraph_after(
                    anchor, line, size_pt=12, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                )
            inserted_after.add("Abstract")
        elif t == "List of Figures" and "List of Figures" not in inserted_after:
            anchor = p
            for fig in CONTENT["figures"]:
                anchor = insert_paragraph_after(anchor, fig, size_pt=12)
            inserted_after.add("List of Figures")
        elif t == "List of Tables" and "List of Tables" not in inserted_after:
            anchor = p
            for tab in CONTENT["tables"]:
                anchor = insert_paragraph_after(anchor, tab, size_pt=12)
            inserted_after.add("List of Tables")
        elif t in SECTION_BODY and t not in inserted_after:
            anchor = p
            paragraphs_to_add = SECTION_BODY[t]
            for para in paragraphs_to_add:
                anchor = insert_paragraph_after(
                    anchor, para, size_pt=12,
                    align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                )
            inserted_after.add(t)

    # 3) Q&A: find each question paragraph and insert answer right after it.
    qa_map = {q["q"].rstrip().rstrip("?") + "?": q["a"] for q in QUESTION_ANSWERS}
    qa_seen = set()
    for p in list(doc.paragraphs):
        t = p.text.strip()
        # the template questions sometimes have trailing whitespace
        norm = t.rstrip()
        if norm.endswith("?"):
            for tmpl_q, ans in qa_map.items():
                if tmpl_q.lower().startswith(norm[:30].lower()) and tmpl_q not in qa_seen:
                    anchor = p
                    anchor = insert_paragraph_after(
                        anchor, "Answer: " + ans, size_pt=12,
                        align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                    )
                    qa_seen.add(tmpl_q)
                    break

    # 4) References: insert after the References heading
    for p in list(doc.paragraphs):
        if p.text.strip() == "References" and "References" not in inserted_after:
            anchor = p
            for i, ref in enumerate(REFERENCES, start=1):
                anchor = insert_paragraph_after(
                    anchor, f"[{i}] {ref}", size_pt=12,
                )
            inserted_after.add("References")
            break

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUT))
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
    print(f"sections filled: {sorted(inserted_after)}")
    print(f"questions answered: {len(qa_seen)} / {len(QUESTION_ANSWERS)}")


if __name__ == "__main__":
    main()
