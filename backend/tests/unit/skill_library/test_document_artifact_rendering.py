from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_render_text_pdf_rejects_markdown_input(tmp_path: Path) -> None:
    script_path = (
        Path(__file__).resolve().parents[3]
        / 'skill_library'
        / 'curated_skills'
        / 'document-artifact-rendering'
        / 'scripts'
        / 'render_text_pdf.py'
    )
    input_path = tmp_path / 'sample.md'
    output_path = tmp_path / 'sample.pdf'
    input_path.write_text('# title\n\n正文', encoding='utf-8')

    completed = subprocess.run(
        [
            sys.executable,
            str(script_path),
            '--input',
            str(input_path),
            '--output',
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert 'render_document.sh' in completed.stderr
    assert not output_path.exists()
