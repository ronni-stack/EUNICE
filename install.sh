#!/bin/bash
set -e

REPO_URL="https://github.com/ronni-stack/EUNICE.git"
INSTALL_DIR="$HOME/EUNICE_MASTER"

echo "Installing EUNICE to $INSTALL_DIR..."

if [ -d "$INSTALL_DIR" ]; then
    echo "EUNICE already exists at $INSTALL_DIR. Pulling latest..."
    cd "$INSTALL_DIR"
    git pull
else
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Run setup
./eunice.sh setup

echo ""
echo "========================================="
echo "  EUNICE installed!"
echo "  cd $INSTALL_DIR"
echo "  ./eunice.sh launch"
echo "========================================="
