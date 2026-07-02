#!/bin/bash
set -e

REPO_URL="https://github.com/ronni-stack/EUNICE.git"
BRANCH="eunice-enterprise"
INSTALL_DIR="$HOME/EUNICE_MASTER"

echo "Installing EUNICE Enterprise to $INSTALL_DIR..."

if [ -d "$INSTALL_DIR" ]; then
    echo "EUNICE already exists at $INSTALL_DIR. Pulling latest $BRANCH..."
    cd "$INSTALL_DIR"
    git fetch origin
    git checkout "$BRANCH"
    git pull origin "$BRANCH"
else
    git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Create a starter .env if none exists
if [ ! -f ".env" ]; then
    cat > .env <<'EOF'
# EUNICE Enterprise — required secrets (change before production!)
EUNICE_MASTER_KEY="replace-with-a-long-random-string"
EUNICE_API_KEY="replace-with-a-random-api-key"
EUNICE_JWT_SECRET="replace-with-a-random-jwt-secret"

# Inference
EUNICE_OLLAMA_URL=http://localhost:11434
EUNICE_MODEL=llama3.2:3b

# CORS (production)
# EUNICE_ALLOWED_ORIGINS=https://chat.company.com
EOF
    echo ""
    echo "Created starter .env file. EDIT IT and set real secrets before launching."
fi

# Run setup
./eunice.sh setup

echo ""
echo "========================================="
echo "  EUNICE Enterprise installed!"
echo "  cd $INSTALL_DIR"
echo "  ./eunice.sh launch"
echo "========================================="
