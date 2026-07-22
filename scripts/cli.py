from __future__ import annotations

# ── LOG SILENCE — must run before any silex import ───────────────────────────
# silex modules call setup_logger() at import time, which attaches RichHandlers
# to sys.stderr. This block installs a file-only root handler FIRST so those
# calls find an existing handler and skip adding a stream handler (see
# logger.py: `if not logger.handlers`). Result: zero log text on the terminal.
import logging
import os
from pathlib import Path as _Path

_log_dir = _Path.home() / ".kinthic"
_log_dir.mkdir(parents=True, exist_ok=True)
_log_file = _log_dir / "kinthic.log"

# Set env var so silex/utils/logger.py setup_logger() picks file mode
os.environ.setdefault("KINTHIC_INK_ACTIVE", "1")

_root = logging.getLogger()
_root.handlers.clear()
_root.setLevel(logging.DEBUG)
_fh = logging.FileHandler(str(_log_file), encoding="utf-8", mode="a")
_fh.setFormatter(
    logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)
_root.addHandler(_fh)
# ─────────────────────────────────────────────────────────────────────────────

import argparse
import asyncio

from silex_core.llm.catalog import get_provider_defaults
from silex_core.llm.registry import list_providers
from silex_core.runtime.settings import RuntimeSettingsStore
from silex_core.utils.config import (
    browser_actions_enabled,
    code_apply_enabled,
    terminal_execution_enabled,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kinthic", description="Kinthic local operator CLI"
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "init", help="First-run wizard: provider, skills, Telegram, MCP"
    )
    subparsers.add_parser("innit", help="Alias for init (common typo)")
    subparsers.add_parser("onboard", help="Alias for init (first-run wizard)")
    subparsers.add_parser("setup", help="Alias for init (first-run wizard)")
    doctor_parser = subparsers.add_parser(
        "doctor", help="Show local setup and security status"
    )
    doctor_parser.add_argument(
        "--ping",
        action="store_true",
        help="Run a tiny live API call to verify configured provider credentials",
    )
    subparsers.add_parser("models", help="List supported providers and models")
    subparsers.add_parser("web", help="Launch the local Kinthic web dashboard")
    subparsers.add_parser("usage", help="View usage and token costs")
    subparsers.add_parser("observe", help="Visualize the active Silex memory graph")

    daemon_parser = subparsers.add_parser(
        "daemon", help="Manage the background supervisor daemon"
    )
    daemon_sub = daemon_parser.add_subparsers(dest="daemon_command")
    daemon_sub.add_parser("start", help="Start the supervisor in the background")
    daemon_sub.add_parser("stop", help="Stop the background supervisor")
    daemon_sub.add_parser("status", help="Check if the daemon is running")
    daemon_sub.add_parser("logs", help="Tail the daemon logs")
    daemon_sub.add_parser("run", help="Run the supervisor in the foreground")
    daemon_install = daemon_sub.add_parser(
        "install", help="Install as a systemd/LaunchAgent service (survives reboot)"
    )
    daemon_install.add_argument(
        "--force", action="store_true", help="Overwrite an existing service unit"
    )
    daemon_sub.add_parser("uninstall", help="Remove the installed service unit")

    data_parser = subparsers.add_parser(
        "data", help="Manage memories, backups, and exports"
    )
    data_sub = data_parser.add_subparsers(dest="data_command")
    backup_p = data_sub.add_parser("backup", help="Export ~/.kinthic to a zip archive")
    backup_p.add_argument(
        "--output", default="kinthic-backup.zip", help="Output zip file"
    )
    restore_p = data_sub.add_parser(
        "restore", help="Restore ~/.kinthic from a backup zip"
    )
    restore_p.add_argument("archive", help="Path to kinthic-backup.zip")
    restore_p.add_argument(
        "--dry-run", action="store_true", help="Preview restore plan (default)"
    )
    restore_p.add_argument("--apply", action="store_true", help="Execute restore")
    restore_p.add_argument(
        "--no-pre-backup",
        action="store_true",
        help="Skip automatic pre-restore safety backup",
    )
    export_p = data_sub.add_parser(
        "export", help="Export training trajectories (SFT / GRPO / CSV)"
    )
    export_p.add_argument(
        "--format",
        choices=["sft", "grpo", "csv"],
        default="grpo",
        help="Output format (default: grpo)",
    )
    export_p.add_argument("--output", default=None, help="Output file path")
    export_p.add_argument(
        "--success-only",
        action="store_true",
        help="Only include successful trajectories",
    )
    export_p.add_argument(
        "--since", default=None, metavar="YYYY-MM-DD", help="Lower date bound (UTC)"
    )
    export_p.add_argument(
        "--until", default=None, metavar="YYYY-MM-DD", help="Upper date bound (UTC)"
    )
    export_p.add_argument(
        "--max",
        type=int,
        default=10_000,
        dest="max_traj",
        help="Maximum number of trajectories to export",
    )
    migrate_scan = data_sub.add_parser(
        "migrate", help="Scan and import migratable data from legacy agents"
    )
    migrate_scan.add_argument(
        "--from", dest="source", choices=["hermes", "openclaw"], required=True
    )
    migrate_scan.add_argument("--path", default=None, help="Custom path to target")
    migrate_group = migrate_scan.add_mutually_exclusive_group()
    migrate_group.add_argument(
        "--scan-only", action="store_true", help="Only scan without importing"
    )
    migrate_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be migrated without copying",
    )
    migrate_group.add_argument(
        "--apply", action="store_true", help="Execute the migration"
    )

    channels_parser = subparsers.add_parser(
        "channels", help="Manage connected messaging channels"
    )
    channels_sub = channels_parser.add_subparsers(dest="channel_app")
    telegram_parser = channels_sub.add_parser("telegram", help="Telegram integration")
    telegram_sub = telegram_parser.add_subparsers(dest="channel_cmd")
    telegram_sub.add_parser("run", help="Run the Telegram bot")
    telegram_sub.add_parser("pair", help="Generate a Telegram pairing code")
    discord_parser = channels_sub.add_parser("discord", help="Discord integration")
    discord_sub = discord_parser.add_subparsers(dest="channel_cmd")
    discord_sub.add_parser("run", help="Run the Discord bot")

    proposals_parser = subparsers.add_parser(
        "proposals", help="Manage self-improvement proposals"
    )
    proposals_sub = proposals_parser.add_subparsers(dest="proposals_command")
    proposals_sub.add_parser("list", help="List all pending proposals")
    approve_p = proposals_sub.add_parser(
        "approve", help="Approve a proposal by ID prefix"
    )
    approve_p.add_argument("proposal_id", help="Proposal ID or prefix")
    reject_p = proposals_sub.add_parser("reject", help="Reject a proposal by ID prefix")
    reject_p.add_argument("proposal_id", help="Proposal ID or prefix")

    skills_parser = subparsers.add_parser("skills", help="Manage Kinthic skills")
    skills_sub = skills_parser.add_subparsers(dest="skills_command")
    skills_sub.add_parser("list", help="List installed and catalog skills")
    skills_search = skills_sub.add_parser("search", help="Search the skill catalog")
    skills_search.add_argument("query", help="Search query")
    skills_install = skills_sub.add_parser(
        "install", help="Install a skill by name or URL"
    )
    skills_install.add_argument("name", help="Skill name or https:// URL")
    skills_sub.add_parser("reload", help="Reload skills from disk")
    skills_uninstall = skills_sub.add_parser(
        "uninstall", help="Remove an installed skill"
    )
    skills_uninstall.add_argument("name", help="Skill name")
    skills_show = skills_sub.add_parser("show", help="Show full skill markdown")
    skills_show.add_argument("name", help="Skill name")
    skills_sub.add_parser("refresh", help="Refresh skill catalog from KinthicHub")

    mcp_parser = subparsers.add_parser("mcp", help="Manage MCP server integrations")
    mcp_sub = mcp_parser.add_subparsers(dest="mcp_command")
    mcp_sub.add_parser("list", help="List configured MCP servers")
    mcp_add = mcp_sub.add_parser("add", help="Add an MCP server")
    mcp_add.add_argument("name", help="Server name")
    mcp_add.add_argument(
        "--preset",
        choices=["filesystem", "fetch", "github"],
        help="Use a bundled preset",
    )
    mcp_add.add_argument(
        "--exec", dest="mcp_exec", help="Executable command (with --args)"
    )
    mcp_add.add_argument(
        "--args", nargs="*", default=[], dest="mcp_args", help="Command arguments"
    )
    mcp_enable = mcp_sub.add_parser("enable", help="Enable an MCP server")
    mcp_enable.add_argument("name", help="Server name")
    mcp_disable = mcp_sub.add_parser("disable", help="Disable an MCP server")
    mcp_disable.add_argument("name", help="Server name")
    mcp_test = mcp_sub.add_parser("test", help="Test connectivity to an MCP server")
    mcp_test.add_argument("name", help="Server name")
    mcp_tools = mcp_sub.add_parser("tools", help="List tools exposed by MCP servers")
    mcp_tools.add_argument("--server", default=None, help="Filter by server name")
    mcp_serve = mcp_sub.add_parser("serve", help="Run the Silex memory MCP server")
    mcp_serve.add_argument(
        "--stdio", action="store_true", help="stdio transport (Claude Desktop / Cursor)"
    )
    mcp_print = mcp_sub.add_parser("print-config", help="Print MCP client config JSON")
    mcp_print.add_argument("--client", choices=["claude", "cursor"], default="claude")

    benchmark_parser = subparsers.add_parser(
        "benchmark", help="Run evaluation benchmarks"
    )
    benchmark_sub = benchmark_parser.add_subparsers(dest="benchmark_command")
    recall_p = benchmark_sub.add_parser(
        "recall", help="Memory recall needle-in-haystack benchmark"
    )
    recall_p.add_argument("--seed", type=int, default=42, help="RNG seed (default: 42)")
    recall_p.add_argument(
        "--noise", type=int, default=None, help="Override distractor memory count"
    )
    recall_p.add_argument(
        "--conditions",
        nargs="*",
        default=None,
        help="Condition names (default: all in suite.yaml)",
    )
    recall_p.add_argument("--output", default=None, help="JSON results path")
    recall_p.add_argument("--report", default=None, help="Markdown report path")
    recall_p.add_argument(
        "--track",
        choices=["retrieval", "mcp"],
        default="retrieval",
        help="retrieval=MemoryStore baselines; mcp=silex_recall service path",
    )

    return parser


