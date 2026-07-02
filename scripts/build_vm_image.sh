#!/usr/bin/env bash
# EUNICE Enterprise — VM image builder (Week 8)
# Packages the application into a deployable tarball with an install script
# and a systemd service unit.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="${PROJECT_DIR}/dist"
BUILD_DIR="$(mktemp -d)"
VERSION="$(grep -E '^VERSION\s*=' "${PROJECT_DIR}/config.py" | sed 's/.*= *"\(.*\)".*/\1/')"

cleanup() {
    rm -rf "${BUILD_DIR}"
}
trap cleanup EXIT

mkdir -p "${DIST_DIR}"

echo "[BUILD] Preparing EUNICE Enterprise v${VERSION} VM bundle..."

# Copy source tree excluding dev-only artifacts
rsync -a \
    --exclude='.git' \
    --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='data' \
    --exclude='dist' \
    --exclude='*.log' \
    --exclude='.env' \
    "${PROJECT_DIR}/" "${BUILD_DIR}/eunice-enterprise/"

# Create install script
cat > "${BUILD_DIR}/eunice-enterprise/install.sh" <<'INSTALL'
#!/usr/bin/env bash
set -euo pipefail
INSTALL_DIR="${1:-/opt/eunice-enterprise}"
DATA_DIR="${INSTALL_DIR}/data"
SERVICE_NAME="eunice-enterprise"

echo "[INSTALL] Installing EUNICE Enterprise to ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}"
cp -r "$(dirname "$0")"/* "${INSTALL_DIR}/"
mkdir -p "${DATA_DIR}"

python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

# Create systemd service
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
echo "[INSTALL] Enabled ${SERVICE_NAME}.service. Start with: systemctl start ${SERVICE_NAME}"
INSTALL
chmod +x "${BUILD_DIR}/eunice-enterprise/install.sh"

# Create cloud-init config that fetches and runs the bundle (customize URL)
cat > "${DIST_DIR}/cloud-config.yaml" <<EOF
#cloud-config
package_update: false
runcmd:
  - mkdir -p /opt
  - curl -fsSL "https://YOUR_BUNDLE_HOST/eunice-enterprise-vm-${VERSION}.tar.gz" | tar -xz -C /opt
  - /opt/eunice-enterprise/install.sh
  - systemctl start eunice-enterprise
EOF

# Build tarball
TARBALL="${DIST_DIR}/eunice-enterprise-vm-${VERSION}.tar.gz"
tar -czf "${TARBALL}" -C "${BUILD_DIR}" eunice-enterprise/

# Create a convenience latest symlink
ln -sf "eunice-enterprise-vm-${VERSION}.tar.gz" "${DIST_DIR}/eunice-enterprise-vm-latest.tar.gz"

echo "[BUILD] VM bundle created: ${TARBALL}"
echo "[BUILD] Cloud-init config: ${DIST_DIR}/cloud-config.yaml"
