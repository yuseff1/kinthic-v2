"""Discord messaging adapter for Kinthic."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from silex_core.adapters.base import MessageAdapter
from silex_core.utils.logger import setup_logger

if TYPE_CHECKING:


log = setup_logger("silex.adapters.discord")

_active_loop: Any | None = None


def get_active_loop() -> Any | None:
    return _active_loop


def _env_allowlist() -> list[int]:
    raw = os.getenv("ALLOWED_DISCORD_USERS", "")
    if not raw:
        return []
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        log.error("ALLOWED_DISCORD_USERS contains non-integer values!")
        return []


def discord_user_allowed(user_id: int) -> bool:
    if os.getenv("DISCORD_PUBLIC_MODE", "").lower() in {"1", "true", "yes"}:
        return True
    return user_id in _env_allowlist()


class DiscordAdapter(MessageAdapter):
    name = "discord"

    @classmethod
    def is_configured(cls) -> bool:
        return bool(os.getenv("DISCORD_BOT_TOKEN"))

    async def start_async(self, cognitive_loop: Any) -> None:
        try:
            import discord
            from discord.ext import commands
        except ImportError:
            print(
                "\n❌ discord.py is not installed.\n"
                "Install with: uv pip install 'openyfai-kinthic[discord]'\n"
                "Or from the project venv: pip install discord.py>=2.3\n"
            )
            return

        from dotenv import load_dotenv

        load_dotenv()
        token = os.getenv("DISCORD_BOT_TOKEN")
        if not token:
            log.error("DISCORD_BOT_TOKEN is not set.")
            return

        global _active_loop
        self._loop = cognitive_loop
        _active_loop = cognitive_loop

        intents = discord.Intents.default()
        intents.message_content = True
        bot = commands.Bot(command_prefix="!", intents=intents)

        @bot.event
        async def on_ready() -> None:
            log.info("Discord adapter online as %s", bot.user)
            print(f"\n🚀 Kinthic Discord adapter online as {bot.user}")

        @bot.command(name="start")
        async def start_cmd(ctx: commands.Context) -> None:
            await ctx.reply(
                f"👋 Kinthic is online.\n"
                f"Your Discord user ID: `{ctx.author.id}`\n"
                f"Add this ID to ALLOWED_DISCORD_USERS in your .env to authorize access.",
                mention_author=False,
            )

        @bot.command(name="status")
        async def status_cmd(ctx: commands.Context) -> None:
            if not discord_user_allowed(ctx.author.id):
                await ctx.reply("Access denied.")
                return
            loop = get_active_loop()
            if loop is None:
                await ctx.reply("Cognitive engine not ready yet.")
                return
            health = await loop.get_health_status()
            await ctx.reply(
                f"Provider: {health.get('provider')}\n"
                f"Model: {health.get('model')}\n"
                f"Session: {health.get('current_session') or 'none'}"
            )

        @bot.command(name="approvals")
        async def approvals_cmd(ctx: commands.Context) -> None:
            if not discord_user_allowed(ctx.author.id):
                await ctx.reply("Access denied.")
                return
            loop = get_active_loop()
            if loop is None:
                await ctx.reply("Cognitive engine not ready yet.")
                return
            pending = await loop.tool_registry.get_pending_approvals()
            if not pending:
                await ctx.reply("No pending tool approvals.")
                return
            lines = [
                f"`{a['id'][:8]}` · {a['tool_name']} · {a['risk_level']}"
                for a in pending[:10]
            ]
            await ctx.reply("\n".join(lines))

        @bot.command(name="approve")
        async def approve_cmd(ctx: commands.Context, approval_id: str) -> None:
            await _resolve_approval(ctx, approval_id, "approved")

        @bot.command(name="reject")
        async def reject_cmd(ctx: commands.Context, approval_id: str) -> None:
            await _resolve_approval(ctx, approval_id, "rejected")

        @bot.event
        async def on_message(message: discord.Message) -> None:
            if message.author.bot:
                return

            # Gate BEFORE dispatching to any command handler. Previously
            # `process_commands` ran unconditionally first and each command
            # did its own internal allow-check — correct today, but fragile:
            # any future `@bot.command` added without that check would be
            # silently exposed to unauthorized users. `!start` is the one
            # deliberate exception (its only purpose is letting a new user
            # discover their own Discord ID for onboarding).
            content = message.content.strip()
            is_start_command = (
                content.split()[0].lower() == "!start" if content else False
            )

            if not discord_user_allowed(message.author.id) and not is_start_command:
                if content.startswith("!"):
                    await message.reply(
                        f"🚫 Access denied. Your Discord ID is `{message.author.id}`. "
                        "Ask the operator to add it to ALLOWED_DISCORD_USERS, or run `!start`."
                    )
                else:
                    await message.reply(
                        f"🚫 Access denied. Your Discord ID is `{message.author.id}`. "
                        "Ask the operator to add it to ALLOWED_DISCORD_USERS."
                    )
                return

            await bot.process_commands(message)

            if content.startswith("!"):
                return

            loop = get_active_loop()
            if loop is None:
                await message.reply(
                    "Cognitive engine is still starting. Try again shortly."
                )
                return

            async with message.channel.typing():
                try:
                    result = await loop.process(message.content)
                    text = getattr(result, "response", str(result))
                    # Discord message limit is 2000 chars
                    if len(text) > 1900:
                        text = text[:1900] + "\n…(truncated)"
                    await message.reply(text)
                except Exception as exc:
                    log.error("Discord message processing error: %s", exc)
                    await message.reply(
                        "⚠️ Internal error while processing your message. Please try again."
                    )

        _print_security_status()
        import asyncio

        asyncio.create_task(bot.start(token))
        self._bot = bot


async def _resolve_approval(ctx, approval_id: str, decision: str) -> None:
    if not discord_user_allowed(ctx.author.id):
        await ctx.reply("Access denied.")
        return
    loop = get_active_loop()
    if loop is None:
        await ctx.reply("Cognitive engine not ready yet.")
        return
    matches = await loop.tool_registry.get_pending_approvals()
    match = next((item for item in matches if item["id"].startswith(approval_id)), None)
    if not match:
        await ctx.reply("Approval not found.")
        return
    ok = await loop.tool_registry.resolve_approval(match["id"], decision)
    await ctx.reply("Approval updated." if ok else "Failed to update approval.")


def _print_security_status() -> None:
    allowed = os.getenv("ALLOWED_DISCORD_USERS", "")
    public = os.getenv("DISCORD_PUBLIC_MODE", "").lower() in {"1", "true", "yes"}
    if public:
        print("⚠️  PUBLIC MODE: Any Discord user can interact with Kinthic!")
    elif allowed:
        print(f"🔒 Discord whitelist active: {allowed}")
    else:
        print(
            "🔒 Deny-by-default: set ALLOWED_DISCORD_USERS in .env "
            "(comma-separated Discord user IDs)."
        )