def detect_local_ollama_models(base_url: str) -> list[str]:
    """Auto-detect installed models from local Ollama tags API."""
    import httpx

    try:
        url = base_url.rstrip("/").replace("/v1", "") + "/api/tags"
        resp = httpx.get(url, timeout=1.5)
        if resp.status_code == 200:
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        pass
    return []


def detect_local_lmstudio_models(base_url: str) -> list[str]:
    """Auto-detect loaded models from local LM Studio models API."""
    import httpx

    try:
        url = base_url.rstrip("/") + "/models"
        resp = httpx.get(url, timeout=1.5)
        if resp.status_code == 200:
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]
    except Exception:
        pass
    return []


async def run_interactive_setup(*, onboard: bool = False) -> None:
    """The premium interactive setup wizard with dynamically detected local models."""
    from silex_core.ui.onboarding import OnboardingUI
    from silex_core.llm.registry import get_provider_profile
    import logging

    # Silence internal warnings and client initialization logs during the setup TUI
    logging.getLogger("silex").setLevel(logging.ERROR)
    logging.getLogger("kinthic").setLevel(logging.ERROR)

    ui = OnboardingUI()
    ui.clear()  # Clear any initial warning logs printed during imports/startup
    store = RuntimeSettingsStore()
    defaults = {"fast_model": "", "reasoning_model": ""}

    if onboard:
        from silex_core.utils.config import KINTHIC_HOME, KINTHIC_SKILLS, WORKSPACE_DIR

        ui.render_step(
            "Welcome to Kinthic",
            f"Home: {KINTHIC_HOME}\nSkills: {KINTHIC_SKILLS}\nWorkspace: {WORKSPACE_DIR}",
            subtitle="This wizard configures your provider, skills, and optional channels",
        )
        ui.prompt("Press Enter to continue")

    providers = (
        list_providers()
    )  # Returns list of dicts: {id, label, env_key, base_url, models}
    if not providers:
        ui.render_step(
            "Setup Error",
            "No model providers could be loaded from your Kinthic/Silex plugins folder.\n\n"
            "This usually indicates a packaging/installation error where the provider manifests "
            "(plugin.yaml files) were not copied to site-packages.",
            subtitle="Press Enter to exit",
        )
        ui.prompt("Press Enter to exit")
        return

    # Sort: gemini first, anthropic second, then cloud, then local, custom last
    def provider_sort_key(p):
        p_id = p.name
        if p_id == "gemini":
            return 0
        if p_id == "anthropic":
            return 1
        if p_id == "openai":
            return 2
        if p_id == "azure":
            return 3
        if p_id == "deepseek":
            return 4
        if p_id == "custom":
            return 99
        return 10

    providers = sorted(providers, key=provider_sort_key)

    # 1. Provider Selection — build labels with descriptions
    provider_labels = []
    for p in providers:
        profile = get_provider_profile(p.name)
        desc = profile.description if profile else ""
        label = p.display_name
        if desc:
            label += f" ({desc})"
        provider_labels.append(label)

    provider_idx = ui.prompt_choice(
        "provider",
        provider_labels,
        default_idx=0,
        subtitle="Choose your primary LLM provider",
    )
    provider = providers[provider_idx]

    custom_base_url = ""
    custom_label = ""
    detected_models: list[str] = []

    if provider.name == "ollama":
        base_url = provider.base_url or "http://127.0.0.1:11434/v1"
        ui.render_step("Local Core", "Auto-detecting installed Ollama models...")
        detected_models = detect_local_ollama_models(base_url)
    elif provider.name == "lm_studio":
        base_url = provider.base_url or "http://127.0.0.1:1234/v1"
        ui.render_step("Local Core", "Auto-detecting loaded LM Studio models...")
        detected_models = detect_local_lmstudio_models(base_url)

    if provider.name == "custom":
        ui.render_step(
            "Universal Provider",
            "Configure your custom endpoint.",
            subtitle="Display Name (e.g. My Private Llama)",
        )
        custom_label = ui.prompt("Display Name", default="Custom Model")

        ui.render_step(
            "Universal Provider",
            f"Configuring '{custom_label}'",
            subtitle="Base URL (e.g. https://api.proxy.com/v1)",
        )
        custom_base_url = ""
        while not custom_base_url:
            custom_base_url = ui.prompt("Base URL").strip()

        ui.render_step("Universal Provider", "Auto-detecting available models...")
        detected_models = detect_local_lmstudio_models(custom_base_url)

        if detected_models:
            model_choices = [f"{m} (detected)" for m in detected_models] + [
                "Enter custom model ID manually..."
            ]
            m_idx = ui.prompt_choice(
                "model",
                model_choices,
                default_idx=0,
                subtitle=f"Select the model for {custom_label}",
            )
            if m_idx < len(detected_models):
                model_id = detected_models[m_idx]
            else:
                ui.render_step(
                    "Universal Provider",
                    f"Configuring '{custom_label}'",
                    subtitle="Exact Model ID (e.g. mixtral-8x7b-instruct)",
                )
                model_id = ""
                while not model_id:
                    model_id = ui.prompt("Model ID").strip()
        else:
            ui.render_step(
                "Universal Provider",
                f"Configuring '{custom_label}'",
                subtitle="Exact Model ID (e.g. mixtral-8x7b-instruct)",
            )
            model_id = ""
            while not model_id:
                model_id = ui.prompt("Model ID").strip()

        model = {"id": model_id, "label": custom_label}
        defaults = {"fast_model": model_id, "reasoning_model": model_id}

    elif provider.name == "azure":
        ui.render_step(
            "Azure OpenAI",
            "Configure your Azure OpenAI resource.",
            subtitle="Endpoint URL (e.g. https://my-resource.openai.azure.com)",
        )
        custom_base_url = ""
        while not custom_base_url:
            custom_base_url = ui.prompt("Endpoint URL").strip()

        ui.render_step(
            "Azure OpenAI",
            "Configure your Azure OpenAI deployment.",
            subtitle="Deployment Name / Model ID (e.g. gpt-4o)",
        )
        model_id = ""
        while not model_id:
            model_id = ui.prompt("Deployment Name").strip()
        model = {"id": model_id, "label": model_id}
        defaults = {"fast_model": model_id, "reasoning_model": model_id}

    elif provider.name in ("ollama", "lm_studio"):
        if detected_models:
            model_choices = [f"{m} (installed)" for m in detected_models] + [
                "Enter custom model ID manually..."
            ]
            m_idx = ui.prompt_choice(
                "model",
                model_choices,
                default_idx=0,
                subtitle=f"Select from your locally installed {provider.display_name} models",
            )
            if m_idx < len(detected_models):
                model_id = detected_models[m_idx]
                model = {"id": model_id, "label": model_id}
            else:
                ui.render_step(
                    provider.display_name,
                    f"Configuring '{provider.display_name}'",
                    subtitle="Enter custom model ID manually (e.g. llama3:8b)",
                )
                model_id = ""
                while not model_id:
                    model_id = ui.prompt("Model ID").strip()
                model = {"id": model_id, "label": model_id}
        else:
            # Fallback to curated catalog
            models = provider.fetch_models()
            model_labels = [
                f"{m['label']} ({m.get('tier')})" if m.get("tier") else m["label"]
                for m in models
            ] + ["Enter custom model ID manually..."]
            m_idx = ui.prompt_choice(
                "model",
                model_labels,
                default_idx=0,
                subtitle="Select model (no running local models detected)",
            )
            if m_idx < len(models):
                model = models[m_idx]
            else:
                ui.render_step(
                    provider.display_name,
                    f"Configuring '{provider.display_name}'",
                    subtitle="Enter model ID (e.g. llama3)",
                )
                model_id = ""
                while not model_id:
                    model_id = ui.prompt("Model ID").strip()
                model = {"id": model_id, "label": model_id}
        defaults = get_provider_defaults(provider.name)

    else:
        # 2. Model Selection — cloud provider
        models = provider.fetch_models()
        model_labels = [
            f"{m['label']} ({m.get('tier')})" if m.get("tier") else m["label"]
            for m in models
        ] + ["Enter custom model ID manually..."]
        m_idx = ui.prompt_choice(
            "model",
            model_labels,
            default_idx=0,
            subtitle=f"Select the active model for {provider.display_name}",
        )
        if m_idx < len(models):
            model = models[m_idx]
        else:
            ui.render_step(
                provider.display_name,
                f"Configuring '{provider.display_name}'",
                subtitle="Enter custom model ID manually",
            )
            model_id = ""
            while not model_id:
                model_id = ui.prompt("Model ID").strip()
            model = {"id": model_id, "label": model_id}
        defaults = get_provider_defaults(provider.name)

    # 3. API Key Verification
    api_key = ""
    if provider.name not in ("ollama", "lm_studio"):
        while True:
            ui.render_step(
                "Authentication",
                f"Identity verification for {provider.display_name}.",
                subtitle="Paste your API key below",
            )
            api_key = ui.prompt("API Key", password=True)
            if not api_key:
                break

            ui.render_step("Authentication", "Verifying connectivity...")
            from silex_core.llm.provider_test import ping_provider

            result = await ping_provider(
                provider.name,
                api_key,
                model["id"],
                base_url=custom_base_url
                if provider.name in ("custom", "azure")
                else None,
            )

            if result.get("ok"):
                store.set_provider_secret(provider.name, api_key)
                break
            else:
                ui.render_step(
                    "Authentication",
                    "Invalid API key or connectivity failure.",
                    subtitle=result.get("message", "Check your key and try again."),
                )
                ui.prompt("Press Enter to retry")
    else:
        # Ollama / LM Studio connectivity check
        ui.render_step("Local Core", "Verifying local core endpoint...")
        from silex_core.llm.provider_test import ping_provider

        result = await ping_provider(provider.name, "", model["id"])
        if not result.get("ok"):
            ui.render_step(
                "Local Core",
                f"{provider.display_name} unreachable.",
                subtitle=result.get(
                    "hint",
                    f"Ensure {provider.display_name} is running and the model is loaded/pulled.",
                ),
            )
            ui.prompt("Press Enter to continue anyway")

    if onboard:
        ui.render_step("Live verify", "Running provider health check...")
        from silex_core.llm.provider_test import ping_provider
        from silex_core.utils.config import get_provider_secret

        while True:
            key = (
                get_provider_secret(provider.name, settings_store=store) or ""
            ).strip()
            result = await ping_provider(
                provider.name,
                key,
                model["id"],
                base_url=custom_base_url
                if provider.name in ("custom", "azure")
                else None,
            )
            if result.get("ok"):
                ui.render_step("Live verify", "✓ Provider responded successfully.")
                break
            ui.render_step(
                "Live verify",
                "Provider check failed.",
                subtitle=result.get("message", "Fix your API key or model and retry."),
            )
            retry = ui.prompt_choice(
                "Retry",
                ["Retry ping", "Continue anyway (not recommended)"],
                default_idx=0,
            )
            if retry == 1:
                break

        ui.render_step("Core skills", "Installing bundled workflow skills...")
        from silex_core.plugins.registry import get_registry

        reg = get_registry()
        try:
            ok, refresh_msg = reg.refresh_from_remote()
            if ok:
                ui.render_step("Core skills", refresh_msg)
        except Exception:
            pass
        installed = reg.install_core_skills()
        ui.render_step(
            "Core skills",
            f"Installed {len(installed)} skills: {', '.join(installed) or 'none'}",
        )
        await asyncio.sleep(0.8)

    # 4. Telegram Pairing
    telegram_idx = ui.prompt_choice(
        "Telegram link",
        ["Yes (recommended for remote access)", "No"],
        default_idx=0,
        subtitle="Would you like to link Kinthic to your Telegram account?",
    )
    wants_telegram = telegram_idx == 0

    if wants_telegram:
        ui.render_step(
            "Telegram Link",
            "Enter your Telegram Bot Token.",
            subtitle="Get this from @BotFather",
        )
        bot_token = ui.prompt("Bot Token", password=True)
        if bot_token:
            from silex_core.utils.telegram_pairing import TelegramPairingSession

            session = TelegramPairingSession(bot_token)
            try:
                await session.get_bot_info()
                deep_link = session.get_deep_link()

                ui.render_step(
                    "Telegram Link",
                    f"Open this link in Telegram and click 'Start':\n\n  {deep_link}",
                    subtitle="Waiting for handshake...",
                )

                chat_id = await session.wait_for_handshake(timeout_s=120)

                store.set_provider_secret("telegram", bot_token)
                store.add_paired_telegram_user(chat_id)

                # Write to .env to allow kinthic telegram run to work out of the box
                from silex_core.utils.config import KINTHIC_HOME

                env_path = KINTHIC_HOME / ".env"
                env_lines = []
                if env_path.exists():
                    env_lines = env_path.read_text(encoding="utf-8").splitlines()

                # Replace existing token or append
                new_lines = [
                    line
                    for line in env_lines
                    if not line.startswith("TELEGRAM_BOT_TOKEN=")
                ]
                new_lines.append(f"TELEGRAM_BOT_TOKEN={bot_token}")
                env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

                ui.render_step(
                    "Telegram Link",
                    "✓ Identity Verified. Account Linked and .env updated.",
                )
                await asyncio.sleep(1.5)
            except Exception as e:
                ui.render_step("Telegram Link", f"Pairing failed: {e}")
                ui.prompt("Press Enter to skip")

    # 4.2. Search Configuration
    search_idx = ui.prompt_choice(
        "Search Setup",
        [
            "Keep using free DuckDuckGo (zero config)",
            "Configure paid Search APIs (Tavily, Brave)",
        ],
        default_idx=0,
        subtitle="Would you like to set up high-reliability Search APIs for internet searches?",
    )

    if search_idx == 1:
        prov_idx = ui.prompt_choice(
            "Search API Provider",
            [
                "Configure Tavily API (Agent-optimized search)",
                "Configure Brave Search API",
                "Configure Both (Tavily + Brave)",
            ],
            default_idx=0,
            subtitle="Choose which Search API you want to configure:",
        )

        if prov_idx in (0, 2):
            ui.render_step(
                "Search Setup",
                "Configure Tavily API.",
                subtitle="Enter your Tavily API Key (or press enter to skip)",
            )
            tavily_key = ui.prompt("Tavily API Key", password=True).strip()
            if tavily_key:
                store.set_provider_secret("tavily", tavily_key)
                ui.render_step("Search Setup", "✓ Tavily API Key saved.")
                await asyncio.sleep(0.8)

        if prov_idx in (1, 2):
            ui.render_step(
                "Search Setup",
                "Configure Brave Search API.",
                subtitle="Enter your Brave Search API Key (or press enter to skip)",
            )
            brave_key = ui.prompt("Brave Search API Key", password=True).strip()
            if brave_key:
                store.set_provider_secret("brave", brave_key)
                ui.render_step("Search Setup", "✓ Brave Search API Key saved.")
                await asyncio.sleep(0.8)

    if onboard:
        mcp_idx = ui.prompt_choice(
            "MCP servers",
            [
                "Skip for now (configure later with kinthic mcp add)",
                "Enable filesystem MCP (read-only workspace)",
                "Enable fetch MCP",
                "Enable both filesystem + fetch",
            ],
            default_idx=0,
            subtitle="Optional Model Context Protocol integrations",
        )
        if mcp_idx in (1, 3):
            await _onboard_enable_mcp_preset(ui, "filesystem")
        if mcp_idx in (2, 3):
            await _onboard_enable_mcp_preset(ui, "fetch")

    # 4.5. Configure Agent Persona
    ui.render_step(
        "Configure Agent Persona", "Choose the identity and name of your local agent."
    )
    agent_name_input = ui.prompt(
        "Name your specific agent instance (Default: Kinthic)", default="Kinthic"
    ).strip()

    from silex_core.utils.config import KINTHIC_PERSONA
    import yaml

    persona_data = {
        "agent_name": "Kinthic",
        "engine_name": "SILEX",
        "primary_brand": "Kinthic (λ)",
        "personality_archetype": "Sovereign CLI Development Engine",
        "tone_modifiers": [
            "Direct, sharp, and technically flawless.",
            "Gives raw engineering facts, completely avoiding polite fluff.",
        ],
        "custom_greeting": "🧠 SILEX memory core active. Kinthic CLI operational. Systems are 100% green.",
    }

    if KINTHIC_PERSONA.exists():
        try:
            with open(KINTHIC_PERSONA, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    persona_data.update(loaded)
        except Exception:
            pass

    if agent_name_input:
        persona_data["agent_name"] = agent_name_input

    try:
        with open(KINTHIC_PERSONA, "w", encoding="utf-8") as f:
            yaml.safe_dump(persona_data, f, sort_keys=False, allow_unicode=True)
    except Exception as e:
        logging.getLogger("kinthic.cli").error(
            "Failed to save persona name in setup: %s", e
        )

    # 5. Finalize
    settings_payload = {
        "setup_completed": True,
        "provider": provider.name,
        "model": model["id"],
        "fast_model": defaults["fast_model"],
        "reasoning_model": defaults["reasoning_model"],
    }

    if custom_base_url:
        settings_payload["base_url"] = custom_base_url
    if custom_label:
        settings_payload["custom_label"] = custom_label

    store.save_settings(settings_payload)

    if onboard:
        ui.render_step(
            "Semantic memory", "Prefetching embedding model (one-time download)..."
        )
        from silex_core.ops.prefetch import prefetch_embedding_model

        prefetch_msg = prefetch_embedding_model()
        if prefetch_msg:
            ui.render_step("Semantic memory", prefetch_msg)
            await asyncio.sleep(0.5)

    if onboard:
        ui.render_step(
            "You're ready",
            "Next steps:\n\n"
            "  kinthic                      — interactive terminal agent\n"
            "  kinthic daemon install       — 24/7 service (survives reboot)\n"
            "  kinthic channels telegram run — messaging bot (if paired)\n"
            "  kinthic skills list          — browse installed skills\n"
            "  kinthic mcp list             — MCP client integrations\n"
            "  kinthic mcp print-config     — connect Claude/Cursor to Silex memory\n"
            "  kinthic data backup          — export ~/.kinthic (restore with data restore)",
            subtitle="Run kinthic doctor --ping anytime to verify connectivity",
        )
    else:
        greeting = persona_data.get(
            "custom_greeting",
            "🧠 SILEX memory core active. Kinthic CLI operational. Systems are 100% green.",
        )
        ui.render_step(
            "Activation Complete",
            f"Kinthic cognitive core is now active.\n\n  {greeting}",
            subtitle="Run 'kinthic init' for the full first-run path, or 'kinthic' to start",
        )
    ui.prompt("Press Enter to exit")
    ui.clear()


async def _onboard_enable_mcp_preset(ui, preset_name: str) -> None:
    """Write mcp.yaml preset and run a connectivity test."""
    from silex_core.mcp.presets import get_preset
    from silex_core.mcp.config import write_server
    from silex_core.mcp.manager import get_mcp_manager

    preset = get_preset(preset_name)
    if not preset:
        ui.render_step("MCP", f"Unknown preset: {preset_name}")
        return
    preset = dict(preset)
    preset["enabled"] = True
    write_server(preset_name, preset)
    ui.render_step("MCP", f"Testing {preset_name} MCP server...")
    ok, msg = await get_mcp_manager().test_server(preset_name)
    status = "✓" if ok else "✗"
    ui.render_step("MCP", f"{status} {preset_name}: {msg}")


def run_onboard() -> None:
    asyncio.run(run_interactive_setup(onboard=True))


def run_setup() -> None:
    run_onboard()


def run_doctor(*, ping: bool = False) -> None:
    store = RuntimeSettingsStore()
    settings = store.load_settings()
    status = store.setup_status()

    provider_label = status["provider"]
    if status["provider"] == "custom":
        provider_label = f"Custom ({settings.get('custom_label', 'Unknown')})"

    print("\nKinthic doctor\n")
    if not status["setup_completed"]:
        print("Setup complete: False  ← expected before first run of `kinthic init`")
        print("Next step: run `kinthic init` to configure your provider and skills.\n")
    else:
        print(f"Setup complete: {status['setup_completed']}")
    p_val = provider_label if provider_label else "None (Not Configured)"
    m_val = status['model'] if status['model'] else "None (Not Configured)"
    print(f"Provider: {p_val}")
    print(f"Model: {m_val}")
    print(f"Provider key configured: {status['provider_configured']}")
    print(f"Web API key configured: {status['web_api_key_configured']}")

    from silex_core.utils.config import get_search_secret

    has_tavily = bool(get_search_secret("tavily", settings_store=store))
    has_brave = bool(get_search_secret("brave", settings_store=store))
    print(f"Tavily Search API Key configured: {has_tavily}")
    print(f"Brave Search API Key configured: {has_brave}")

    print(f"Paired Telegram users: {status['paired_telegram_users']}")
    print(
        f"Approvals required: {settings.get('security', {}).get('require_tool_approvals', True)}"
    )
    print(f"Browser actions enabled: {browser_actions_enabled()}")
    terminal_enabled = terminal_execution_enabled()
    code_enabled = code_apply_enabled()
    print(f"Terminal execution enabled: {terminal_enabled}")
    print(f"Direct code apply enabled: {code_enabled}")

    import os

    public_mode = os.environ.get("TELEGRAM_PUBLIC_MODE", "false").lower() == "true"
    print(f"Telegram Public Mode: {public_mode}")

    warnings = []
    if public_mode and (terminal_enabled or code_enabled):
        warnings.append(
            "⚠️ RISKY CONFIG: Telegram Public Mode is ON while Terminal/Code Apply is enabled. Unpaired users could execute arbitrary code!"
        )
    if not settings.get("security", {}).get("require_tool_approvals", True):
        warnings.append(
            "⚠️ RISKY CONFIG: require_tool_approvals is FALSE. The agent can take irreversible actions without operator consent."
        )

    if warnings:
        print("\n--- SECURITY WARNINGS ---")
        for w in warnings:
            print(w)
        print("-------------------------\n")

    try:
        from silex_core.mcp.manager import get_mcp_manager
        from silex_core.mcp.config import load_mcp_config

        mcp_cfg = load_mcp_config()
        enabled = [n for n, s in mcp_cfg.servers.items() if s.get("enabled", True)]
        print(
            f"MCP servers configured: {len(mcp_cfg.servers)} ({len(enabled)} enabled)"
        )
        for line in get_mcp_manager().status_report():
            print(line)
    except Exception as exc:
        print(f"MCP status unavailable: {exc}")

    from silex_core.utils.config import KINTHIC_BACKUPS, KINTHIC_HOME

    print(f"Kinthic data home: {KINTHIC_HOME}")
    print(
        "Backup/restore: kinthic data backup | kinthic data restore <archive> [--apply]"
    )
    print(f"Pre-restore safety backups: {KINTHIC_BACKUPS}")

    warnings = []
    if os.name == "nt":
        warnings.append(
            "Windows detected: ~/.kinthic/secrets.json has no OS-level file permission protection. (Prefer Env Vars)"
        )

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"- {warning}")

    try:
        import importlib.util

        if browser_actions_enabled() and importlib.util.find_spec("playwright") is None:
            print("\nWarnings:")
            print(
                "- Browser tools are enabled but playwright is not installed. Run: pip install 'kinthic[browser]'"
            )
    except Exception:
        pass

    if ping:
        import asyncio
        from silex_core.llm.provider_test import ping_provider
        from silex_core.utils.config import get_provider_secret

        provider = str(
            settings.get("provider", "") or status.get("provider") or "gemini"
        ).strip()
        model = settings.get("model")
        key = (get_provider_secret(provider, settings_store=store) or "").strip()
        if provider != "ollama" and not key:
            print("\nLive provider check skipped: no API key stored.")
        else:
            print("\nLive provider check...")
            base_url = settings.get("base_url")
            result = asyncio.run(ping_provider(provider, key, model, base_url=base_url))
            print(f"  [{'ok' if result.get('ok') else 'fail'}] {result.get('message')}")


