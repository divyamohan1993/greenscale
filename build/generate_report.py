"""Fill the capstone template DOCX with the GreenScale project report.

Loads the original "CAPSTONE PROJECT REPORT.docx", walks paragraphs,
replaces cover-page placeholders, inserts content after each section
heading, and writes the result to frontend/public/report.docx.
This preserves the template's exact styling (Times New Roman, sizes,
bold weights, layout) byte-for-byte except for the parts we add.

Body paragraphs are inserted with the same formatting the template uses
for its question paragraphs: Times New Roman 12pt, justified, line
spacing 1.5, regular weight - so the visual feel matches the template.

Run from project root:  python3 build/generate_report.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Twips
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING

# Body indent the template uses on its existing body (question) paragraphs.
# Verified against word/document.xml: <w:ind w:left="1276"/>.
TEMPLATE_BODY_INDENT_TWIPS = 1276

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "CAPSTONE PROJECT REPORT.docx"
OUT = ROOT / "frontend" / "public" / "report.docx"
CONTENT = json.loads((ROOT / "build" / "report_content.json").read_text())


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def set_paragraph_text(p, text: str):
    """Replace paragraph text, keeping the first run's formatting."""
    runs = list(p.runs)
    if runs:
        runs[0].text = text
        for r in runs[1:]:
            r._element.getparent().remove(r._element)
    else:
        p.add_run(text)


def _ensure_run_font(run, font_name="Times New Roman"):
    """Force ascii/hAnsi/cs/east-asia rFonts on a run."""
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.insert(0, rFonts)
    for k in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'):
        rFonts.set(qn(k), font_name)


def _strip_numbering(p):
    """Remove any list-numbering reference on this paragraph (numPr)."""
    pPr = p._element.find(qn('w:pPr'))
    if pPr is None:
        return
    numPr = pPr.find(qn('w:numPr'))
    if numPr is not None:
        pPr.remove(numPr)


def insert_paragraph_after(anchor, text: str = "",
                           style_name: str | None = "List Paragraph",
                           bold: bool = False, italic: bool = False,
                           font_name: str = "Times New Roman",
                           size_pt: float = 12,
                           align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                           line_spacing: float | None = 1.5,
                           strip_numbering: bool = True,
                           left_indent_twips: int | None = TEMPLATE_BODY_INDENT_TWIPS):
    """Insert a new paragraph immediately after `anchor` and return it.

    Defaults strictly match the template's body formatting (verified against
    its existing question paragraphs): pStyle=ListParagraph, ind left=1276,
    spacing line=360 (1.5), jc=both (JUSTIFY), Times New Roman 12pt regular.
    Numbering (numPr) is stripped so body paragraphs do NOT auto-number.
    """
    new_p = OxmlElement("w:p")
    anchor._p.addnext(new_p)
    from docx.text.paragraph import Paragraph
    p = Paragraph(new_p, anchor._parent)

    if style_name:
        try:
            p.style = anchor.part.document.styles[style_name]
        except KeyError:
            pass
    if strip_numbering:
        _strip_numbering(p)

    if align is not None:
        p.alignment = align
    if line_spacing is not None:
        p.paragraph_format.line_spacing = line_spacing
    if left_indent_twips is not None:
        p.paragraph_format.left_indent = Twips(left_indent_twips)

    if text:
        run = p.add_run(text)
        _ensure_run_font(run, font_name)
        run.font.size = Pt(size_pt)
        if bold:    run.bold = True
        if italic:  run.italic = True
    return p


