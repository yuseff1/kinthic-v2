import uuid
from datetime import datetime, timezone
from silex_engine.storage.database import Database
from silex_core.utils.logger import setup_logger

log = setup_logger("silex.adapters.approval_notifier")


async def notify_approval_required(
    db: Database, approval_id: str, tool_name: str, risk_level: str, reason: str
) -> None:
    """
    Inserts a row into the notifications table to push an approval request
    to the paired Telegram user(s).
    """
    if not db:
        return

    prefix = approval_id.split("-")[0]

    # Message template matching the design spec
    message = (
        f"⚠️ **Approval Required**\n\n"
        f"**Tool:** `{tool_name}`\n"
        f"**Risk:** {risk_level}\n"
        f"**ID:** `{prefix}`\n\n"
        f"{reason}\n\n"
        f"Type `/approve {prefix}` or `/reject {prefix}`"
    )

    try:
        await db.execute(
            """
            INSERT INTO notifications (id, type, message, delivered, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                "approval_request",
                message,
                0,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        log.info(f"Queued approval notification for {tool_name} ({prefix})")
    except Exception as e:
        log.error(f"Failed to queue approval notification: {e}")
