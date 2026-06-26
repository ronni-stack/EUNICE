# EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0. See LICENSE for details.

"""EUNICE Background Daemon — Proactive Trail Monitor (multi-user)
Runs continuously, checks dormant trails, queues reactivations.
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from memory.trail_manager import TrailManager
from core.inference import generate_non_stream

DEFAULT_USER_ID = "ronny"

class BackgroundDaemon:
    """Monitors dormant trails and surfaces relevant context proactively."""

    def __init__(self, check_interval: int = 900):
        self.trails = TrailManager()
        self.check_interval = check_interval  # 15 minutes default
        self.reactivation_queue = []
        self.running = False

    async def start(self):
        """Start the background loop."""
        self.running = True
        print("[DAEMON] Background trail monitor started")
        while self.running:
            await self.check_all_trails()
            await asyncio.sleep(self.check_interval)

    def stop(self):
        """Stop the daemon."""
        self.running = False

    async def check_all_trails(self):
        """Scan all dormant trails for reactivation triggers."""
        # In multi-user mode we would iterate users; for now, monitor default user
        dormant = self.trails.get_dormant_trails(user_id=DEFAULT_USER_ID)
        new_alerts = []

        for trail in dormant:
            trigger = self._evaluate_trail(trail)
            if trigger:
                new_alerts.append({
                    'trail_id': trail['id'],
                    'trail_name': trail['name'],
                    'trigger_type': trigger['type'],
                    'context': trigger['context'],
                    'priority': trigger['priority'],
                    'suggested_message': trigger['message'],
                    'detected_at': datetime.now().isoformat()
                })

        # Merge with existing queue, deduplicate by trail_id
        existing_ids = {a['trail_id'] for a in self.reactivation_queue}
        for alert in new_alerts:
            if alert['trail_id'] not in existing_ids:
                self.reactivation_queue.append(alert)

        # Sort by priority (highest first)
        self.reactivation_queue.sort(key=lambda x: x['priority'], reverse=True)

        if new_alerts:
            print(f"[DAEMON] {len(new_alerts)} new alerts queued")

    def _evaluate_trail(self, trail: Dict) -> Optional[Dict]:
        """Evaluate a single dormant trail for reactivation."""
        trail_id = trail['id']
        trail_name = trail.get('name', 'Unknown')

        # 1. Time deadline check (highest priority)
        if trail.get('deadline'):
            try:
                deadline = datetime.fromisoformat(trail['deadline'].replace('Z', '+00:00'))
                now = datetime.now()
                days_until = (deadline - now).days

                if days_until <= 1:
                    return {
                        'type': 'urgent_deadline',
                        'context': f"Due tomorrow ({trail['deadline']})",
                        'priority': 1.0,
                        'message': f"'{trail_name}' is due tomorrow!"
                    }
                elif days_until <= 3:
                    return {
                        'type': 'approaching_deadline',
                        'context': f"Due in {days_until} days",
                        'priority': 0.8,
                        'message': f"'{trail_name}' deadline approaching ({days_until} days)."
                    }
                elif days_until <= 7:
                    return {
                        'type': 'deadline_warning',
                        'context': f"Due in {days_until} days",
                        'priority': 0.5,
                        'message': f"'{trail_name}' is due in {days_until} days."
                    }
            except (ValueError, TypeError):
                pass

        # 2. Long dormancy check (trail not touched in 30 days)
        if trail.get('last_accessed'):
            try:
                last_access = datetime.fromisoformat(trail['last_accessed'].replace('Z', '+00:00'))
                days_inactive = (datetime.now() - last_access).days
                if days_inactive > 30:
                    return {
                        'type': 'dormancy_reminder',
                        'context': f"Inactive for {days_inactive} days",
                        'priority': 0.3,
                        'message': f"You haven't discussed '{trail_name}' in {days_inactive} days."
                    }
            except (ValueError, TypeError):
                pass

        # 3. Pattern-based (if trail name suggests recurring topic)
        # Simplified: check if trail name suggests recurring topic
        recurring_keywords = ['gym', 'workout', 'medication', 'call', 'meeting', 'report']
        if any(k in trail_name.lower() for k in recurring_keywords):
            return {
                'type': 'pattern_reminder',
                'context': "Recurring activity",
                'priority': 0.4,
                'message': f"Don't forget your '{trail_name}' routine."
            }

        return None

    def get_urgent_alerts(self, n: int = 3) -> List[Dict]:
        """Get top N urgent alerts from the queue."""
        return self.reactivation_queue[:n]

    def get_all_alerts(self) -> List[Dict]:
        """Get all queued alerts."""
        return self.reactivation_queue.copy()

    def clear_alert(self, trail_id: str):
        """Remove a specific alert from the queue."""
        self.reactivation_queue = [a for a in self.reactivation_queue if a['trail_id'] != trail_id]

    def clear_all_alerts(self):
        """Clear the entire queue."""
        self.reactivation_queue = []

    def generate_morning_brief(self, user_name: str = "there") -> str:
        """Generate a proactive morning brief using trail intelligence."""
        parts = []

        # Active trails
        active = self.trails.get_active_trails(user_id=DEFAULT_USER_ID)
        if active:
            parts.append("🟢 Active topics:")
            for t in active:
                parts.append(f"  • {t.get('name', 'Unknown')}")

        # Urgent alerts
        urgent = self.get_urgent_alerts(5)
        if urgent:
            parts.append("\n🔴 Needs attention:")
            for u in urgent:
                parts.append(f"  • {u['trail_name']}: {u['context']}")

        # Cross-trail conflicts
        conflicts = self.trails.find_cross_trail_conflicts(user_id=DEFAULT_USER_ID)
        if conflicts:
            parts.append("\n⚠️ Conflicts:")
            for c in conflicts:
                parts.append(f"  • {c['trail_a']} and {c['trail_b']} both on {c['deadline'][:10]}")

        # Dormant trail count
        dormant = self.trails.get_dormant_trails(user_id=DEFAULT_USER_ID)
        if dormant:
            parts.append(f"\n💤 {len(dormant)} dormant trails being monitored")

        greeting_name = user_name if user_name else "there"
        if not parts:
            return f"Good morning, {greeting_name}. No urgent items. All trails are calm."

        return f"Good morning, {greeting_name}.\n" + "\n".join(parts)

    def generate_proactive_nudge(self, user_msg: str, user_id: str = DEFAULT_USER_ID) -> Optional[str]:
        """Generate a contextual nudge based on current conversation + dormant trails."""
        # Check if any dormant trail is relevant to current message
        entities = self.trails._extract_entities(user_msg)

        for entity in entities:
            related = self.trails.find_related_trails(entity, user_id=user_id)
            for trail in related:
                if trail.get('status') == 'dormant':
                    # Check if this trail has an alert
                    alert = next((a for a in self.reactivation_queue if a['trail_id'] == trail['id']), None)
                    if alert:
                        return f"By the way — {alert['message']}"

        return None

    def set_trail_deadline(self, trail_id: str, deadline: str):
        """Set or update a trail deadline."""
        self.trails.store.update_trail_deadline(trail_id, deadline)

    def get_daemon_status(self) -> Dict:
        """Get current daemon status for health checks."""
        return {
            'running': self.running,
            'check_interval': self.check_interval,
            'queued_alerts': len(self.reactivation_queue),
            'active_trails': len(self.trails.get_active_trails(user_id=DEFAULT_USER_ID)),
            'dormant_trails': len(self.trails.get_dormant_trails(user_id=DEFAULT_USER_ID)),
            'next_check': (datetime.now() + timedelta(seconds=self.check_interval)).isoformat()
        }
