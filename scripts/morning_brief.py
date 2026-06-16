#!/usr/bin/env python3
"""
EUNICE Morning Briefing — v0.7 (Trail-Enhanced)
Uses background daemon and trail intelligence for proactive summaries.

Setup:
  crontab -e
  Add: 30 7 * * * cd ~/EUNICE_MASTER && venv/bin/python3 scripts/morning_brief.py >> data/morning_briefs.log 2>&1

Or run manually:
  venv/bin/python3 scripts/morning_brief.py
"""
import asyncio
import os
import httpx
import json
from datetime import datetime
from pathlib import Path

API_URL = "http://localhost:8000"
API_KEY = os.getenv("EUNICE_API_KEY", "eunice-local-dev-key-2026")
BRIEF_LOG = Path(__file__).parent.parent / "data" / "morning_briefs.log"

async def generate_brief():
    """Fetch daemon status and generate a proactive morning briefing."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Get daemon status and alerts
            resp = await client.get(
                f"{API_URL}/daemon/status",
                headers={"Authorization": f"Bearer {API_KEY}"}
            )
            daemon_status = resp.json() if resp.status_code == 200 else {}

            # Get trail overview
            resp2 = await client.get(
                f"{API_URL}/trails",
                headers={"Authorization": f"Bearer {API_KEY}"}
            )
            trails = resp2.json() if resp2.status_code == 200 else {"active": [], "dormant": []}

            # Get daemon alerts
            resp3 = await client.get(
                f"{API_URL}/daemon/alerts",
                headers={"Authorization": f"Bearer {API_KEY}"}
            )
            alerts = resp3.json().get("alerts", []) if resp3.status_code == 200 else []

            # Build brief
            brief_lines = [f"Morning Brief — {timestamp}", "=" * 50]

            # Active topics
            if trails.get("active"):
                brief_lines.append("\n🟢 Active Topics:")
                for t in trails["active"]:
                    brief_lines.append(f"  • {t['name']}")

            # Urgent alerts
            if alerts:
                brief_lines.append("\n🔴 Urgent Alerts:")
                for a in alerts[:3]:
                    brief_lines.append(f"  • {a['trail_name']}: {a['context']}")

            # Dormant trail count
            dormant_count = len(trails.get("dormant", []))
            if dormant_count:
                brief_lines.append(f"\n💤 {dormant_count} dormant trails being monitored")

            # Daemon status
            brief_lines.append(f"\n📊 Daemon: {daemon_status.get('queued_alerts', 0)} alerts queued")

            brief_lines.append("\n" + "=" * 50)
            result = "\n".join(brief_lines)

    except httpx.ConnectError:
        result = f"[{timestamp}] [ERROR: EUNICE server is not running. Start with python main.py]"
    except Exception as e:
        result = f"[{timestamp}] [ERROR: {type(e).__name__}: {e}]"

    # Log to file
    BRIEF_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(BRIEF_LOG, "a", encoding="utf-8") as f:
        f.write(result + "\n\n")

    print(result)

if __name__ == "__main__":
    asyncio.run(generate_brief())