def run_models() -> None:
    print("\nKinthic supported providers\n")
    for provider in list_providers():
        print(f"{provider.display_name} ({provider.name})")
        for model in provider.fetch_models():
            tier = f" [{model.get('tier')}]" if model.get("tier") else ""
            print(f"  - {model['label']} :: {model['id']}{tier}")
        print()


def run_telegram() -> None:
    from silex_core.adapters.telegram import TelegramAdapter

    TelegramAdapter().run()


def run_discord() -> None:
    from silex_core.adapters.discord import DiscordAdapter

    DiscordAdapter().run()


def _run_export_trajectories(args) -> None:
    """Async wrapper for trajectory export called from CLI."""
    import asyncio
    from pathlib import Path
    from silex_engine.storage.database import Database
    from silex_core.utils.config import SILEX_DB
    from silex_core.autonomy.export import export_trajectories

    fmt = getattr(args, "format", "grpo")
    out = getattr(args, "output", None)
    s_only = getattr(args, "success_only", False)
    since = getattr(args, "since", None)
    until = getattr(args, "until", None)
    max_t = getattr(args, "max_traj", 10_000)

    async def _run() -> None:
        db = Database(str(SILEX_DB))
        await db.connect()
        try:
            records, path = await export_trajectories(
                db,
                format=fmt,
                output_path=Path(out) if out else None,
                success_only=s_only,
                since=since,
                until=until,
                max_trajectories=max_t,
            )
            if path:
                print(
                    f"\n✅  Exported {len(records)} trajectories ({fmt.upper()}) → {path}"
                )
            else:
                print("\n⚠️  No trajectories matched the filter criteria.")
        finally:
            await db.close()

    asyncio.run(_run())


