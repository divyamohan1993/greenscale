"""Generate frontend/public/report.html from report_content.json.

Mirrors the docx template's visual structure: cover page (Times New Roman,
bold lines), TOC, sections each as a "page" div for print-fidelity, Q&A,
references. Web view also has a download button for the matching docx.
"""
from __future__ import annotations
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = json.loads((ROOT / "build" / "report_content.json").read_text())
OUT = ROOT / "frontend" / "public" / "report.html"


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def section_block(title: str, paragraphs: list[str]) -> str:
    body = "\n".join(f'    <p class="body-p">{esc(p)}</p>' for p in paragraphs)
    return f"""<section class="page">
  <h2 class="section-h">{esc(title)}</h2>
{body}
</section>"""


def main():
    c = CONTENT

    # cover page
    cover = f"""<section class="page cover">
  <p class="cover-title">{esc(c['title'])}</p>
  <p class="cover-line">Synopsis submitted for the partial fulfilment of the degree of</p>
  <p class="cover-line">BACHELOR OF TECHNOLOGY (CSE)</p>
  <div class="cover-spacer"></div>
  <div class="cover-info">
    <div class="field">Name of Student: {esc(c['student_name'])}</div>
    <div class="field">Capstone Mentor: {esc(c['mentor'])}</div>
    <div class="field">Registration Number: {esc(c['reg_no'])}</div>
    <div class="field">Course with Specialization: {esc(c['course'])}</div>
    <div class="field">Semester: {esc(c['semester'])}</div>
  </div>
  <div class="cover-spacer"></div>
  <p class="cover-uni">YOGANANDA SCHOOL OF AI, COMPUTERS AND DATA SCIENCES</p>
  <p class="cover-uni">SHOOLINI UNIVERSITY OF BIOTECHNOLOGY AND MANAGEMENT SCIENCES</p>
  <p class="cover-uni">SOLAN, H.P., INDIA</p>
</section>"""

    # ack + abstract on their own pages
    ack = section_block("Acknowledgement", c["acknowledgement"])
    ab = section_block("Abstract", c["abstract"])

    # ToC
    toc_items = [
        "Acknowledgement", "Abstract", "Table of Contents",
        "List of Figures", "List of Tables",
    ] + list(c["sections"].keys()) + ["Questions", "References"]
    page_no = 1
    toc_html = []
    for i, item in enumerate(toc_items, start=1):
        toc_html.append(f'<li><a href="#sec-{i}">{esc(item)}</a><span class="pn">{i + 2}</span></li>')

    toc = f"""<section class="page">
  <h2 class="section-h">Table of Contents</h2>
  <ol class="toc">
    {"".join(toc_html)}
  </ol>
</section>"""

    # Lists
    figs = "\n".join(f'    <p class="body-p">{esc(f)}</p>' for f in c["figures"])
    tabs = "\n".join(f'    <p class="body-p">{esc(t)}</p>' for t in c["tables"])
    fig_page = f"""<section class="page"><h2 class="section-h">List of Figures</h2>
{figs}
</section>"""
    tab_page = f"""<section class="page"><h2 class="section-h">List of Tables</h2>
{tabs}
</section>"""

    # Sections
    sec_pages = []
    for title, paras in c["sections"].items():
        sec_pages.append(section_block(title, paras))

    # Q&A page
    qa_html = []
    for i, qa in enumerate(c["qa"], start=1):
        qa_html.append(f'<p class="qa-q">Q{i}. {esc(qa["q"])}</p>')
        qa_html.append(f'<p class="qa-a"><b>Answer:</b> {esc(qa["a"])}</p>')
    qa_page = f"""<section class="page"><h2 class="section-h">Questions</h2>
{"".join(qa_html)}
</section>"""

    # References
    refs = "\n".join(f'    <li>{esc(r)}</li>' for r in c["references"])
    refs_page = f"""<section class="page"><h2 class="section-h">References</h2>
  <ol class="refs">
{refs}
  </ol>
</section>"""

    # Final page
    body = "\n".join([cover, ack, ab, toc, fig_page, tab_page, *sec_pages, qa_page, refs_page])

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>GreenScale - Capstone Report - Anshuman Mohanty</title>
<meta name="description" content="Full capstone project report for GreenScale, by Anshuman Mohanty (B.Tech CSE Cloud Computing, GF202217744). Mirrors the university-supplied docx template; downloadable as docx." />
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/css/report.css?v=1" />
</head>
<body>

<div class="report-bar">
  <div class="left">
    <div class="logo">G</div>
    <div>GreenScale &mdash; Capstone Report</div>
  </div>
  <div class="actions">
    <a href="/">Dashboard</a>
    <a href="/pitch">Pitch</a>
    <a class="download" href="/report.docx" download>Download .docx</a>
  </div>
</div>

{body}

</body>
</html>
"""

    OUT.write_text(page)
    print(f"wrote {OUT} ({len(page)} bytes)")


if __name__ == "__main__":
    main()
