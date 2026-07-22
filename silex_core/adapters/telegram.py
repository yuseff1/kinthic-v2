"""Telegram messaging adapter for Kinthic."""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

from silex_core.adapters.base import MessageAdapter
from silex_core.runtime.settings import RuntimeSettingsStore
from silex_core.utils.config import telegram_public_mode_enabled
from silex_core.utils.logger import setup_logger

if TYPE_CHECKING:

    from telegram import Update
    from telegram.ext import ContextTypes

log = setup_logger("silex.adapters.telegram")

settings_store = RuntimeSettingsStore()

# Set during adapter startup — handlers read this singleton.
_active_loop: Any | None = None


def get_active_loop() -> Any | None:
    return _active_loop


def _env_allowlist() -> list[int]:
    allowed_users_env = os.getenv("ALLOWED_TELEGRAM_USERS", "")
    if not allowed_users_env:
        return []
    try:
        return [int(x.strip()) for x in allowed_users_env.split(",") if x.strip()]
    except ValueError:
        log.error("ALLOWED_TELEGRAM_USERS contains non-integer values!")
        return []


def telegram_user_allowed(user_id: int) -> bool:
    if telegram_public_mode_enabled():
        return True
    if settings_store.is_telegram_user_allowed(user_id):
        return True
    return user_id in _env_allowlist()


class TelegramAdapter(MessageAdapter):
    name = "telegram"

    @classmethod
    def is_configured(cls) -> bool:
        return bool(os.getenv("TELEGRAM_BOT_TOKEN"))

    async def start_async(self, cognitive_loop: Any) -> None:
        from dotenv import load_dotenv
        from telegram.ext import (
            ApplicationBuilder,
            CommandHandler,
            MessageHandler,
            filters,
        )

        load_dotenv()
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            log.error("TELEGRAM_BOT_TOKEN is not set.")
            return

        global _active_loop
        self._loop = cognitive_loop
        _active_loop = cognitive_loop

        app = ApplicationBuilder().token(token).build()

        app.add_handler(CommandHandler("start", _start_command))
        app.add_handler(CommandHandler("whoami", _whoami_command))
        app.add_handler(CommandHandler("approvals", _approvals_command))
        app.add_handler(CommandHandler("approve", _approve_command))
        app.add_handler(CommandHandler("reject", _reject_command))
        app.add_handler(CommandHandler("status", _status_command))
        app.add_handler(CommandHandler("usage", _usage_command))
        app.add_handler(CommandHandler("skills", _skills_command))
        app.add_handler(CommandHandler("logout", _logout_command))
        app.add_handler(CommandHandler("remember", _remember_command))
        app.add_handler(CommandHandler("briefing", _briefing_command))
        app.add_handler(CommandHandler("pair", _pair_command))
        app.add_handler(
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.Document.ALL)
                & ~filters.COMMAND,
                _handle_message,
            )
        )

        print("\n🚀 Starting Kinthic Telegram adapter...")
        _print_security_status()

        await app.initialize()
        app.job_queue.run_repeating(_poll_notifications, interval=5, first=2)
        app.job_queue.run_repeating(_daily_briefing_job, interval=86400, first=60)
        await app.start()
        await app.updater.start_polling()

        # Keep app reference to avoid GC
        self._app = app