def generate_pair_code() -> None:
    store = RuntimeSettingsStore()
    code = store.create_pair_code()
    print(f"\nTelegram pairing code: {code}")


def run_skills(command: str, name: str | None = None) -> None:
    from silex_core.plugins.registry import get_registry
    from silex_core.skills.loader import SkillLoader

    registry = get_registry()
    loader = SkillLoader()

    if command == "list":
        entries = registry.get_all(type_filter="skill")
        print("\nKinthic skills (catalog)\n")
        print(registry.format_list(entries))
        count = loader.load_all()
        print(f"\nLoaded locally: {count} skill(s)\n")
        for row in loader.list_skills_detailed():
            trigger = f" | trigger: {row['trigger']}" if row.get("trigger") else ""
            print(
                f"  [{row['trust_level']}] {row['name']} ({row.get('source', 'user')})"
                f"{trigger}\n    {row['description']}"
            )
    elif command == "search":
        results = registry.search(name or "", type_filter="skill")
        print(registry.format_list(results))
    elif command == "install":
        ok, msg = registry.install(name or "")
        if ok:
            loader.load_all()
        print(msg if ok else f"Failed: {msg}")
    elif command == "uninstall":
        ok, msg = registry.uninstall(name or "")
        if ok:
            loader.load_all()
        print(msg if ok else f"Failed: {msg}")
    elif command == "show":
        loader.load_all()
        body = loader.get_skill_body(name or "")
        if body is None:
            print(f"Skill '{name}' not loaded.")
            return
        meta = loader.skill_meta.get(name or "")
        if meta and meta.trigger:
            print(f"# {name}\nTrigger: {meta.trigger}\n")
        print(body)
    elif command == "refresh":
        ok, msg = registry.refresh_from_remote()
        print(msg if ok else f"Failed: {msg}")
    elif command == "reload":
        count = loader.load_all()
        print(f"Reloaded {count} skill(s) from ~/.kinthic/skills/")


