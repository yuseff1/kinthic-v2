from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import signal
import sys
import time
import asyncio
import uuid

from silex_core.utils.logger import setup_logger

log = setup_logger("kinthic.daemon")


def _webhook_url_is_safe(url: str) -> bool:
    """Restrict the watchdog webhook to public http(s) endpoints.

    KINTHIC_WATCHDOG_WEBHOOK is operator-set, not remote-attacker-controlled,
    but it's still a raw URL handed to a fetcher — allowlist the scheme and
    resolve+check the host so a mistyped/malicious value can't be used to
    probe loopback/private/link-local addresses (including cloud metadata
    endpoints at 169.254.169.254, which resolves as link-local) from this
    process.
    """
    import ipaddress
    import socket as _socket
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    try:
        resolved = _socket.getaddrinfo(host, None)
    except Exception:
        return False
    for _family, _type, _proto, _canon, sockaddr in resolved:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def run_gateway_worker() -> None:
    """Entry point for the Omnichannel Gateway (FastAPI server + Adapters)."""
    try:
        import uvicorn
        from silex_core.utils.config import gateway_host, gateway_port

        # We pass the import string so uvicorn can run it
        uvicorn.run(
            "silex_core.api.server:app",
            host=gateway_host(),
            port=gateway_port(),
            log_level="info",
        )
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.error(f"Gateway worker crashed: {e}")
        sys.exit(1)


async def _worker_loop():
    from silex_engine.storage.database import Database
    from silex_core.utils.config import SILEX_DB

    db = Database(str(SILEX_DB))
    await db.connect()

    goal_row = None
    log.info("Cognitive worker spawned. Polling for pending goals...")
    while True:
        goal_row = await db.fetch_one(
            "SELECT * FROM goals WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1"
        )
        if goal_row:
            break
        await asyncio.sleep(5.0)

    log.info(f"Picked up pending goal: {goal_row['id']}")

    # Claim the goal to prevent other instances from grabbing it
    await db.execute(
        "UPDATE goals SET status = 'active' WHERE id = ?", (goal_row["id"],)
    )

    # Initialize Heartbeat table
    await db.execute(
        "CREATE TABLE IF NOT EXISTS heartbeats (process TEXT PRIMARY KEY, last_seen TEXT)"
    )

    # Background Heartbeat Task
    async def heartbeat_loop():
        try:
            while True:
                await db.execute(
                    "INSERT OR REPLACE INTO heartbeats (process, last_seen) VALUES (?, ?)",
                    ("cognitive_worker", str(time.time())),
                )
                await asyncio.sleep(60.0)
        except asyncio.CancelledError:
            pass

    hb_task = asyncio.create_task(heartbeat_loop())

    # Spin up the Heavy Cognitive Brain
    from silex_core.harness.wrapper import LoopWrapper
    loop = LoopWrapper()
    await loop.startup(target_query=goal_row["description"])
    try:
        # Record job run in durable table
        job_run_id = str(uuid.uuid4())[:16]
        await db.execute(
            """INSERT OR IGNORE INTO autonomous_jobs
               (goal_id, run_id, description, status, idempotency_key, created_at, started_at, last_heartbeat)
               VALUES (?, ?, ?, 'running', ?, ?, ?, ?)""",
            (
                goal_row["id"],
                job_run_id,
                goal_row["description"],
                hashlib.sha256(
                    f"{goal_row['id']}:{goal_row['description']}".encode()
                ).hexdigest()[:32],
                time.time(),
                time.time(),
                time.time(),
            ),
        )
        # Record created event
        await db.execute(
            "INSERT OR IGNORE INTO job_events (event_id, goal_id, run_id, kind, payload_json, payload_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                goal_row["id"],
                job_run_id,
                "running",
                json.dumps({"description": goal_row["description"]}),
                "start",
                time.time(),
            ),
        )
        response = await loop.process(
            f"[SYSTEM TASK - EXECUTE GOAL]: {goal_row['description']}"
        )
        output_summary = getattr(response, "response", str(response))[:2000]

        await db.execute(
            "UPDATE autonomous_jobs SET status='completed', completed_at=?, output_summary=? WHERE goal_id=? AND run_id=?",
            (time.time(), output_summary, goal_row["id"], job_run_id),
        )
        await db.execute(
            "INSERT OR IGNORE INTO job_events (event_id, goal_id, run_id, kind, payload_json, payload_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                goal_row["id"],
                job_run_id,
                "completed",
                json.dumps({"output": output_summary[:512]}),
                "done",
                time.time(),
            ),
        )
    except Exception as exc:
        log.error("Goal execution failed: %s", exc)
        try:
            await db.execute(
                "UPDATE autonomous_jobs SET status='failed', completed_at=?, error=? WHERE goal_id=? AND run_id=?",
                (time.time(), str(exc)[:512], goal_row["id"], job_run_id),
            )
        except Exception:
            pass
    finally:
        hb_task.cancel()
        await loop.shutdown()
        await db.close()

    log.info(
        "Task completed. Ephemeral Cognitive Worker is committing seppuku to free RAM."
    )
    sys.exit(0)


