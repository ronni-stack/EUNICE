#!/bin/bash
# EUNICE Backup Script v0.7
BACKUP_DIR="$HOME/eunice_backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$BACKUP_DIR"

echo "Creating backup: eunice_backup_$TIMESTAMP.tar.gz"

tar -czf "$BACKUP_DIR/eunice_backup_$TIMESTAMP.tar.gz" \
    -C "$SOURCE_DIR" \
    data \
    personality.txt \
    config.py \
    main.py \
    client.html \
    sw.js \
    manifest.json \
    core \
    memory \
    api \
    tools \
    scripts \
    tests \
    prompts \
    2>/dev/null

echo "Backup saved to: $BACKUP_DIR/eunice_backup_$TIMESTAMP.tar.gz"
echo "Size: $(du -h $BACKUP_DIR/eunice_backup_$TIMESTAMP.tar.gz | cut -f1)"
echo "To restore: cd ~/EUNICE_MASTER && tar -xzf $BACKUP_DIR/eunice_backup_$TIMESTAMP.tar.gz"