async def _send_pending_approvals(update: "Update", loop: Any) -> None:
    approvals = await loop.tool_registry.get_pending_approvals()
    if not approvals:
        await update.message.reply_text("No pending tool approvals.")
        return
    lines = []
    for approval in approvals[:10]:
        lines.append(
            f"`{approval['id'][:8]}` · {approval['tool_name']} · {approval['risk_level']}\n"
            f"{approval['reason']}"
        )
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def _pair_command(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    code = " ".join(context.args).strip().upper()
    if not code:
        await update.message.reply_text("Usage: /pair <code>")
        return
    user = update.effective_user
    paired = settings_store.consume_pair_code(code, user.id, user.username)
    if paired:
        await update.message.reply_text(
            "Pairing successful. You can now use this Kinthic bot."
        )
    else:
        await update.message.reply_text("That pairing code is invalid or expired.")


async def _start_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    user_id = update.effective_user.id
    if context.args:
        code = context.args[0].strip().upper()
        if settings_store.consume_pair_code(
            code, user_id, update.effective_user.username
        ):
            await update.message.reply_text(
                "Pairing successful. Kinthic is now linked to your Telegram account."
            )
            return
    await update.message.reply_text(
        "👋 Hello! I am Kinthic — a local-first cognitive agent.\n\n"
        "My engine is online. I have access (within policy) to your tools, memory, "
        "and knowledge graph. How can I help you today?\n\n"
        f"Your Telegram ID: `{user_id}`\n"
        "If the operator generated a pairing code, send `/start CODE` or `/pair CODE`.",
        parse_mode="Markdown",
    )


async def _whoami_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    user = update.effective_user
    await update.message.reply_text(
        f"Telegram user: `{user.id}`\nUsername: `{user.username or 'unknown'}`",
        parse_mode="Markdown",
    )


async def _logout_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    settings_store.revoke_telegram_user(update.effective_user.id)
    await update.message.reply_text(
        "This Telegram account has been unpaired from Kinthic."
    )


async def _approvals_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    if not telegram_user_allowed(update.effective_user.id):
        await update.message.reply_text(
            "Access denied. Pair this account before requesting approvals."
        )
        return
    loop = get_active_loop()
    if loop is None:
        await update.message.reply_text("Cognitive engine not ready yet.")
        return
    await _send_pending_approvals(update, loop)


async def _status_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    if not telegram_user_allowed(update.effective_user.id):
        await update.message.reply_text(
            "Access denied. Pair this account before requesting status."
        )
        return
    loop = get_active_loop()
    if loop is None:
        await update.message.reply_text("Cognitive engine not ready yet.")
        return
    health = await loop.get_health_status()
    await update.message.reply_text(
        "Kinthic status:\n"
        f"- Provider: {health.get('provider')}\n"
        f"- Model: {health.get('model')}\n"
        f"- SmartRouter Fast Path: {health.get('router_fast_model', 'none')}\n"
        f"- Session: {health.get('current_session') or 'none'}\n"
        f"- Browser tool: {'on' if health.get('browser_registered') else 'off'}"
    )


async def _usage_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    if not telegram_user_allowed(update.effective_user.id):
        await update.message.reply_text("Access denied.")
        return
    loop = get_active_loop()
    if loop is None:
        await update.message.reply_text("Cognitive engine not ready.")
        return

    summary = await loop.get_usage_summary()
    totals = summary.get("totals", {})
    models = summary.get("models", [])

    lines = ["**📊 Usage & Cost Report**\n"]
    lines.append(f"**Total Requests:** {totals.get('requests', 0)}")
    lines.append(f"**Total Tokens In:** {totals.get('input_tokens', 0):,}")
    lines.append(f"**Total Tokens Out:** {totals.get('output_tokens', 0):,}")
    lines.append(f"**Estimated Cost:** ${totals.get('estimated_cost_usd', 0.0):.4f}\n")

    if models:
        lines.append("**Top Models:**")
        for m in models[:3]:
            lines.append(f"• {m['model']} (${m.get('estimated_cost_usd', 0.0):.4f})")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def _remember_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    if not telegram_user_allowed(update.effective_user.id):
        await update.message.reply_text("Access denied.")
        return
    loop = get_active_loop()
    if loop is None:
        await update.message.reply_text("Cognitive engine not ready.")
        return

    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text("Usage: /remember <query>")
        return

    safe_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    results = await loop.memory_store.db.fetch_all(
        "SELECT content, importance, confidence FROM memories WHERE content LIKE ? ESCAPE '\\' ORDER BY importance DESC, confidence DESC LIMIT 5",
        (f"%{safe_query}%",),
    )

    if not results:
        await update.message.reply_text("No memories found matching that query.")
        return

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def _briefing_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    if not telegram_user_allowed(update.effective_user.id):
        await update.message.reply_text("Access denied.")
        return
    from silex_core.services.briefing import BriefingService
    loop = get_active_loop()
    db = loop.db if loop else None
    service = BriefingService(db=db)
    report = await service.generate_briefing()
    await update.message.reply_text(report, parse_mode="Markdown")


async def _daily_briefing_job(context: "ContextTypes.DEFAULT_TYPE") -> None:
    try:
        from silex_core.services.briefing import BriefingService
        loop = get_active_loop()
        db = loop.db if loop else None
        service = BriefingService(db=db)
        await service.queue_briefing_notification()
    except Exception as exc:
        log.error("Failed to queue daily briefing job: %s", exc)


async def _approval_decision_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE", decision: str
) -> None:
    if not telegram_user_allowed(update.effective_user.id):
        await update.message.reply_text(
            "Access denied. Pair this account before resolving approvals."
        )
        return
    loop = get_active_loop()
    if loop is None:
        await update.message.reply_text("Cognitive engine not ready yet.")
        return
    approval_id = " ".join(context.args).strip()
    if not approval_id:
        await update.message.reply_text(f"Usage: /{decision} <approval-id>")
        return
    matches = await loop.tool_registry.get_pending_approvals()
    match = next((item for item in matches if item["id"].startswith(approval_id)), None)
    if not match:
        await update.message.reply_text("Approval not found.")
        return
    ok = await loop.tool_registry.resolve_approval(
        match["id"], "approved" if decision == "approve" else "rejected"
    )
    await update.message.reply_text(
        "Approval updated." if ok else "Failed to update approval."
    )