def run_benchmark_recall(
    *,
    seed: int = 42,
    noise: int | None = None,
    conditions: list[str] | None = None,
    output: str | None = None,
    report: str | None = None,
    track: str = "retrieval",
) -> None:
    import asyncio
    from pathlib import Path

    from benchmarks.memory_recall.harness import run_benchmark, run_mcp_benchmark

    runner = run_mcp_benchmark if track == "mcp" else run_benchmark
    payload = asyncio.run(
        runner(
            seed=seed,
            noise_count=noise,
            conditions=conditions,
            output_json=Path(output) if output else None,
            output_md=Path(report) if report else None,
        )
    )
    hybrid = None
    for cond in payload.get("conditions", []):
        if cond["name"] == "aged_21d":
            hybrid = cond["baselines"].get("hybrid", {})
            break
    if hybrid:
        print(
            f"\naged_21d hybrid — Hit@5: {hybrid.get('hit_at_5', 0):.1%} | "
            f"Hit@12: {hybrid.get('hit_at_12', 0):.1%} | MRR: {hybrid.get('mrr', 0):.3f}"
        )
    print("Full report: benchmarks/memory_recall/results/REPORT.md")


def run_mcp(command: str, name: str | None = None, **kwargs) -> None:
    from silex_core.mcp.config import load_mcp_config, write_server, set_server_enabled
    from silex_core.mcp.presets import get_preset
    from silex_core.mcp.manager import get_mcp_manager

    mgr = get_mcp_manager()
    if command == "list":
        cfg = load_mcp_config()
        print("\nMCP servers (~/.kinthic/config/mcp.yaml)\n")
        if not cfg.servers:
            print("  (none — run: kinthic mcp add filesystem --preset filesystem)")
        for srv_name, srv in cfg.servers.items():
            state = "enabled" if srv.get("enabled", True) else "disabled"
            desc = srv.get("description", "")
            print(f"  {srv_name}: {state} — {desc}")
        print()
        for line in mgr.status_report():
            print(line)
    elif command == "add":
        preset = kwargs.get("preset")
        cmd = kwargs.get("command")
        args = kwargs.get("args") or []
        if preset:
            preset_cfg = get_preset(preset)
            if not preset_cfg:
                print(f"Unknown preset: {preset}")
                return
            write_server(name or preset, dict(preset_cfg))
            print(f"Added MCP server '{name or preset}' from preset '{preset}'")
        elif cmd:
            write_server(
                name or "custom", {"command": cmd, "args": args, "enabled": False}
            )
            print(f"Added MCP server '{name or 'custom'}'")
        else:
            print("Use --preset or --command")
    elif command == "enable":
        if set_server_enabled(name or "", True):
            print(f"Enabled MCP server '{name}'")
        else:
            print(f"Server '{name}' not found")
    elif command == "disable":
        if set_server_enabled(name or "", False):
            print(f"Disabled MCP server '{name}'")
        else:
            print(f"Server '{name}' not found")
    elif command == "test":
        ok, msg = asyncio.run(mgr.test_server(name or ""))
        print(f"[{'ok' if ok else 'fail'}] {msg}")
    elif command == "tools":
        tools = asyncio.run(mgr.discover_tools())
        server_filter = kwargs.get("server")
        for tool in tools:
            if server_filter and tool.server_name != server_filter:
                continue
            print(f"  {tool.name}: {tool.description[:80]}")
    elif command == "serve":
        if kwargs.get("stdio"):
            from silex_core.mcp.server.stdio_bridge import run_stdio_bridge

            run_stdio_bridge()
        else:
            print(
                "Use --stdio for Claude Desktop / Cursor, or connect via HTTP when daemon is running:"
            )
            from silex_core.utils.config import gateway_host, gateway_port

            print(f"  http://{gateway_host()}:{gateway_port()}/mcp")
    elif command == "print-config":
        from silex_core.mcp.server.print_config import print_config

        print_config(kwargs.get("client", "claude"))


