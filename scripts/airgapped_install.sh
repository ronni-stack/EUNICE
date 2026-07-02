#!/usr/bin/env bash
# EUNICE Enterprise — Air-gapped install script (Week 8)
# Installs EUNICE from a local bundle without requiring an Internet connection,
# provided the bundle contains a pre-populated vendor/ wheel directory.
set -euo pipefail

BUNDLE_DIR="${1:-/opt/eunice-enterprise}"
INSTALL_DIR="${2:-/opt/eunice-enterprise}"
VENDOR_DIR="${BUNDLE_DIR}/vendor"
SERVICE_NAME="eunice-enterprise"

if [[ ! -d "${BUNDLE_DIR}" ]]; then
    echo "[ERROR] Bundle directory not found: ${BUNDLE_DIR}"
    echo "Usage: $0 <bundle_dir> [install_dir]"
    exit 1
fi

echo "[AIRGAP] Installing EUNICE Enterprise from ${BUNDLE_DIR} to ${INSTALL_DIR}..."

mkdir -p "${INSTALL_DIR}"
rsync -a --exclude='vendor' "${BUNDLE_DIR}/" "${INSTALL_DIR}/"
mkdir -p "${INSTALL_DIR}/data"

python3 -m venv "${INSTALL_DIR}/venv"

if [[ -d "${VENDOR_DIR}" && -n "$(ls -A "${VENDOR_DIR}")" ]]; then
    echo "[AIRGAP] Installing from local vendor wheelhouse..."
    "${INSTALL_DIR}/venv/bin/pip" install --no-index --find-links "${VENDOR_DIR}" -r "${INSTALL_DIR}/requirements.txt"
else
    echo "[WARN] No vendor/ wheelhouse found; falling back to online install (not air-gapped)."
    "${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"
fi

# Install systemd service
mkdir -p /etc/systemd/system
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=EUNICE Enterprise
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=-${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"

echo "[AIRGAP] Installation complete. Start with: systemctl start ${SERVICE_NAME}"