async def _approve_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    await _approval_decision_command(update, context, "approve")


async def _reject_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    await _approval_decision_command(update, context, "reject")


async def _skills_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    if not telegram_user_allowed(update.effective_user.id):
        await update.message.reply_text("Access denied.")
        return
    loop = get_active_loop()
    if loop is None or not getattr(loop, "skill_loader", None):
        await update.message.reply_text("Skill loader not available.")
        return
    skills = loop.skill_loader.list_skills()
    if not skills:
        await update.message.reply_text("No skills loaded.")
        return
    lines = [f"Loaded skills ({len(skills)}):"]
    for s in skills[:15]:
        lines.append(f"• {s['name']} — {s['description'][:60]}")
    await update.message.reply_text("\n".join(lines))


_pairing_attempts = {}


async def _handle_message(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    if not update.message:
        return
    user_text = update.message.text or update.message.caption or ""

    user_id = update.effective_user.id

    # Rate limit un-paired users (max 5 attempts per 60s)
    if not telegram_user_allowed(user_id):
        import time

        now = time.time()
        attempts = _pairing_attempts.get(user_id, [])
        attempts = [t for t in attempts if now - t < 60]
        if len(attempts) >= 5:
            await update.message.reply_text(
                "Rate limit exceeded. Please try again later."
            )
            return
        attempts.append(now)
        _pairing_attempts[user_id] = attempts

    images = None
    if update.message.photo:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        img_bytes = await file.download_as_bytearray()
        images = [{"mime": "image/jpeg", "bytes": bytes(img_bytes)}]
    elif (
        update.message.document
        and update.message.document.mime_type
        and update.message.document.mime_type.startswith("image/")
    ):
        file = await context.bot.get_file(update.message.document.file_id)
        img_bytes = await file.download_as_bytearray()
        images = [
            {"mime": update.message.document.mime_type, "bytes": bytes(img_bytes)}
        ]

    if not user_text and not images:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not telegram_user_allowed(user_id):
        potential_code = user_text.strip().upper()
        if potential_code.startswith("PAIR-"):
            if settings_store.consume_pair_code(
                potential_code, user_id, update.effective_user.username
            ):
                await update.message.reply_text(
                    "Pairing successful. Connection secured.\n\nHi, I'm Kinthic. What are we working on today?"
                )
                return

        log.warning("Unauthorized Telegram access attempt from user %s", user_id)
        await update.message.reply_text(
            "🚫 **Access Denied**\n\n"
            "Send your exact pairing code (eg. `PAIR-XYZ`) to secure this connection.\n"
            f"Your Telegram ID: `{user_id}`",
            parse_mode="Markdown",
        )
        return

    loop = get_active_loop()
    if loop is None:
        await update.message.reply_text(
            "Cognitive engine is still starting. Try again shortly."
        )
        return

    async def _keep_typing(bot, chat_id: int, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await bot.send_chat_action(chat_id=chat_id, action="typing")
            except Exception:
                break
            await asyncio.sleep(4)

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(context.bot, chat_id, stop_typing))
    try:
        try:
            cognitive = await loop.process(user_text, images=images)
        finally:
            stop_typing.set()
            typing_task.cancel()
            await asyncio.gather(typing_task, return_exceptions=True)

        # Message Splitting for Telegram's 4096 char limit
        MAX_LEN = 4000
        text_to_send = str(getattr(cognitive, "response", "") or "").strip()
        if not text_to_send:
            text_to_send = "I received your message, but the model response was empty. Please check your provider settings."
        if len(text_to_send) <= MAX_LEN:
            chunks = [text_to_send]
        else:
            chunks = []
            # Split by paragraph if possible, else strict chunking
            paragraphs = text_to_send.split("\n\n")
            current_chunk = ""
            for p in paragraphs:
                if len(current_chunk) + len(p) + 2 <= MAX_LEN:
                    current_chunk += p + "\n\n"
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())

                    if len(p) > MAX_LEN:
                        # Hard split if a single paragraph is massive
                        for i in range(0, len(p), MAX_LEN):
                            chunks.append(p[i : i + MAX_LEN])
                        current_chunk = ""
                    else:
                        current_chunk = p + "\n\n"
            if current_chunk:
                chunks.append(current_chunk.strip())

        try:
            for i, chunk in enumerate(chunks):
                prefix = f"[{i + 1}/{len(chunks)}]\n" if len(chunks) > 1 else ""
                await update.message.reply_text(prefix + chunk, parse_mode="Markdown")
        except Exception as parse_error:
            log.error(
                "Markdown parse failed, falling back to plain text: %s", parse_error
            )
            for i, chunk in enumerate(chunks):
                prefix = f"[{i + 1}/{len(chunks)}]\n\n" if len(chunks) > 1 else ""
                await update.message.reply_text(prefix + chunk)
    except Exception as exc:
        log.error("Error processing Telegram message: %s", exc, exc_info=True)
        err_msg = str(exc) or type(exc).__name__
        try:
            await update.message.reply_text(
                f"⚠️ Error processing message:\n`{err_msg[:400]}`",
                parse_mode="Markdown",
            )
        except Exception:
            try:
                await update.message.reply_text(
                    f"⚠️ Error processing message: {err_msg[:400]}"
                )
            except Exception:
                pass