def run_usage() -> None:
    from silex_engine.storage.database import Database
    from silex_core.runtime.usage import UsageTracker
    from silex_core.utils.config import SILEX_DB

    async def _run():
        db = Database(str(SILEX_DB))
        await db.connect()
        try:
            tracker = UsageTracker(db)
            summary = await tracker.summary()

            totals = summary.get("totals", {})
            models = summary.get("models", [])

            print("\n📊 Usage & Cost Report\n")
            print(f"Total Requests: {totals.get('requests', 0)}")
            print(f"Total Tokens In: {totals.get('input_tokens', 0):,}")
            print(f"Total Tokens Out: {totals.get('output_tokens', 0):,}")
            print(f"Estimated Cost: ${totals.get('estimated_cost_usd', 0.0):.4f}\n")

            if models:
                print("Top Models:")
                for m in models:
                    print(f"  {m['model']} (${m.get('estimated_cost_usd', 0.0):.4f})")
            print()
        finally:
            await db.close()

    asyncio.run(_run())


def run_backup(command: str, output: str) -> None:
    if command == "export":
        from silex_core.ops.backup import export_backup

        export_backup(output)
    else:
        print("Usage: kinthic data backup [--output filename.zip]")


def run_restore(archive: str, *, apply: bool, pre_backup: bool) -> None:
    from silex_core.ops.backup import print_restore_summary, restore_backup

    summary = restore_backup(archive, apply=apply, pre_backup=pre_backup)
    print_restore_summary(summary, apply=apply)
    if summary.get("errors"):
        raise SystemExit(1)


