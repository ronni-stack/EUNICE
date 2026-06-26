#!/bin/bash
# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.


# # Quick Morning Brief Test
# Run this anytime to manually trigger EUNICE's morning briefing

cd "$(dirname "$0")/.."
source venv/bin/activate
python3 scripts/morning_brief.py
