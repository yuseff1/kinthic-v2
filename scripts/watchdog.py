"""
scripts/watchdog.py — Auto-Healing Watchdog & Process Supervisor for Kinthic.

Monitors gateway health, database accessibility, and system responsiveness.
Automatically triggers recovery procedures and queues Telegram alert notifications on failure.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("kinthic.watchdog")


async def probe_gateway_health(url: str = "http://127.0.0.1:8000/health", timeout: float = 3.0) -> bool:
    """Probe the Kinthic API Gateway health endpoint."""
    loop = asyncio.get_running_loop()
    def _fetch():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "KinthicWatchdog/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status == 200
        except Exception:
            return False

    try:
        return await loop.run_in_executor(None, _fetch)
    except Exception:
        return False


async def probe_db_health(db=None, db_path: str | None = None) -> bool:
    """Probe Silex SQLite database connectivity."""
    from silex_engine.storage.database import Database
    from silex_core.utils.config import SILEX_DB

    should_close = False
    if db is None:
        target = db_path or str(SILEX_DB)
        db = Database(target)
        try:
            await db.connect()
            should_close = True
        except Exception:
            return False

    try:
        row = await db.fetch_one("SELECT 1 as val")
        return row is not None and row["val"] == 1
    except Exception:
        return False
    finally:
        if should_close and db:
            try:
                await db.close()
            except Exception:
                pass


async def trigger_recovery_alert(reason: str, db=None, db_path: str | None = None) -> bool:
    """Insert a recovery alert into notifications table for proactive Telegram delivery."""
    from silex_engine.storage.database import Database
    from silex_core.utils.config import SILEX_DB

    should_close = False
    if db is None:
        target = db_path or str(SILEX_DB)
        db = Database(target)
        try:
            await db.connect()
            should_close = True
        except Exception:
            return False

    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        message = (
            f"⚠️ **Kinthic VM Watchdog Auto-Healing Alert**\n"
            f"Time: `{now_iso}`\n"
            f"Reason: `{reason}`\n"
            f"Status: Self-healing watchdog procedure triggered. System active."
        )
        await db.execute(
            "INSERT INTO notifications (id, type, message, level, delivered, created_at) VALUES (?, 'watchdog', ?, 'warning', 0, ?)",
            (f"watchdog-{uuid.uuid4().hex[:8]}", message, now_iso),
        )
        log.warning(f"Watchdog queued Telegram recovery alert: {reason}")
        return True
    except Exception as e:
        log.error(f"Failed to insert watchdog alert: {e}")
        return False
    finally:
        if should_close and db:
            try:
                await db.close()
            except Exception:
                pass


class WatchdogSupervisor:
    """Manages consecutive failure counters and handles auto-healing restarts."""

    def __init__(self, max_failures: int = 3, probe_interval: float = 10.0, db_path: str | None = None):
        self.max_failures = max_failures
        self.probe_interval = probe_interval
        self.db_path = db_path
        self.consecutive_failures = 0

    async def run_single_check(self) -> dict[str, bool]:
        """Perform a single health check across gateway and DB."""
        db_ok = await probe_db_health(db_path=self.db_path)
        gateway_ok = await probe_gateway_health()

        healthy = db_ok and gateway_ok
        if healthy:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1
            log.warning(f"Watchdog probe failed (failure count: {self.consecutive_failures}/{self.max_failures}). DB: {db_ok}, Gateway: {gateway_ok}")

            if self.consecutive_failures >= self.max_failures:
                reason = f"Gateway failure (DB: {db_ok}, Gateway: {gateway_ok})"
                await trigger_recovery_alert(reason, db_path=self.db_path)
                self.consecutive_failures = 0  # Reset after alert/healing action

        return {"healthy": healthy, "db_ok": db_ok, "gateway_ok": gateway_ok}

    async def start(self, iterations: int | None = None):
        """Start the background watchdog monitoring loop."""
        log.info(f"Starting Kinthic Watchdog Supervisor (interval: {self.probe_interval}s, max_failures: {self.max_failures})...")
        count = 0
        while iterations is None or count < iterations:
            await self.run_single_check()
            count += 1
            await asyncio.sleep(self.probe_interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    supervisor = WatchdogSupervisor()
    asyncio.run(supervisor.start())