def run_migrate(command: str, source: str, path: str | None, dry_run: bool) -> None:
    if source == "hermes":
        from silex_core.migrate.hermes import scan_hermes, import_hermes

        if command == "scan":
            report = scan_hermes(path)
            print("Hermes Migration Scan Report:")
            import json

            print(json.dumps(report, indent=2))
        elif command == "import":
            logs = import_hermes(path, dry_run=dry_run)
            print("\n".join(logs))
    elif source == "openclaw":
        from silex_core.migrate.openclaw import scan_openclaw, import_openclaw

        if command == "scan":
            report = scan_openclaw(path)
            print("OpenClaw Migration Scan Report:")
            import json

            print(json.dumps(report, indent=2))
        elif command == "import":
            logs = import_openclaw(path, dry_run=dry_run)
            print("\n".join(logs))
    else:
        print("Unknown source for migration.")


def run_start() -> None:
    import subprocess
    import sys
    import os
    import json
    import time
    from silex_core.utils.config import KINTHIC_DAEMON_LOCK

    if KINTHIC_DAEMON_LOCK.exists():
        try:
            lock_data = json.loads(
                KINTHIC_DAEMON_LOCK.read_text(encoding="utf-8").strip()
            )
            pid = lock_data.get("pid")
            if pid:
                os.kill(pid, 0)
                print(f"Kinthic daemon is already running (PID {pid}).")
                return
        except Exception:
            pass

    # Prefer systemd/LaunchAgent when the service unit is installed.
    try:
        from silex_core.ops.service import is_service_installed, start_service

        if is_service_installed():
            ok, msg = start_service()
            print(msg)
            if ok:
                return
    except Exception:
        pass

    print("Starting Kinthic daemon in the background...")
    daemon_argv = [sys.executable, sys.argv[0], "daemon", "run"]

    if os.name == "nt":
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(daemon_argv, creationflags=CREATE_NO_WINDOW)
    else:
        subprocess.Popen(
            daemon_argv,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # Wait briefly for the lockfile — the child should create it almost immediately.
    for _ in range(30):
        if KINTHIC_DAEMON_LOCK.exists():
            try:
                lock_data = json.loads(
                    KINTHIC_DAEMON_LOCK.read_text(encoding="utf-8").strip()
                )
                pid = lock_data.get("pid")
                if pid:
                    os.kill(pid, 0)
                    print(f"Daemon started (PID {pid}).")
                    return
            except Exception:
                pass
        time.sleep(0.1)

    print(
        "Error: daemon process did not start (no lockfile after 3s). "
        "Run 'kinthic daemon run' in the foreground to see the error."
    )


def run_stop() -> None:
    import json
    import signal
    from silex_core.utils.config import KINTHIC_DAEMON_LOCK

    lock_path = KINTHIC_DAEMON_LOCK
    if not lock_path.exists():
        print("Kinthic is not running (no daemon.lock found).")
        return
    try:
        lock_data = json.loads(lock_path.read_text(encoding="utf-8").strip())
        pid = lock_data.get("pid")
    except Exception:
        print("Corrupted daemon.lock. Removing.")
        lock_path.unlink(missing_ok=True)
        return

    try:
        from silex_core.ops.service import is_service_installed, stop_service

        if is_service_installed():
            ok, msg = stop_service()
            if ok:
                print(msg)
                lock_path.unlink(missing_ok=True)
                return
    except Exception:
        pass

    try:
        os.kill(pid, 0)  # existence check
    except OSError:
        print("No running process. Cleaning up stale daemon.lock.")
        lock_path.unlink(missing_ok=True)
        return

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Stopped Kinthic (PID {pid}).")
    except OSError as e:
        print(f"Failed to stop Kinthic: {e}")
    lock_path.unlink(missing_ok=True)


def run_proposals(command: str, proposal_id: str | None = None) -> None:
    print("Meta reasoning is disabled.")


def run_web() -> None:
    import subprocess
    import sys
    import os
    from silex_core.utils.config import PROJECT_ROOT, gateway_host, gateway_port
    from silex_core.runtime.settings import RuntimeSettingsStore

    dashboard_path = PROJECT_ROOT / "kinthic-dashboard"
    if not dashboard_path.exists():
        print(
            "Dashboard is not bundled in this install (dev checkout only).\n"
            "On a server, run:\n"
            "  kinthic daemon install\n"
            f"  ssh -N -L {gateway_port()}:{gateway_host()}:{gateway_port()} user@your-host\n"
            f"Then open http://127.0.0.1:{gateway_port()}/api/health"
        )
        return

    # Auto-provision (or reuse) the local web API key and hand it to the
    # Next.js dev server so the dashboard can authenticate to the gateway
    # without any manual setup step.
    api_key = RuntimeSettingsStore().ensure_web_api_key()
    api_base = f"http://{gateway_host()}:{gateway_port()}"

    print("Starting Kinthic Dashboard (Backend + Frontend)...")
    api_proc = None
    ui_proc = None
    try:
        api_proc = subprocess.Popen(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "dashboard_api.py")]
        )
        npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
        ui_env = {
            **os.environ,
            "NEXT_PUBLIC_KINTHIC_API_KEY": api_key,
            "NEXT_PUBLIC_KINTHIC_API_BASE": api_base,
        }
        ui_proc = subprocess.Popen(
            [npm_cmd, "run", "dev"], cwd=str(dashboard_path), env=ui_env
        )

        print(f"\n[+] Dashboard is running against {api_base} (Press Ctrl+C to stop).")
        ui_proc.wait()
    except KeyboardInterrupt:
        print("\nStopping dashboard...")
    finally:
        if api_proc:
            api_proc.terminate()
        if ui_proc:
            ui_proc.terminate()


def run_daemon_status() -> None:
    import json
    import os
    from silex_core.utils.config import KINTHIC_DAEMON_LOCK

    lock_path = KINTHIC_DAEMON_LOCK
    if not lock_path.exists():
        print("Kinthic daemon is NOT running.")
        return
    try:
        lock_data = json.loads(lock_path.read_text(encoding="utf-8").strip())
        pid = lock_data.get("pid")
        if pid:
            os.kill(pid, 0)
            print(f"Kinthic daemon is RUNNING (PID {pid}).")
            return
    except OSError:
        pass
    except Exception:
        pass
    print("Kinthic daemon is NOT running (stale lockfile).")
    lock_path.unlink(missing_ok=True)