def run_cognitive_worker() -> None:
    """Entry point for the Ephemeral Cognitive Worker."""
    try:
        asyncio.run(_worker_loop())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.error(f"Cognitive worker crashed: {e}")
        sys.exit(1)


def run_watcher_worker() -> None:
    """Entry point for the Debounced FS Watcher."""
    try:
        from silex_engine.storage.database import Database
        from silex_core.utils.config import SILEX_DB
        from silex_core.knowledge_graph.watcher import DebouncedWatcher

        async def _run():
            db = Database(str(SILEX_DB))
            await db.connect()
            watcher = DebouncedWatcher(db)
            await watcher.run_loop()

        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    except Exception:
        sys.exit(1)


def run_vault_sync_worker() -> None:
    """Entry point for the Obsidian Vault Sync Worker."""
    try:
        import asyncio
        from silex_engine.storage.database import Database
        from silex_core.utils.config import SILEX_DB, KINTHIC_HOME
        from silex_core.memory.vault_sync import VaultSyncWorker

        async def _run():
            db = Database(str(SILEX_DB))
            await db.connect()
            vault_dir = KINTHIC_HOME / "vault"
            worker = VaultSyncWorker(db, vault_dir)
            await worker.run_loop()

        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.error(f"Vault sync worker crashed: {e}")
        sys.exit(1)


def harvest_zombie_browsers() -> None:
    """Harvest orphaned Playwright Chromium browser processes."""
    import psutil
    import os
    import json
    from pathlib import Path

    # Base set of protected processes: this process and parent process
    protected_pids = {os.getpid(), os.getppid()}

    # Read active process lock if present
    process_lock_path = Path("~/.kinthic/runtime/process.lock").expanduser()
    if process_lock_path.exists():
        try:
            lock_data = json.loads(process_lock_path.read_text(encoding="utf-8"))
            active_pid = lock_data.get("pid")
            if active_pid:
                protected_pids.add(active_pid)
        except Exception:
            pass

    # Scan all active processes
    for proc in psutil.process_iter(["pid", "name", "cmdline", "ppid"]):
        try:
            pid = proc.info["pid"]
            name = proc.info["name"]
            cmdline = proc.info["cmdline"] or []
            ppid = proc.info["ppid"]

            is_chrome = False
            if name:
                low_name = name.lower()
                if "chrome" in low_name or "chromium" in low_name:
                    is_chrome = True

            if not is_chrome:
                continue

            is_playwright = False
            for arg in cmdline:
                if (
                    "playwright" in arg.lower()
                    or "headless" in arg.lower()
                    or "remote-debugging-port" in arg.lower()
                ):
                    is_playwright = True
                    break

            if not is_playwright:
                continue

            # If the process parent is one of the protected active PIDs and alive, skip it
            parent_alive = False
            if ppid and ppid in protected_pids:
                try:
                    parent_proc = psutil.Process(ppid)
                    if parent_proc.is_running():
                        parent_alive = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            if not parent_alive:
                log.warning(
                    f"CronWorker harvesting orphaned Chromium process: PID {pid}, PPID {ppid}"
                )
                try:
                    proc.kill()
                except Exception as e:
                    log.error(f"Failed to kill orphaned Chromium process {pid}: {e}")
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue


