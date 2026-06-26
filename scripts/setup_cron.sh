#!/bin/bash
# EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.


# # EUNICE Cron Setup — Morning Brief
# Run this once to install the morning briefing schedule

echo "Setting up EUNICE morning brief cron job..."

# Check if already exists
if crontab -l 2>/dev/null | grep -q "morning_brief.py"; then
    echo "Morning brief cron job already exists."
    echo "Current crontab entry:"
    crontab -l | grep "morning_brief"
    echo ""
    read -p "Replace it? (y/n): " replace
    if [[ "$replace" != "y" ]]; then
        echo "Cancelled."
        exit 0
    fi
fi

# Get the absolute path
EUNICE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BRIEF_SCRIPT="$EUNICE_DIR/scripts/morning_brief.py"
LOG_FILE="$EUNICE_DIR/data/morning_briefs.log"

# Default time: 7:30 AM
read -p "What time for morning brief? (default: 7:30 AM, format HH:MM): " user_time
TIME="${user_time:-07:30}"

# Parse time
HOUR=$(echo "$TIME" | cut -d: -f1)
MIN=$(echo "$TIME" | cut -d: -f2)

# Validate
if ! [[ "$HOUR" =~ ^[0-9]+$ ]] || ! [[ "$MIN" =~ ^[0-9]+$ ]]; then
    echo "Invalid time format. Using default 07:30."
    HOUR=7
    MIN=30
fi

# Build cron line
CRON_LINE="$MIN $HOUR * * * cd $EUNICE_DIR && $EUNICE_DIR/venv/bin/python3 $BRIEF_SCRIPT >> $LOG_FILE 2>&1"

# Install
(crontab -l 2>/dev/null || true; echo "$CRON_LINE") | crontab -

echo ""
echo "✅ Morning brief scheduled for $HOUR:$MIN daily"
echo "   Script: $BRIEF_SCRIPT"
echo "   Log:    $LOG_FILE"
echo ""
echo "To verify: crontab -l"
echo "To test now: $EUNICE_DIR/venv/bin/python3 $BRIEF_SCRIPT"
