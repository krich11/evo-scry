#!/usr/bin/env bash
# install.sh — Install evo-scry as a systemd service (Python version)
set -euo pipefail

INSTALL_DIR="/opt/evo-scry"
CONFIG_DIR="/etc/evo-scry"
SERVICE_USER="evo-scry"

echo "=== evo-scry Installer (Python) ==="

# Must be root
if [[ $EUID -ne 0 ]]; then
    echo "Error: Run as root (sudo ./install.sh)"
    exit 1
fi

# Check Python >= 3.11
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 not found. Install Python 3.11+."
    exit 1
fi
PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11 ]]; then
    echo "Error: Python 3.11+ required (found $PY_VERSION)"
    exit 1
fi
echo "Python $PY_VERSION found."

# Create service user
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --shell /usr/sbin/nologin --home-dir "$INSTALL_DIR" "$SERVICE_USER"
    echo "Created user: $SERVICE_USER"
fi

# Create install directory
mkdir -p "$INSTALL_DIR"

# Copy source
echo "Installing to $INSTALL_DIR..."
cp -r src/ "$INSTALL_DIR/"
cp pyproject.toml "$INSTALL_DIR/"
cp README.md "$INSTALL_DIR/" 2>/dev/null || true

# Create virtual environment and install
echo "Setting up Python virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install "$INSTALL_DIR"

# Set ownership
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# Config directory
mkdir -p "$CONFIG_DIR"
if [[ ! -f "$CONFIG_DIR/evo-scry.env" ]]; then
    cp systemd/evo-scry.env "$CONFIG_DIR/evo-scry.env"
    echo "Created config: $CONFIG_DIR/evo-scry.env"
else
    echo "Config exists: $CONFIG_DIR/evo-scry.env (not overwritten)"
fi
chmod 600 "$CONFIG_DIR/evo-scry.env"
chown "$SERVICE_USER:$SERVICE_USER" "$CONFIG_DIR/evo-scry.env"

# Install systemd service
cp systemd/evo-scry.service /etc/systemd/system/evo-scry.service
systemctl daemon-reload
echo "Installed systemd service."

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit /etc/evo-scry/evo-scry.env with your settings"
echo "  2. sudo systemctl enable evo-scry"
echo "  3. sudo systemctl start evo-scry"
echo "  4. sudo journalctl -u evo-scry -f"
echo ""
echo "Generate a Copilot token:"
echo "  $INSTALL_DIR/venv/bin/python -m evoscry.generate_copilot_token"