def run_cron_worker() -> None:
    """Entry point for the Background Cron Worker (Issues 11 and 14)."""
    try:
        import asyncio
        from silex_engine.storage.database import Database
        from silex_core.utils.config import SILEX_DB

        async def _run():
            db = Database(str(SILEX_DB))
            await db.connect()

            last_daily = 0.0
            last_memory_decay = 0.0
            last_vector_reconcile = 0.0
            VECTOR_RECONCILE_INTERVAL = 6 * 3600  # every 6 hours

            while True:
                now = time.time()

                # ── Periodic SQLite<->ChromaDB integrity reconciliation ─
                if now - last_vector_reconcile >= VECTOR_RECONCILE_INTERVAL:
                    try:
                        from silex_engine.memory.memory_store import MemoryStore

                        mem_store = MemoryStore(db)
                        reindexed = await mem_store.reconcile_vector_index()
                        retried_deletes = await mem_store.retry_pending_vector_deletes()
                        if reindexed:
                            log.info(
                                "Cron worker: vector integrity reconciliation re-indexed %d memories.",
                                reindexed,
                            )
                        if retried_deletes:
                            log.info(
                                "Cron worker: cleared %d pending vector-store delete(s).",
                                retried_deletes,
                            )
                        last_vector_reconcile = now
                    except Exception as e:
                        log.error(f"Cron worker vector reconciliation error: {e}")

                # ── Daily maintenance pass ──────────────────────────────
                if now - last_daily >= 86400:
                    try:
                        # Issue 11: Graph Pruning
                        await db.execute(
                            "DELETE FROM knowledge_nodes "
                            "WHERE last_validated < datetime('now', '-30 days') AND confidence < 0.5"
                        )
                        # Issue 14: Job Queue TTL
                        await db.execute(
                            "DELETE FROM goals WHERE status IN ('completed', 'failed') "
                            "AND updated_at < datetime('now', '-7 days')"
                        )
                        log.info(
                            "Cron worker: graph pruning and job TTL pass complete."
                        )
                        last_daily = now
                    except Exception as e:
                        log.error(f"Cron worker daily consolidation error: {e}")

                # ── Daily memory decay + archival ───────────────────────
                if now - last_memory_decay >= 86400:
                    try:
                        from silex_core.utils.config import MEMORY_ARCHIVE_THRESHOLD

                        # Decay importance of memories untouched for 7+ days
                        await db.execute(
                            "UPDATE memories "
                            "SET importance = importance * 0.95 "
                            "WHERE (julianday('now') - julianday(last_accessed)) > 7 "
                            "  AND archived_at IS NULL"
                        )
                        # Archive memories whose importance has dropped below threshold
                        await db.execute(
                            "UPDATE memories SET archived_at = datetime('now') "
                            "WHERE importance < ? AND archived_at IS NULL",
                            (MEMORY_ARCHIVE_THRESHOLD,),
                        )
                        log.info(
                            "Cron worker: memory decay + archival pass complete "
                            "(threshold=%.2f).",
                            MEMORY_ARCHIVE_THRESHOLD,
                        )
                        try:
                            from silex_core.core.causal_graph import (
                                CausalKnowledgeGraphGenerator,
                            )

                            causal_kg = CausalKnowledgeGraphGenerator(db)
                            archived = await causal_kg.archive_old_nodes()
                            if archived:
                                log.info(
                                    "Cron worker: archived %d stale epistemic nodes.",
                                    archived,
                                )
                        except Exception as archive_exc:
                            log.error(
                                f"Cron worker epistemic archival error: {archive_exc}"
                            )
                        last_memory_decay = now
                    except Exception as e:
                        log.error(f"Cron worker memory decay error: {e}")

                # ── Hourly browser harvesting ───────────────────────────
                try:
                    harvest_zombie_browsers()
                except Exception as e:
                    log.error(f"Cron worker browser harvesting error: {e}")

                # Sleep for 1 hour (3600 seconds)
                await asyncio.sleep(3600)

        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.error(f"Cron worker crashed: {e}")
        sys.exit(1)


