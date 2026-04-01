---
name: document-artifact-rendering
display_name: Document Artifact Rendering
description: Render and verify document artifacts using the runtime capabilities available in the current sandbox workspace.
homepage: https://linx.local/skills/document-artifact-rendering
metadata:
  category: documents
  tags:
    - documents
    - rendering
    - pdf
    - delivery
  curated: true
gating:
  binaries:
    - python3
---

# Document Artifact Rendering

Use this skill when the user needs a deliverable document artifact rendered from an existing source file, especially PDF output from Markdown, HTML, Office documents, or plain text.

## Required workflow

1. Read the authoritative runtime capability snapshot from `runtime_capabilities.capability_snapshot_path` when it exists.
2. Use the bundled scripts in this package instead of hand-writing ad-hoc `fpdf`, font download, or one-off rendering logic.
3. Render the artifact first, then verify it with the bundled verifier before claiming success.
4. If the bundled renderer reports missing capabilities, tell the user exactly which capability is missing.

## Primary entrypoint

Run:

```bash
bash {baseDir}/scripts/render_document.sh --input /workspace/input/source.md --output /workspace/output/final.pdf --capabilities /workspace/.linx_runtime/capabilities.json
```

## What the scripts do

- `render_document.sh`: selects the best available renderer for the input file type
- `render_text_pdf.py`: generates plain-text style PDFs with ReportLab
- `verify_artifact.py`: validates the generated PDF and checks extracted text

## Rendering rules

- Office and HTML files use LibreOffice when available.
- Markdown requires both `pandoc` and `libreoffice` for the bridge path.
- Text-like sources use ReportLab and runtime-available CJK font recommendations.
- Do not fall back to classic `fpdf` for multilingual output.

## Failure handling

- If the capability snapshot file is missing, the helper scripts may probe the current environment directly.
- If verification fails, report the failure and do not claim the artifact was successfully delivered.

## References

- Renderer selection matrix: `{baseDir}/references/renderer-selection.md`
- Capability snapshot contract: `{baseDir}/references/capability-contract.md`