async def _poll_notifications(context: "ContextTypes.DEFAULT_TYPE") -> None:
    from silex_engine.storage.database import Database
    from silex_core.utils.config import SILEX_DB

    db = None
    should_close = False
    try:
        loop = get_active_loop()
        if loop and loop.db:
            db = loop.db
        else:
            db = Database(str(SILEX_DB))
            await db.connect()
            should_close = True

        rows = await db.fetch_all(
            "SELECT id, message FROM notifications WHERE delivered = 0 ORDER BY created_at ASC"
        )
        if not rows:
            if should_close:
                await db.close()
            return

        paired = settings_store.list_telegram_users()
        chat_ids = [int(u["user_id"]) for u in paired if u.get("user_id")]

        for row in rows:
            sent_ok = False
            for chat_id in chat_ids:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=row["message"])
                    sent_ok = True
                except Exception as send_err:
                    log.warning(
                        "Could not deliver notification to %s: %s", chat_id, send_err
                    )

            if sent_ok or not chat_ids:
                await db.execute(
                    "UPDATE notifications SET delivered = 1 WHERE id = ?", (row["id"],)
                )

        if should_close:
            await db.close()

    except Exception as exc:
        log.error("Notification polling error: %s", exc)
        if db and should_close:
            try:
                await db.close()
            except Exception:
                pass


def _print_security_status() -> None:
    allowed = os.getenv("ALLOWED_TELEGRAM_USERS", "")
    public = telegram_public_mode_enabled()
    paired_users = settings_store.list_telegram_users()
    if allowed:
        print(f"🔒 Whitelist active: {allowed}")
    elif public:
        print("⚠️  PUBLIC MODE: Any Telegram user can interact with Kinthic!")
    elif paired_users:
        print(f"🔒 Pairing active: {len(paired_users)} Telegram user(s) authorized.")
    else:
        print(
            "🔒 Deny-by-default: generate a pairing code with `kinthic telegram pair` "
            "or set ALLOWED_TELEGRAM_USERS."
        )
