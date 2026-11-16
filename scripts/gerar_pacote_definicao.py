"""Gera o PDF do pacote #62 a partir de Markdown restrito (títulos, listas e parágrafos)."""

from html import escape
from pathlib import Path
import re

import fitz
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, PageBreak


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs/definicao/pacote-definicao.md"
OUTPUT = SOURCE.with_suffix(".pdf")


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#d4dce5"))
    canvas.line(42, 35, A4[0] - 42, 35)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#536173"))
    canvas.drawString(42, 23, "Grupo 11 | Desafio 02 | Proposta para revisão")
    canvas.drawRightString(A4[0] - 42, 23, f"{doc.page} / 4")
    canvas.restoreState()


def main():
    styles = {
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10,
                               leading=14, spaceAfter=7, alignment=TA_LEFT),
        "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=18,
                             leading=22, spaceAfter=12, textColor=colors.HexColor("#163b59")),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=14,
                             leading=18, spaceAfter=10, textColor=colors.HexColor("#163b59")),
        "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=11,
                             leading=15, spaceBefore=5, spaceAfter=6),
    }
    source = SOURCE.read_text(encoding="utf-8")
    sections = source.split("\n---\n")
    if len(sections) != 4:
        raise ValueError("O pacote deve ter quatro seções separadas por ---.")

    story = []
    for index, section in enumerate(sections):
        if index:
            story.append(PageBreak())
        for block in re.split(r"\n\s*\n", section.strip()):
            for line in (block.splitlines() if block.startswith("- ") else [block]):
                style = "body"
                for prefix, key in [("### ", "h3"), ("## ", "h2"), ("# ", "h1")]:
                    if line.startswith(prefix):
                        style, line = key, line[len(prefix):]
                        break
                story.append(Paragraph(escape(" ".join(line.splitlines())), styles[style]))

    document = SimpleDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=42,
                                 rightMargin=42, topMargin=36, bottomMargin=46,
                                 title="Pacote de definição — Grupo 11",
                                 author="Grupo 11", invariant=1)
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    with fitz.open(OUTPUT) as pdf:
        if len(pdf) != 4:
            raise ValueError(f"PDF tem {len(pdf)} páginas; ajustar conteúdo antes de publicar.")
        for page in pdf:
            if not page.get_text().strip():
                raise ValueError("PDF contém página sem texto.")
    print(f"OK: {OUTPUT.relative_to(ROOT)}, quatro páginas A4.")


if __name__ == "__main__":
    main()
