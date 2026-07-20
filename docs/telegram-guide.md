# Kinthic Telegram Guide

Kinthic is a local-first cognitive agent designed to act as your secure personal assistant via Telegram. Unlike public cloud bots, this agent runs entirely on your own machine (or VPS) and securely bridges to Telegram using your own private Bot Token. 

## Features

- **Paired Access Only**: By default, Kinthic operates in a deny-by-default security posture. Unrecognized Telegram accounts cannot access it.
- **Tool Approvals**: When Kinthic attempts to use a high-risk tool (e.g. running a terminal command), it will instantly push an Approval Request to your Telegram chat. You remain in the loop.
- **Persistent Memory**: Your memory graph is stored locally in `~/.kinthic`. Telegram is merely the UI layer.

## Setup & Pairing

1. Generate a Telegram Bot Token via [@BotFather](https://t.me/BotFather).
2. Run `kinthic init` on your host machine. When prompted, paste the Bot Token.
3. Kinthic will generate a deep-link. Click it, or open your bot and type `/start`.
4. If you start Kinthic on a headless server and connect from a new Telegram account, run `kinthic channels telegram pair` on the server CLI to generate a secure pairing code, then message `/pair CODE` to your bot.

## Core Commands

Kinthic listens to natural language directly, but you can also use these system commands:

- `/whoami` - Prints your authorized Telegram ID.
- `/status` - Reports the active LLM provider, memory session, and backend health.
- `/skills` - Lists the skills currently loaded into Kinthic's cognitive loop.
- `/approvals` - Shows any pending tool executions that require your permission.
- `/logout` - Sever the pairing connection between this Telegram account and your Kinthic instance.

## Managing Tool Approvals

When Kinthic attempts a risky action, you will receive an immediate notification:

> ⚠️ **Approval Required**
> **Tool:** `run_terminal_command`
> **Risk:** `repo_write`
> **ID:** `a1b2c3d4`
>
> Type `/approve a1b2c3d4` or `/reject a1b2c3d4`

Respond with the `/approve` or `/reject` command followed by the short ID prefix to authorize or block the action. Kinthic will wait securely for your decision before proceeding.

## Troubleshooting

- **No response to messages?** Ensure `kinthic channels telegram run` is actively running on your host machine (or the daemon is started).
- **"Access Denied"** You haven't paired your account. Follow the Pairing instructions above.
- **Long messages getting cut off?** Kinthic automatically splits massive code blocks into multiple 4096-character chunks. If a chunk appears completely missing, check your host's connection.
- **Approval timed out?** If you wait too long to approve a tool (default 120 seconds), Kinthic will assume a rejection to prevent system deadlock. You will need to ask Kinthic to retry the action.
