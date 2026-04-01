#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify rendered PDF artifact")
    parser.add_argument("--file", required=True)
    parser.add_argument("--source", required=False)
    parser.add_argument("--capabilities", required=False)
    return parser


def _extract_with_pypdf(pdf_path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_with_pdfplumber(pdf_path: Path) -> str:
    import pdfplumber

    with pdfplumber.open(str(pdf_path)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _page_count(pdf_path: Path) -> int:
    from pypdf import PdfReader

    return len(PdfReader(str(pdf_path)).pages)


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text or ""))


def _expected_snippets(source_text: str) -> list[str]:
    snippets = []
    for raw_line in source_text.splitlines():
        line = " ".join(raw_line.strip().split())
        if not line:
            continue
        snippets.append(line[:16] if _contains_cjk(line) else line[:24])
        if len(snippets) >= 4:
            break
    return [snippet for snippet in snippets if snippet]


def main() -> int:
    args = _parser().parse_args()
    pdf_path = Path(args.file)
    source_path = Path(args.source) if args.source else None

    result = {
        "ok": False,
        "file": str(pdf_path),
        "exists": pdf_path.exists(),
        "size_bytes": pdf_path.stat().st_size if pdf_path.exists() else 0,
        "page_count": 0,
        "extractor": None,
        "text_check_passed": True,
        "error": None,
    }

    if not pdf_path.exists():
        result["error"] = "output file does not exist"
        print(json.dumps(result, ensure_ascii=False))
        return 1

    try:
        result["page_count"] = _page_count(pdf_path)
        extracted_text = ""
        try:
            extracted_text = _extract_with_pypdf(pdf_path)
            result["extractor"] = "pypdf"
        except Exception:
            extracted_text = _extract_with_pdfplumber(pdf_path)
            result["extractor"] = "pdfplumber"

        if source_path and source_path.exists():
            source_text = source_path.read_text(encoding="utf-8")
            if _contains_cjk(source_text):
                snippets = _expected_snippets(source_text)
                result["text_check_passed"] = any(snippet in extracted_text for snippet in snippets)

        result["ok"] = (
            result["size_bytes"] > 0
            and result["page_count"] > 0
            and result["text_check_passed"]
        )
    except Exception as exc:
        result["error"] = str(exc)

    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
