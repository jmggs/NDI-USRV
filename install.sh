#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  NDI Signal Generator — Install script (Linux & macOS)
# ─────────────────────────────────────────────────────────────────────────────
set -e

INSTALL_DIR="${NDI_INSTALL_DIR:-/opt/ndi-generator}"
SERVICE_USER="${NDI_USER:-ndi}"
VENV="$INSTALL_DIR/venv"

GREEN='\033[0;32m'; AMBER='\033[0;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✔ $*${NC}"; }
warn() { echo -e "${AMBER}⚠ $*${NC}"; }
die()  { echo -e "${RED}✘ $*${NC}"; exit 1; }

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║        NDI Signal Generator  —  Installer            ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Detect OS ────────────────────────────────────────────────────────────────
OS="$(uname -s)"
case "$OS" in
  Linux)  PLATFORM="linux";;
  Darwin) PLATFORM="macos";;
  *)      die "Unsupported OS: $OS";;
esac
ok "Platform: $PLATFORM"

# ── Check Python ─────────────────────────────────────────────────────────────
PYTHON=$(command -v python3.11 || command -v python3.10 || command -v python3 || true)
[[ -z "$PYTHON" ]] && die "Python 3.10+ required. Install via your package manager."
PY_VER=$($PYTHON -c 'import sys; print(".".join(map(str,sys.version_info[:2])))')
ok "Python: $PYTHON ($PY_VER)"

# ── NDI SDK check ─────────────────────────────────────────────────────────────
echo ""
echo "──────────────────────────────────────────────────────"
echo "  NDI SDK (required for real NDI output)"
echo "  Download from: https://ndi.video/for-developers/ndi-sdk/download/"
echo "──────────────────────────────────────────────────────"

NDI_FOUND=false
if [[ "$PLATFORM" == "linux" ]]; then
  if ldconfig -p 2>/dev/null | grep -q libndi; then
    ok "NDI SDK library found"; NDI_FOUND=true
  else
    warn "NDI SDK not found. Install it then re-run: pip install ndi-python"
    warn "Running in MOCK mode until SDK is installed."
  fi
elif [[ "$PLATFORM" == "macos" ]]; then
  if [[ -f "/Library/NDI SDK for Apple/lib/macOS/libndi.dylib" ]]; then
    ok "NDI SDK found"; NDI_FOUND=true
  else
    warn "NDI SDK not found. Install from ndi.video then re-run install."
  fi
fi

# ── Create install directory ─────────────────────────────────────────────────
echo ""
echo "Installing to: $INSTALL_DIR"
sudo mkdir -p "$INSTALL_DIR"
sudo cp -r . "$INSTALL_DIR/"
ok "Files copied to $INSTALL_DIR"

# ── Virtual environment ───────────────────────────────────────────────────────
$PYTHON -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q
ok "Python venv created at $VENV"

if $NDI_FOUND; then
  "$VENV/bin/pip" install ndi-python -q && ok "ndi-python installed"
else
  warn "Skipping ndi-python (NDI SDK not found). Set NDI_MOCK=1 to test."
fi

# ── Uploads directory ─────────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR/uploads"

# ── systemd service (Linux only) ─────────────────────────────────────────────
if [[ "$PLATFORM" == "linux" ]] && command -v systemctl &>/dev/null; then
  echo ""
  echo "Installing systemd service…"

  # Create service user if not exists
  if ! id "$SERVICE_USER" &>/dev/null; then
    sudo useradd -r -s /sbin/nologin "$SERVICE_USER" 2>/dev/null || true
    ok "Service user '$SERVICE_USER' created"
  fi
  sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

  cat > /tmp/ndi-generator.service << EOF
[Unit]
Description=NDI Signal Generator
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV/bin/python main.py --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ndi-generator
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

  sudo mv /tmp/ndi-generator.service /etc/systemd/system/ndi-generator.service
  sudo systemctl daemon-reload
  sudo systemctl enable ndi-generator
  ok "systemd service installed and enabled"

  echo ""
  echo "  Start:   sudo systemctl start ndi-generator"
  echo "  Status:  sudo systemctl status ndi-generator"
  echo "  Logs:    journalctl -u ndi-generator -f"

elif [[ "$PLATFORM" == "macos" ]]; then
  # LaunchDaemon plist for macOS
  PLIST="/Library/LaunchDaemons/com.ndi-generator.plist"
  cat > /tmp/com.ndi-generator.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.ndi-generator</string>
  <key>ProgramArguments</key>
  <array>
    <string>$VENV/bin/python</string>
    <string>$INSTALL_DIR/main.py</string>
    <string>--host</string><string>0.0.0.0</string>
    <string>--port</string><string>8080</string>
  </array>
  <key>WorkingDirectory</key><string>$INSTALL_DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/var/log/ndi-generator.log</string>
  <key>StandardErrorPath</key><string>/var/log/ndi-generator.log</string>
</dict>
</plist>
EOF
  sudo mv /tmp/com.ndi-generator.plist "$PLIST"
  sudo launchctl load -w "$PLIST"
  ok "macOS LaunchDaemon installed and started"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Installation complete!                              ║"
echo "║                                                      ║"
echo "║  Web UI:   http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo localhost):8080   ║"
echo "║                                                      ║"
if ! $NDI_FOUND; then
echo "║  ⚠ NDI SDK not installed — mock mode active          ║"
echo "║  Install SDK from ndi.video then re-run install.sh   ║"
fi
echo "╚══════════════════════════════════════════════════════╝"
echo ""
