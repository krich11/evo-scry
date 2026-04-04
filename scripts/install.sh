#!/usr/bin/env bash
set -euo pipefail

# evo-scry systemd installation script
# Run as root or with sudo

INSTALL_DIR="/opt/evo-scry"
CONFIG_DIR="/etc/evo-scry"
SERVICE_USER="evo-scry"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== evo-scry systemd installer ==="
echo ""

# Check for root
if [[ $EUID -ne 0 ]]; then
  echo "Error: This script must be run as root (use sudo)."
  exit 1
fi

# Check for node
if ! command -v node &>/dev/null; then
  echo "Error: Node.js is required but not found in PATH."
  exit 1
fi

NODE_VERSION=$(node --version)
echo "Found Node.js $NODE_VERSION"

# Create service user
if ! id "$SERVICE_USER" &>/dev/null; then
  echo "Creating service user: $SERVICE_USER"
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
else
  echo "Service user $SERVICE_USER already exists"
fi

# Install application
echo "Installing to $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -r "$PROJECT_DIR/dist" "$INSTALL_DIR/"
cp -r "$PROJECT_DIR/node_modules" "$INSTALL_DIR/"
cp "$PROJECT_DIR/package.json" "$INSTALL_DIR/"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# Install config
echo "Installing config to $CONFIG_DIR"
mkdir -p "$CONFIG_DIR"
if [[ ! -f "$CONFIG_DIR/evo-scry.env" ]]; then
  cp "$PROJECT_DIR/systemd/evo-scry.env" "$CONFIG_DIR/evo-scry.env"
  chmod 600 "$CONFIG_DIR/evo-scry.env"
  chown "$SERVICE_USER:$SERVICE_USER" "$CONFIG_DIR/evo-scry.env"
  echo "  Created $CONFIG_DIR/evo-scry.env (edit with your settings)"
else
  echo "  Config already exists, not overwriting"
fi

# Install systemd service
echo "Installing systemd service"
cp "$PROJECT_DIR/systemd/evo-scry.service" /etc/systemd/system/evo-scry.service
systemctl daemon-reload

echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit /etc/evo-scry/evo-scry.env with your settings"
echo "  2. Enable the service:  systemctl enable evo-scry"
echo "  3. Start the service:   systemctl start evo-scry"
echo "  4. Check status:        systemctl status evo-scry"
echo "  5. View logs:           journalctl -u evo-scry -f"
echo ""
echo "MCP endpoint will be at: http://localhost:3000/mcp"
echo "Health check:            http://localhost:3000/health"
