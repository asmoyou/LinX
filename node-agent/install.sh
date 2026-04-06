#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_ROOT="${LINX_NODE_AGENT_INSTALL_ROOT:-$HOME/.linx-node-agent}"
BIN_DIR="${LINX_NODE_AGENT_BIN_DIR:-$HOME/.local/bin}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

mkdir -p "$INSTALL_ROOT" "$BIN_DIR"
rm -rf "$INSTALL_ROOT/venv"
"$PYTHON_BIN" -m venv "$INSTALL_ROOT/venv"
"$INSTALL_ROOT/venv/bin/pip" install --upgrade pip >/dev/null
"$INSTALL_ROOT/venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
cp "$SCRIPT_DIR/linx_node_agent.py" "$INSTALL_ROOT/linx_node_agent.py"
chmod +x "$INSTALL_ROOT/linx_node_agent.py"
cat > "$BIN_DIR/linx-node-agent" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
INSTALL_ROOT="${LINX_NODE_AGENT_INSTALL_ROOT:-$HOME/.linx-node-agent}"
exec "$INSTALL_ROOT/venv/bin/python" "$INSTALL_ROOT/linx_node_agent.py" "$@"
EOF
chmod +x "$BIN_DIR/linx-node-agent"

echo "Installed linx-node-agent to $BIN_DIR/linx-node-agent"
echo "If $BIN_DIR is not on your PATH, add: export PATH="$BIN_DIR:$PATH""
