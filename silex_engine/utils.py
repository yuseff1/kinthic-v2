import asyncio
from contextvars import ContextVar
import traceback
from silex_engine.logger import setup_logger

log = setup_logger("silex.engine.utils")
mcp_http_write_ctx = ContextVar('mcp_http_write_ctx', default=False)

def safe_create_task(coro, name=None):
    task = asyncio.create_task(coro, name=name)
    def handle_exception(t):
        try:
            t.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            log.error(f"Task {name or t.get_name()} failed with exception:\n{traceback.format_exc()}")
    task.add_done_callback(handle_exception)
    return task
