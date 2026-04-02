#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from common_capabilities import first_available_font, load_capabilities, resolve_font_path

_TEXT_ONLY_EXTENSIONS = {'.txt', '.json', '.csv'}
_REDIRECT_EXTENSIONS = {'.md', '.markdown'}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render text-like source files to PDF")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--capabilities", required=False)
    return parser


def _guard_supported_input(input_path: Path) -> None:
    suffix = input_path.suffix.lower()
    if suffix in _REDIRECT_EXTENSIONS:
        raise ValueError(
            "Markdown inputs must use render_document.sh instead of render_text_pdf.py. "
            "Run the packaged shell entrypoint so pandoc/libreoffice can preserve document layout."
        )
    if suffix not in _TEXT_ONLY_EXTENSIONS:
        allowed = ", ".join(sorted(_TEXT_ONLY_EXTENSIONS))
        raise ValueError(
            f"Unsupported direct ReportLab input type: {suffix or '(none)'}. "
            f"Use render_document.sh for document-like formats. Direct ReportLab inputs are limited to: {allowed}."
        )


def _register_font(capabilities: dict) -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    preferred_family = first_available_font(capabilities, preferred_key="recommended_sans")
    if preferred_family:
        font_path = resolve_font_path(preferred_family)
        if font_path:
            try:
                pdfmetrics.registerFont(TTFont("LinxCJK", font_path))
                return "LinxCJK"
            except Exception:
                pass

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


def main() -> int:
    args = _build_parser().parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        _guard_supported_input(input_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    capabilities = load_capabilities(args.capabilities)
    font_name = _register_font(capabilities)

    text = input_path.read_text(encoding="utf-8")

    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    doc = SimpleDocTemplate(str(output_path), pagesize=A4)
    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "LinxBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=11,
        leading=16,
        alignment=TA_LEFT,
    )

    story = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 8))
            continue
        story.append(Paragraph(escape(line).replace("\n", "<br/>"), body_style))
        story.append(Spacer(1, 6))

    if not story:
        story.append(Paragraph("(empty document)", body_style))

    doc.build(story)
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
