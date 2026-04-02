# Renderer Selection

- Office-like and HTML sources: use `libreoffice --headless --convert-to pdf`
- Markdown: use `bash {baseDir}/scripts/render_document.sh ...`, which applies the `pandoc -> docx` bridge and then `libreoffice -> pdf`
- Plain text / CSV / JSON: use `render_text_pdf.py` with ReportLab
- Never call `render_text_pdf.py` directly on `.md` / `.markdown`; that skips the document renderer and usually degrades layout quality
- Do not fall back to classic `fpdf` for multilingual output
