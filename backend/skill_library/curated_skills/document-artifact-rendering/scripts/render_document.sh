#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

INPUT=""
OUTPUT=""
CAPABILITIES="/workspace/.linx_runtime/capabilities.json"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --input)
      INPUT="$2"
      shift 2
      ;;
    --output)
      OUTPUT="$2"
      shift 2
      ;;
    --capabilities)
      CAPABILITIES="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [ -z "$INPUT" ] || [ -z "$OUTPUT" ]; then
  echo "Usage: render_document.sh --input <file> --output <file> [--capabilities <file>]" >&2
  exit 2
fi

INPUT_EXT=$(printf '%s' "$INPUT" | tr '[:upper:]' '[:lower:]')
OUTPUT_DIR=$(dirname "$OUTPUT")
mkdir -p "$OUTPUT_DIR"

convert_with_libreoffice() {
  src="$1"
  out="$2"
  base=$(basename "$src")
  stem=${base%.*}
  libreoffice --headless --convert-to pdf --outdir "$OUTPUT_DIR" "$src" >/tmp/linx_lo_stdout.log 2>/tmp/linx_lo_stderr.log
  generated="$OUTPUT_DIR/$stem.pdf"
  if [ ! -f "$generated" ]; then
    echo "LibreOffice conversion did not create expected output: $generated" >&2
    cat /tmp/linx_lo_stderr.log >&2 || true
    exit 1
  fi
  mv "$generated" "$out"
}

case "$INPUT_EXT" in
  *.doc|*.docx|*.ppt|*.pptx|*.odt|*.html|*.htm)
    if ! command -v libreoffice >/dev/null 2>&1; then
      echo "Missing capability: libreoffice" >&2
      exit 1
    fi
    convert_with_libreoffice "$INPUT" "$OUTPUT"
    ;;
  *.md|*.markdown)
    if ! command -v pandoc >/dev/null 2>&1; then
      echo "Missing capability: pandoc" >&2
      exit 1
    fi
    if ! command -v libreoffice >/dev/null 2>&1; then
      echo "Missing capability: libreoffice" >&2
      exit 1
    fi
    TMP_DIR=$(mktemp -d)
    TMP_DOCX="$TMP_DIR/bridge.docx"
    pandoc "$INPUT" -o "$TMP_DOCX"
    convert_with_libreoffice "$TMP_DOCX" "$OUTPUT"
    rm -rf "$TMP_DIR"
    ;;
  *.txt|*.json|*.csv)
    python3 "$SCRIPT_DIR/render_text_pdf.py" --input "$INPUT" --output "$OUTPUT" --capabilities "$CAPABILITIES"
    ;;
  *)
    echo "Unsupported input type for document-artifact-rendering: $INPUT" >&2
    exit 1
    ;;
esac

python3 "$SCRIPT_DIR/verify_artifact.py" --file "$OUTPUT" --source "$INPUT" --capabilities "$CAPABILITIES"
