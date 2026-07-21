"""
silex_core/services/briefing.py — Proactive Daily Briefings & Intelligence Summary Service.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("silex.services.briefing")


class BriefingService:
    """Generates comprehensive daily briefings for Kinthic operators."""

    def __init__(self, db: Any = None):
        self.db = db

    async def generate_briefing(self) -> str:
        """Generate a complete Markdown Daily Briefing report."""
        from silex_engine.storage.database import Database
        from silex_core.utils.config import SILEX_DB

        db = self.db
        should_close = False
        if db is None:
            db = Database(str(SILEX_DB))
            await db.connect()
            should_close = True

        try:
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

            # 1. System & Memory Stats
            mem_row = await db.fetch_one("SELECT COUNT(*) as cnt FROM memories WHERE archived_at IS NULL")
            mem_count = mem_row["cnt"] if mem_row else 0

            node_row = await db.fetch_one("SELECT COUNT(*) as cnt FROM knowledge_nodes")
            node_count = node_row["cnt"] if node_row else 0

            edge_row = await db.fetch_one("SELECT COUNT(*) as cnt FROM causal_edges")
            edge_count = edge_row["cnt"] if edge_row else 0

            # 2. Goals & Jobs Status
            active_goals = await db.fetch_all("SELECT description, priority FROM goals WHERE status = 'active' LIMIT 5")
            pending_jobs = await db.fetch_all("SELECT goal_id, status FROM autonomous_jobs WHERE status IN ('pending', 'running') LIMIT 5")

            # 3. Usage & Cost Metrics
            usage_row = await db.fetch_one(
                "SELECT COUNT(*) as reqs, SUM(input_tokens) as in_tok, SUM(output_tokens) as out_tok, SUM(estimated_cost_usd) as cost FROM llm_usage"
            )
            cost = usage_row["cost"] if usage_row and usage_row["cost"] is not None else 0.0
            reqs = usage_row["reqs"] if usage_row and usage_row["reqs"] is not None else 0

            # 4. Format Report
            lines = [
                f"🌅 **Kinthic Daily Briefing — {now_str}**",
                "---",
                "🧠 **Memory & Knowledge Engine:**",
                f"• Active Memories: `{mem_count}`",
                f"• Knowledge Graph: `{node_count}` nodes, `{edge_count}` causal edges",
                "",
                "🎯 **Active Goals & Autonomous Jobs:**",
            ]

            if active_goals:
                for g in active_goals:
                    lines.append(f"• Goal: {g['description']} (Priority: {g['priority']})")
            else:
                lines.append("• No active goals queued.")

            if pending_jobs:
                for j in pending_jobs:
                    lines.append(f"• Job: Goal `{j['goal_id'][:8]}` — Status: `{j['status']}`")

            lines.extend([
                "",
                "📊 **System Usage & Telemetry:**",
                f"• LLM Requests: `{reqs}`",
                f"• Total Estimated Cost: `${cost:.4f}`",
                "",
                "📱 **Social Media & X Engagement:**",
                "• Status: Active (X Social Suite plugin loaded)",
                "• Auto-engagement scheduler ready.",
                "---",
                "_Type `/status` or `/remember <query>` in Telegram for live queries._"
            ])

            report = "\n".join(lines)
            return report
        finally:
            if should_close and db:
                await db.close()

    async def queue_briefing_notification(self) -> str:
        """Generate briefing and insert into notifications table for proactive Telegram delivery."""
        report = await self.generate_briefing()
        from silex_engine.storage.database import Database
        from silex_core.utils.config import SILEX_DB

        db = self.db
        should_close = False
        if db is None:
            db = Database(str(SILEX_DB))
            await db.connect()
            should_close = True

        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            await db.execute(
                "INSERT INTO notifications (id, type, message, level, delivered, created_at) VALUES (?, 'briefing', ?, 'info', 0, ?)",
                (f"briefing-{uuid.uuid4().hex[:8]}", report, now_iso),
            )
            log.info("Queued proactive daily briefing into notifications table.")
            return report
        finally:
            if should_close and db:
                await db.close()
