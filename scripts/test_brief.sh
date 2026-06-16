#!/bin/bash
# Quick Morning Brief Test
# Run this anytime to manually trigger EUNICE's morning briefing

cd "$(dirname "$0")/.."
source venv/bin/activate
python3 scripts/morning_brief.py
