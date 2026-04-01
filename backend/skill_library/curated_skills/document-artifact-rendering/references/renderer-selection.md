# Renderer Selection

- Office-like and HTML sources: use `libreoffice --headless --convert-to pdf`
- Markdown: use `pandoc -> docx` bridge, then `libreoffice -> pdf`
- Plain text / CSV / JSON: use `render_text_pdf.py` with ReportLab
- Do not fall back to classic `fpdf` for multilingual output
