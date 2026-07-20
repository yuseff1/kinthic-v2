import asyncio
import contextvars
import logging
import sys
from typing import Coroutine, Any, Optional

log = logging.getLogger(__name__)


def _clear_db_transaction_context():
    """Clear database transaction context variables to prevent background tasks from joining parent transactions."""
    if "silex_engine.storage.database" in sys.modules:
        db_module = sys.modules["silex_engine.storage.database"]
        if hasattr(db_module, "active_transaction_conn_var"):
            db_module.active_transaction_conn_var.set(None)
        if hasattr(db_module, "transaction_depth_var"):
            db_module.transaction_depth_var.set(0)


def safe_create_task(coro: Coroutine, name: str, clear_db_context: bool = True) -> asyncio.Task:
    """
    Spawns an asyncio task with a done callback to catch and log unhandled exceptions.
    Optionally clears database transaction ContextVars to ensure task isolation.
    """
    ctx = contextvars.copy_context()

    def run_in_context():
        if clear_db_context:
            _clear_db_transaction_context()
        return coro

    # Python 3.11+ asyncio.create_task supports context= argument
    task = asyncio.create_task(ctx.run(run_in_context), name=name)

    def exception_handler(t: asyncio.Task):
        try:
            if not t.cancelled():
                if exc := t.exception():
                    log.critical(f"Fatal unhandled exception in background task '{t.get_name()}': {exc}", exc_info=exc)
        except Exception as e:
            log.error(f"Failed to extract exception from task '{t.get_name()}': {e}", exc_info=e)

    task.add_done_callback(exception_handler)
    return task