def run_daemon_logs() -> None:
    from silex_core.utils.config import KINTHIC_DAEMON_LOG
    import subprocess
    import os

    if not KINTHIC_DAEMON_LOG.exists():
        print("No daemon logs found.")
        return
    print(f"Tailing {KINTHIC_DAEMON_LOG}...")
    if os.name == "nt":
        subprocess.run(
            ["powershell", "-c", f"Get-Content '{KINTHIC_DAEMON_LOG}' -Wait"]
        )
    else:
        subprocess.run(["tail", "-f", str(KINTHIC_DAEMON_LOG)])


def run_daemon_foreground() -> None:
    import json
    import os
    from silex_core.utils.config import KINTHIC_DAEMON_LOCK

    lock_path = KINTHIC_DAEMON_LOCK
    if lock_path.exists():
        try:
            lock_data = json.loads(lock_path.read_text(encoding="utf-8").strip())
            pid = lock_data.get("pid")
            if pid:
                os.kill(pid, 0)
                print(f"Kinthic daemon is already running (PID {pid}).")
                return
        except OSError:
            lock_path.unlink(missing_ok=True)
        except Exception:
            lock_path.unlink(missing_ok=True)

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")

    def setup_daemon_logging():
        from silex_core.utils.config import KINTHIC_DAEMON_LOG
        import os

        if (
            KINTHIC_DAEMON_LOG.exists()
            and KINTHIC_DAEMON_LOG.stat().st_size > 10 * 1024 * 1024
        ):
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
        log_file = open(KINTHIC_DAEMON_LOG, "a", buffering=1, encoding="utf-8")
        try:
            os.dup2(log_file.fileno(), 1)
            os.dup2(log_file.fileno(), 2)
        except Exception:
            pass

    setup_daemon_logging()
    try:
        from scripts.daemon import main as daemon_main

        daemon_main()
    finally:
        lock_path.unlink(missing_ok=True)


def run_observe() -> None:
    import sqlite3
    import sys
    from silex_core.utils.config import SILEX_DB

    db_path = SILEX_DB
    if not db_path.exists():
        print("\n[!] No active Silex memory graph found.")
        print(f"    (Database not found at {db_path})\n")
        sys.exit(1)

    print("\n\033[1;36m🧠 SILEX EPISTEMIC TOPOLOGY\033[0m")
    print("\033[90m==================================================\033[0m")

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT node_id, type, content, status FROM epistemic_nodes")
        nodes = cursor.fetchall()
        
        cursor.execute("SELECT source_node_id, target_node_id, relation_type FROM epistemic_edges")
        edges = cursor.fetchall()

        if not nodes:
            print("  [Graph is empty. No nodes found.]")
        else:
            node_map = {n["node_id"]: n for n in nodes}
            for n in nodes:
                nid = n["node_id"]
                ctype = n["type"].upper()
                content = n["content"][:60].replace("\n", " ")
                print(f"\n\033[1;37m[{ctype}]\033[0m {content}")
                
                out_edges = [e for e in edges if e["source_node_id"] == nid]
                for e in out_edges:
                    target_nid = e["target_node_id"]
                    target_node = node_map.get(target_nid)
                    if target_node:
                        rel = e["relation_type"]
                        t_content = target_node["content"][:40].replace("\n", " ")
                        t_type = target_node["type"].upper()
                        print(f"   \033[90m└──({rel})──>\033[0m [{t_type}] {t_content}")

        print("\n\033[90m==================================================\033[0m")
        print(f"  Total Nodes: {len(nodes)}  |  Total Edges: {len(edges)}\n")

    except Exception as e:
        print(f"\n[!] Failed to read graph: {e}")


def main() -> None:
    import sys

    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        from scripts.run import main as run_main

        run_main()
        return

    if args.command in ("init", "innit", "onboard", "setup"):
        run_onboard()
    elif args.command == "doctor":
        run_doctor(ping=getattr(args, "ping", False))
    elif args.command == "models":
        run_models()
    elif args.command == "web":
        run_web()
    elif args.command == "usage":
        run_usage()
    elif args.command == "observe":
        run_observe()
    elif args.command == "daemon":
        if args.daemon_command == "start":
            run_start()
        elif args.daemon_command == "stop":
            run_stop()
        elif args.daemon_command == "status":
            run_daemon_status()
        elif args.daemon_command == "logs":
            run_daemon_logs()
        elif args.daemon_command == "run":
            run_daemon_foreground()
        elif args.daemon_command == "install":
            from silex_core.ops.service import install_service

            ok, msg = install_service(force=getattr(args, "force", False))
            print(msg)
            if not ok:
                sys.exit(1)
        elif args.daemon_command == "uninstall":
            from silex_core.ops.service import uninstall_service

            ok, msg = uninstall_service()
            print(msg)
            if not ok:
                sys.exit(1)
        else:
            print("Unknown daemon command")
    elif args.command == "data":
        if args.data_command == "backup":
            run_backup("export", getattr(args, "output", "kinthic-backup.zip"))
        elif args.data_command == "restore":
            apply = bool(getattr(args, "apply", False))
            dry_run = bool(getattr(args, "dry_run", False))
            if apply and dry_run:
                print("Use either --dry-run or --apply, not both.")
                raise SystemExit(1)
            if not apply and not dry_run:
                dry_run = True
            run_restore(
                getattr(args, "archive"),
                apply=apply,
                pre_backup=not getattr(args, "no_pre_backup", False),
            )
        elif args.data_command == "export":
            _run_export_trajectories(args)
        elif args.data_command == "migrate":
            source = getattr(args, "source", "")
            path = getattr(args, "path", None)
            if getattr(args, "scan_only", False) or (
                not getattr(args, "dry_run", False)
                and not getattr(args, "apply", False)
            ):
                run_migrate("scan", source, path, True)
            elif getattr(args, "apply", False):
                run_migrate("import", source, path, False)
            else:
                run_migrate("import", source, path, True)
        else:
            print("Unknown data command")
    elif args.command == "channels":
        if args.channel_app == "telegram":
            if getattr(args, "channel_cmd", None) == "pair":
                generate_pair_code()
            else:
                run_telegram()
        elif args.channel_app == "discord":
            run_discord()
    elif args.command == "proposals":
        run_proposals(
            getattr(args, "proposals_command", "list"),
            getattr(args, "proposal_id", None),
        )
    elif args.command == "skills":
        run_skills(
            getattr(args, "skills_command", "list") or "list",
            getattr(args, "name", None) or getattr(args, "query", None),
        )
    elif args.command == "mcp":
        run_mcp(
            getattr(args, "mcp_command", "list") or "list",
            getattr(args, "name", None),
            preset=getattr(args, "preset", None),
            command=getattr(args, "mcp_exec", None),
            args=getattr(args, "mcp_args", None),
            server=getattr(args, "server", None),
            stdio=getattr(args, "stdio", False),
            client=getattr(args, "client", "claude"),
        )
    elif args.command == "benchmark":
        cmd = getattr(args, "benchmark_command", None) or "recall"
        if cmd == "recall":
            run_benchmark_recall(
                seed=getattr(args, "seed", 42),
                noise=getattr(args, "noise", None),
                conditions=getattr(args, "conditions", None),
                output=getattr(args, "output", None),
                report=getattr(args, "report", None),
                track=getattr(args, "track", "retrieval"),
            )
        else:
            print(f"Unknown benchmark command: {cmd}")


if __name__ == "__main__":
    main()