class DaemonWatchdog:
    """The multi-process supervisor."""

    # Heartbeat check is throttled to once every 60s to avoid
    # thousands of unnecessary DB open/close cycles per day.
    HEARTBEAT_CHECK_INTERVAL = 60.0
    LOG_ROTATE_INTERVAL = 3600.0
    LOG_ROTATE_MAX_BYTES = 10 * 1024 * 1024
    MAX_CONSECUTIVE_FAILURES = 5
    BACKOFF_SECONDS = (2, 5, 15, 60)

    def __init__(self):
        self.gateway_process: multiprocessing.Process | None = None
        self.cognitive_process: multiprocessing.Process | None = None
        self.watcher_process: multiprocessing.Process | None = None
        self.cron_process: multiprocessing.Process | None = None
        self.vault_sync_process: multiprocessing.Process | None = None
        self.running = False
        self._last_heartbeat_check: float = 0.0  # epoch seconds
        self._last_log_rotate: float = 0.0
        self._worker_state: dict[str, dict] = {}

    def _worker_state_for(self, name: str) -> dict:
        return self._worker_state.setdefault(
            name,
            {
                "consecutive_failures": 0,
                "next_restart_at": 0.0,
                "started_at": 0.0,
                "disabled": False,
            },
        )

    def _rotate_daemon_log_if_needed(self) -> None:
        from silex_core.utils.config import KINTHIC_DAEMON_LOG

        if not KINTHIC_DAEMON_LOG.exists():
            return
        if KINTHIC_DAEMON_LOG.stat().st_size <= self.LOG_ROTATE_MAX_BYTES:
            return
        for i in range(2, 0, -1):
            old = KINTHIC_DAEMON_LOG.with_name(f"daemon.log.{i}")
            new = KINTHIC_DAEMON_LOG.with_name(f"daemon.log.{i + 1}")
            if old.exists():
                try:
                    old.replace(new)
                except OSError:
                    pass
        try:
            KINTHIC_DAEMON_LOG.replace(KINTHIC_DAEMON_LOG.with_name("daemon.log.1"))
        except OSError:
            pass

    def _maybe_restart_worker(
        self,
        name: str,
        process: multiprocessing.Process | None,
        target,
        *,
        normal_exit_codes: tuple[int | None, ...] = (0, None),
    ) -> multiprocessing.Process | None:
        """Restart a dead worker with backoff; disable after repeated crashes."""
        if process is None or process.is_alive():
            return process

        state = self._worker_state_for(name)
        if state["disabled"]:
            return process

        exit_code = process.exitcode
        now = time.time()

        if exit_code in normal_exit_codes:
            state["consecutive_failures"] = 0
            state["next_restart_at"] = 0.0
            log.info("%s exited normally (code=%s); restarting.", name, exit_code)
            return self.start_process(target, name)

        # Waiting for backoff window before restart attempt.
        if state["next_restart_at"] and now < state["next_restart_at"]:
            return process

        # Backoff elapsed (or first scheduling pass) — restart now.
        if state["next_restart_at"] and now >= state["next_restart_at"]:
            state["next_restart_at"] = 0.0
            new_proc = self.start_process(target, name)
            state["started_at"] = time.time()
            return new_proc

        # First observation of a crash — schedule backoff and alert once.
        state["consecutive_failures"] += 1
        backoff_idx = min(
            state["consecutive_failures"] - 1, len(self.BACKOFF_SECONDS) - 1
        )
        delay = self.BACKOFF_SECONDS[backoff_idx]
        state["next_restart_at"] = now + delay

        if state["consecutive_failures"] >= self.MAX_CONSECUTIVE_FAILURES:
            state["disabled"] = True
            msg = (
                f"⚠️ [FATAL] {name} crashed {state['consecutive_failures']} times in a row "
                f"(last exit code {exit_code}). Watchdog will not restart it until daemon reload."
            )
            log.critical(msg)
            self._send_webhook(msg)
            return process

        msg = (
            f"⚠️ [CRITICAL] {name} died with exit code {exit_code}! "
            f"Restart in {delay}s (failure {state['consecutive_failures']}/{self.MAX_CONSECUTIVE_FAILURES})."
        )
        log.warning(msg)
        self._send_webhook(msg)
        return process

    def _track_worker_uptime_resets(self) -> None:
        """Reset failure counters after a worker has stayed up for 30s."""
        now = time.time()
        for name, proc in (
            ("GatewayWorker", self.gateway_process),
            ("CognitiveWorker", self.cognitive_process),
            ("WatcherWorker", self.watcher_process),
            ("CronWorker", self.cron_process),
            ("VaultSyncWorker", self.vault_sync_process),
        ):
            state = self._worker_state_for(name)
            if proc and proc.is_alive() and state["started_at"]:
                if now - state["started_at"] >= 30.0:
                    state["consecutive_failures"] = 0
                    state["next_restart_at"] = 0.0
                    state["started_at"] = 0.0

    def _send_webhook(self, message: str) -> None:
        webhook_url = os.environ.get("KINTHIC_WATCHDOG_WEBHOOK")
        if not webhook_url:
            return

        import urllib.request
        import json

        if not _webhook_url_is_safe(webhook_url):
            log.error(
                "KINTHIC_WATCHDOG_WEBHOOK is set to an unsafe target (must be a public "
                "http(s) URL, not a loopback/private/link-local address) — refusing to send."
            )
            return

        log.info(f"Sending out-of-band webhook alert: {message}")
        payload = {
            "text": message,
            "message": message,
            "timestamp": time.time(),
        }

        try:
            req = urllib.request.Request(
                webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            # Short timeout to avoid blocking the watchdog loop
            with urllib.request.urlopen(req, timeout=5.0) as response:
                response.read()
        except Exception as e:
            log.error(f"Failed to send out-of-band webhook: {e}")

    def start_process(self, target, name: str) -> multiprocessing.Process:
        log.info(f"Watchdog starting {name}...")
        p = multiprocessing.Process(target=target, name=name, daemon=True)
        p.start()
        self._worker_state_for(name)["started_at"] = time.time()
        return p

    def _recover_stale_jobs(self) -> None:
        """Resets active jobs back to pending to recover from an unclean shutdown."""
        import asyncio
        from silex_engine.storage.database import Database
        from silex_core.utils.config import SILEX_DB

        async def _run():
            db = Database(str(SILEX_DB))
            await db.connect()
            stale_jobs = await db.fetch_all(
                "SELECT id, description FROM goals WHERE status = 'active'"
            )
            for job in stale_jobs:
                log.warning(
                    f"Recovered stale active job after unclean shutdown: {job['id']}"
                )
                await db.execute(
                    "UPDATE goals SET status = 'pending', completion_notes = 'Recovered after unclean shutdown' WHERE id = ?",
                    (job["id"],),
                )
            if stale_jobs:
                log.info(
                    f"Successfully recovered {len(stale_jobs)} orphaned jobs to pending queue."
                )
            await db.close()

        try:
            asyncio.run(_run())
        except Exception as e:
            log.error(f"Failed to run recovery cleanup: {e}")

    def _check_heartbeats(self) -> None:
        """Issue 6: Checks if the Cognitive Worker has frozen for > 3 hours."""
        import asyncio
        from silex_engine.storage.database import Database
        from silex_core.utils.config import SILEX_DB

        async def _run():
            db = Database(str(SILEX_DB))
            await db.connect()
            await db.execute(
                "CREATE TABLE IF NOT EXISTS heartbeats (process TEXT PRIMARY KEY, last_seen TEXT)"
            )
            hb_row = await db.fetch_one(
                "SELECT last_seen FROM heartbeats WHERE process = 'cognitive_worker'"
            )
            if hb_row:
                last_seen = float(hb_row["last_seen"])
                if time.time() - last_seen > 3 * 3600:  # 3 hours
                    if self.cognitive_process and self.cognitive_process.is_alive():
                        msg = "⚠️ [ALERT] Kinthic cognitive worker was frozen for >3 hours and has been force-restarted."
                        log.error(msg)
                        self._send_webhook(msg)
                        self.cognitive_process.kill()
                        # Write alert so the Telegram bot can notify the user
                        import uuid
                        from datetime import datetime, timezone

                        await db.execute(
                            "INSERT INTO notifications (id, message, level, delivered, created_at) VALUES (?, ?, ?, 0, ?)",
                            (
                                str(uuid.uuid4()),
                                msg,
                                "alert",
                                datetime.now(timezone.utc).isoformat(),
                            ),
                        )
                        # db.execute() auto-commits — no explicit commit needed.
            await db.close()

        try:
            asyncio.run(_run())
        except Exception:
            pass

    def run(self) -> None:
        self.running = True

        # Handle SIGTERM for graceful shutdown
        def handle_sigterm(*args):
            log.info("Watchdog received SIGTERM. Shutting down...")
            self.running = False

        signal.signal(signal.SIGINT, handle_sigterm)
        signal.signal(signal.SIGTERM, handle_sigterm)

        log.info("--- Kinthic Watchdog Started ---")

        # Issue 2: Recover orphaned jobs before workers can grab them
        self._recover_stale_jobs()

        # Start Omnichannel Gateway
        self.gateway_process = self.start_process(run_gateway_worker, "GatewayWorker")

        self.cognitive_process = self.start_process(
            run_cognitive_worker, "CognitiveWorker"
        )
        self.watcher_process = self.start_process(run_watcher_worker, "WatcherWorker")
        self.cron_process = self.start_process(run_cron_worker, "CronWorker")
        self.vault_sync_process = self.start_process(run_vault_sync_worker, "VaultSyncWorker")

        # The Watchdog Loop
        while self.running:
            try:
                now = time.time()
                if now - self._last_log_rotate >= self.LOG_ROTATE_INTERVAL:
                    self._last_log_rotate = now
                    self._rotate_daemon_log_if_needed()

                self.gateway_process = self._maybe_restart_worker(
                    "GatewayWorker", self.gateway_process, run_gateway_worker
                )
                self.cognitive_process = self._maybe_restart_worker(
                    "CognitiveWorker",
                    self.cognitive_process,
                    run_cognitive_worker,
                    normal_exit_codes=(0, None),
                )
                self.watcher_process = self._maybe_restart_worker(
                    "WatcherWorker", self.watcher_process, run_watcher_worker
                )
                self.cron_process = self._maybe_restart_worker(
                    "CronWorker", self.cron_process, run_cron_worker
                )
                self.vault_sync_process = self._maybe_restart_worker(
                    "VaultSyncWorker", self.vault_sync_process, run_vault_sync_worker
                )

                self._track_worker_uptime_resets()

                if self.cognitive_process and self.cognitive_process.is_alive():
                    if (
                        now - self._last_heartbeat_check
                        >= self.HEARTBEAT_CHECK_INTERVAL
                    ):
                        self._last_heartbeat_check = now
                        self._check_heartbeats()

                time.sleep(2.0)  # Gentle polling
            except Exception as e:
                log.error(f"Watchdog error: {e}")
                time.sleep(5.0)

        # Shutdown sequence
        log.info("Terminating all child processes gracefully...")
        processes = [
            p
            for p in (
                self.gateway_process,
                self.cognitive_process,
                self.watcher_process,
                self.cron_process,
                self.vault_sync_process,
            )
            if p
        ]

        for p in processes:
            if p.is_alive():
                # Send SIGTERM for graceful exit
                os.kill(p.pid, signal.SIGTERM)

        # Wait up to 10 seconds for them to shut down cleanly
        timeout = 10
        start_wait = time.time()
        while time.time() - start_wait < timeout:
            if all(not p.is_alive() for p in processes):
                break
            time.sleep(0.5)

        # Hard kill any survivors
        for p in processes:
            if p.is_alive():
                log.warning(
                    f"Process {p.name} (PID {p.pid}) did not shut down in time. Sending SIGKILL."
                )
                try:
                    p.kill()  # Python 3.7+ equivalent of SIGKILL
                except Exception:
                    pass
        log.info("Watchdog shutdown complete.")


def main() -> None:
    import silex_core.utils.config  # noqa: F401 — loads ~/.kinthic/.env before adapter env checks

    watchdog = DaemonWatchdog()
    watchdog.run()


if __name__ == "__main__":
    main()
