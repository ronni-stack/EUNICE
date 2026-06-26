#!/usr/bin/env python3
# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""
EUNICE Tool: Get Balance (HIGH RISK)
Retrieves account balance from configured bank API or local ledger.

Usage:
  python tools/get_balance.py
  # Or via EUNICE: "what's my balance"

Requirements:
  - Bank API credentials in environment or local config
  - Or manual ledger at data/banking.json
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(os.environ.get("EUNICE_DATA_DIR", "/tmp"))
BANKING_PATH = DATA_DIR / "banking.json"

def get_balance(account_id: str = "default"):
    """Retrieve balance from local ledger or mock for demo."""

    # Check for real banking config
    bank_api_key = os.environ.get("BANK_API_KEY")
    bank_api_url = os.environ.get("BANK_API_URL")

    if bank_api_key and bank_api_url:
        # Real bank integration would go here
        # For now, return mock with disclaimer
        return {
            "account": account_id,
            "balance": "[REAL BANK INTEGRATION PENDING]",
            "currency": "USD",
            "timestamp": datetime.now().isoformat(),
            "note": "Set BANK_API_KEY and BANK_API_URL for live data"
        }

    # Fallback to local ledger
    if BANKING_PATH.exists():
        with open(BANKING_PATH, "r") as f:
            ledger = json.load(f)
        account = ledger.get(account_id, {})
        return {
            "account": account_id,
            "balance": account.get("balance", 0.0),
            "currency": account.get("currency", "USD"),
            "last_updated": account.get("last_updated", "never"),
            "timestamp": datetime.now().isoformat()
        }

    # No ledger exists — create demo
    demo_ledger = {
        "default": {
            "balance": 10000.00,
            "currency": "USD",
            "last_updated": datetime.now().isoformat()
        }
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(BANKING_PATH, "w") as f:
        json.dump(demo_ledger, f, indent=2)

    return {
        "account": account_id,
        "balance": 10000.00,
        "currency": "USD",
        "note": "Demo ledger created. Edit data/banking.json for real data.",
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    try:
        params = json.load(sys.stdin) if sys.stdin else {}
    except json.JSONDecodeError:
        params = {}

    account_id = params.get("account_id", "default")
    result = get_balance(account_id)
    print(json.dumps(result, indent=2))