def insert_qa_answer(anchor, answer_text: str):
    """Insert a Q&A answer that lines up with the auto-numbered question.

    Uses the exact same paragraph properties as the template's question
    paragraphs (List Paragraph, ind left=1276, line=360, jc=both) but with
    numbering stripped, so it does NOT get an auto-number and the list
    continues correctly on the next question.
    """
    new_p = OxmlElement("w:p")
    anchor._p.addnext(new_p)
    from docx.text.paragraph import Paragraph
    p = Paragraph(new_p, anchor._parent)
    try:
        p.style = anchor.part.document.styles["List Paragraph"]
    except KeyError:
        pass
    _strip_numbering(p)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.line_spacing = 1.5
    p.paragraph_format.left_indent = Twips(TEMPLATE_BODY_INDENT_TWIPS)

    label = p.add_run("Answer: ")
    _ensure_run_font(label)
    label.font.size = Pt(12); label.bold = True

    body = p.add_run(answer_text)
    _ensure_run_font(body)
    body.font.size = Pt(12)
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

SECTION_BODY = CONTENT["sections"]
QUESTION_ANSWERS = CONTENT["qa"]
REFERENCES = CONTENT["references"]


def main():
    if not TEMPLATE.exists():
        print(f"ERROR: template not found at {TEMPLATE}", file=sys.stderr)
        sys.exit(2)

    doc = Document(str(TEMPLATE))

    def all_paragraphs(d):
        for p in d.paragraphs:
            yield p
        for t in d.tables:
            for row in t.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        yield p

    # --- 1) cover page text replacements (tables included) ----------------
    for p in all_paragraphs(doc):
        txt = p.text.strip()
        if txt in COVER_REPLACEMENTS:
            set_paragraph_text(p, COVER_REPLACEMENTS[txt])

    # --- 2) insert content after each section heading ---------------------
    inserted_after: set[str] = set()

    for p in list(doc.paragraphs):
        t = p.text.strip()
        if t == "Acknowledgement" and "Acknowledgement" not in inserted_after:
            anchor = p
            for line in CONTENT["acknowledgement"]:
                anchor = insert_paragraph_after(anchor, line)
            inserted_after.add("Acknowledgement")

        elif t == "Abstract" and "Abstract" not in inserted_after:
            anchor = p
            for line in CONTENT["abstract"]:
                anchor = insert_paragraph_after(anchor, line)
            inserted_after.add("Abstract")

        elif t == "List of Figures" and "List of Figures" not in inserted_after:
            anchor = p
            for fig in CONTENT["figures"]:
                anchor = insert_paragraph_after(anchor, fig, align=WD_ALIGN_PARAGRAPH.LEFT)
            inserted_after.add("List of Figures")

        elif t == "List of Tables" and "List of Tables" not in inserted_after:
            anchor = p
            for tab in CONTENT["tables"]:
                anchor = insert_paragraph_after(anchor, tab, align=WD_ALIGN_PARAGRAPH.LEFT)
            inserted_after.add("List of Tables")

        elif t in SECTION_BODY and t not in inserted_after:
            anchor = p
            for para in SECTION_BODY[t]:
                anchor = insert_paragraph_after(anchor, para)
            inserted_after.add(t)

    # --- 3) Q&A: answer paragraph immediately after each question ---------
    qa_map = {qa["q"].strip(): qa["a"] for qa in QUESTION_ANSWERS}
    qa_seen: set[str] = set()
    for p in list(doc.paragraphs):
        t = p.text.strip()
        if not t.endswith("?"):
            continue
        # match by best prefix-overlap (template questions sometimes have trailing whitespace)
        for tmpl_q, ans in qa_map.items():
            key = tmpl_q[:30].lower()
            if t[:30].lower().startswith(key) and tmpl_q not in qa_seen:
                insert_qa_answer(p, ans)
                qa_seen.add(tmpl_q)
                break

    # --- 4) References list -----------------------------------------------
    for p in list(doc.paragraphs):
        if p.text.strip() == "References" and "References" not in inserted_after:
            anchor = p
            for i, ref in enumerate(REFERENCES, start=1):
                anchor = insert_paragraph_after(
                    anchor, f"[{i}] {ref}", align=WD_ALIGN_PARAGRAPH.LEFT
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
