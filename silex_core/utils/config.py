"""
Configuration loader for Kinthic.

Reads from .env file and provides typed access to all settings.
All runtime data lives under ~/.kinthic/
"""

from __future__ import annotations

import os
import shutil
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from silex_core.runtime.settings import RuntimeSettingsStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
KINTHIC_HOME = Path.home() / ".kinthic"

# Auto-load environment variables from ~/.kinthic/.env if present
_env_file = KINTHIC_HOME / ".env"
if _env_file.exists():
    load_dotenv(_env_file)
else:
    load_dotenv()
SILEX_DB = KINTHIC_HOME / "storage" / "silex.db"
KINTHIC_CONFIG = KINTHIC_HOME / "config" / "rules.json"
KINTHIC_SECRETS = KINTHIC_HOME / "config" / "secrets.json"
KINTHIC_WORKSPACE = KINTHIC_HOME / "workspace"
SILEX_VECTOR_DB = KINTHIC_HOME / "storage" / "vector_db"
KINTHIC_SKILLS = KINTHIC_HOME / "skills"
KINTHIC_LOGS = KINTHIC_HOME / "logs"
KINTHIC_DAEMON_LOG = KINTHIC_HOME / "logs" / "daemon.log"
KINTHIC_PHANTOM = KINTHIC_HOME / "runtime" / ".phantom"
KINTHIC_DAEMON_LOCK = KINTHIC_HOME / "runtime" / "daemon.lock"
KINTHIC_MANIFEST = KINTHIC_HOME / "workspace" / "workspace_index_manifest.json"
KINTHIC_PROCESS_LOCK = KINTHIC_HOME / "runtime" / "process.lock"
KINTHIC_ONTOLOGY = KINTHIC_HOME / "storage" / "ontology.json"
KINTHIC_EXPORTS = KINTHIC_HOME / "workspace" / "exports"
KINTHIC_TRACES = KINTHIC_HOME / "logs" / "traces"
KINTHIC_PENDING_EDITS = KINTHIC_HOME / "workspace" / "pending_edits.json"
KINTHIC_BACKUPS = KINTHIC_HOME / "workspace" / "backups"
KINTHIC_PLUGINS_PROVIDERS = KINTHIC_HOME / "config" / "plugins" / "model-providers"
KINTHIC_PLUGINS_TOOLS = KINTHIC_HOME / "plugins" / "tools"
KINTHIC_PLUGINS_SKILLS = KINTHIC_HOME / "plugins" / "skills"
KINTHIC_PERSONA = KINTHIC_HOME / "config" / "persona.yaml"
KINTHIC_HMAC_KEY = KINTHIC_HOME / "config" / "hmac_key.bin"


# Legacy aliases kept so existing imports don't break
DATA_DIR = KINTHIC_HOME
DB_PATH = SILEX_DB


# WORKSPACE: KINTHIC_WORKSPACE env > SILEX_WORKSPACE env (backwards compat) > ~/.kinthic/workspace
_workspace_env = (
    os.getenv("KINTHIC_WORKSPACE")
    or os.getenv("SILEX_WORKSPACE")
    or os.getenv("KINTHIC_WORKSPACE")
    or os.getenv("ARIA_WORKSPACE")
)
if _workspace_env:
    WORKSPACE_DIR = Path(_workspace_env).resolve()
    if not str(WORKSPACE_DIR).startswith(str(KINTHIC_WORKSPACE)):
        logging.getLogger("kinthic.init").warning(
            f"SECURITY WARNING: Workspace directory resolved to {WORKSPACE_DIR} outside {KINTHIC_WORKSPACE}"
        )
else:
    # Development fallback: default to the repository root if running from a git clone
    if (PROJECT_ROOT / ".git").exists():
        WORKSPACE_DIR = PROJECT_ROOT
    else:
        WORKSPACE_DIR = KINTHIC_WORKSPACE

KINTHIC_DIRECTIVES_FILE = WORKSPACE_DIR / "kinthic_core_directives.md"

_kinthic_home_ensured = False


def ensure_kinthic_home() -> None:
    global _kinthic_home_ensured
    if _kinthic_home_ensured:
        return
    _kinthic_home_ensured = True

    log = logging.getLogger("kinthic.init")

    # 1. Create base directory structure first
    for path in [
        KINTHIC_HOME,
        KINTHIC_HOME / "storage",
        KINTHIC_HOME / "config",
        KINTHIC_HOME / "workspace",
        KINTHIC_HOME / "runtime",
        KINTHIC_HOME / "logs",
        KINTHIC_SKILLS,
    ]:
        try:
            path.mkdir(exist_ok=True, parents=True)
        except Exception:
            pass

    # 2. Automatic migration from ~/.vyn to ~/.kinthic
    legacy_vyn_home = Path.home() / ".vyn"
    if (
        legacy_vyn_home.exists()
        and not (KINTHIC_HOME / "storage" / "silex.db").exists()
    ):
        try:
            # Copy all files from ~/.vyn to ~/.kinthic/ config/storage folders
            for item in legacy_vyn_home.iterdir():
                if item.name == "vyn.db":
                    shutil.copy2(item, SILEX_DB)
                elif item.name == "vyn.db-wal":
                    shutil.copy2(item, KINTHIC_HOME / "storage" / "silex.db-wal")
                elif item.name == "vyn.db-shm":
                    shutil.copy2(item, KINTHIC_HOME / "storage" / "silex.db-shm")
                elif item.name == "ontology.json":
                    shutil.copy2(item, KINTHIC_ONTOLOGY)
                elif item.name in ("config.json", "settings.json"):
                    shutil.copy2(item, KINTHIC_CONFIG)
                elif item.name == "secrets.json":
                    shutil.copy2(item, KINTHIC_SECRETS)
                elif item.name == "persona.yaml":
                    shutil.copy2(item, KINTHIC_PERSONA)
                elif item.name == "vector_db" or item.name == "memory":
                    src_v = item / "vector_db" if item.name == "memory" else item
                    if src_v.exists():
                        shutil.copytree(src_v, SILEX_VECTOR_DB, dirs_exist_ok=True)
                elif item.is_dir():
                    # Generic copy fallback
                    dest_dir = (
                        KINTHIC_HOME / "config"
                        if item.name == "plugins"
                        else KINTHIC_HOME / "workspace" / item.name
                    )
                    shutil.copytree(item, dest_dir, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, KINTHIC_HOME / "config" / item.name)
            log.info(
                "✓ Successfully migrated existing profile from ~/.vyn to new ~/.kinthic layout"
            )
        except Exception as e:
            log.error(f"Failed to migrate legacy ~/.vyn to ~/.kinthic: {e}")

    # 3. Internal migrations from legacy flat ~/.kinthic folder to structured layout
    def safe_is_empty_dir(path: Path) -> bool:
        if not path.exists():
            return True
        try:
            return not any(path.iterdir())
        except Exception:
            return True

    def safe_migrate_file(old_path: Path, new_path: Path) -> None:
        if old_path.exists() and not new_path.exists():
            try:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                old_path.rename(new_path)
                log.info(f"Migrated file {old_path.name} to {new_path}")
            except Exception as e:
                log.error(f"Failed to migrate file {old_path.name}: {e}")

    def safe_migrate_dir(old_path: Path, new_path: Path) -> None:
        if old_path.exists() and old_path.is_dir() and not new_path.exists():
            try:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_path), str(new_path))
                log.info(f"Migrated directory {old_path.name} to {new_path}")
            except Exception as e:
                log.error(f"Failed to migrate directory {old_path.name}: {e}")

    # Relocate SQLite files
    safe_migrate_file(KINTHIC_HOME / "silex.db", SILEX_DB)
    safe_migrate_file(
        KINTHIC_HOME / "silex.db-wal", KINTHIC_HOME / "storage" / "silex.db-wal"
    )
    safe_migrate_file(
        KINTHIC_HOME / "silex.db-shm", KINTHIC_HOME / "storage" / "silex.db-shm"
    )
    safe_migrate_file(KINTHIC_HOME / "ontology.json", KINTHIC_ONTOLOGY)

    # Relocate configuration files
    safe_migrate_file(KINTHIC_HOME / "config.json", KINTHIC_CONFIG)
    safe_migrate_file(KINTHIC_HOME / "secrets.json", KINTHIC_SECRETS)
    safe_migrate_file(KINTHIC_HOME / "persona.yaml", KINTHIC_PERSONA)

    # Relocate workspace metadata
    safe_migrate_file(KINTHIC_HOME / "workspace_index_manifest.json", KINTHIC_MANIFEST)
    safe_migrate_file(KINTHIC_HOME / "pending_edits.json", KINTHIC_PENDING_EDITS)

    # Relocate folders
    safe_migrate_dir(KINTHIC_HOME / "memory" / "vector_db", SILEX_VECTOR_DB)
    safe_migrate_dir(KINTHIC_HOME / "vector_db", SILEX_VECTOR_DB)
    if (KINTHIC_HOME / "memory").exists() and safe_is_empty_dir(KINTHIC_HOME / "memory"):
        try:
            (KINTHIC_HOME / "memory").rmdir()
        except OSError:
            pass

    safe_migrate_dir(KINTHIC_HOME / "plugins", KINTHIC_HOME / "config" / "plugins")
    safe_migrate_dir(KINTHIC_HOME / "exports", KINTHIC_EXPORTS)
    safe_migrate_dir(KINTHIC_HOME / "backups", KINTHIC_BACKUPS)
    safe_migrate_dir(KINTHIC_HOME / "traces", KINTHIC_TRACES)

    # 4. Ensure all directories are created
    for path in [
        SILEX_VECTOR_DB,
        KINTHIC_SKILLS,
        KINTHIC_LOGS,
        KINTHIC_PLUGINS_TOOLS,
        KINTHIC_PLUGINS_SKILLS,
        KINTHIC_TRACES,
        KINTHIC_BACKUPS,
        KINTHIC_PLUGINS_PROVIDERS,
    ]:
        try:
            path.mkdir(exist_ok=True, parents=True)
        except Exception:
            pass

    # 5. Skills README + seed bundled skills from the package checkout
    readme_path = KINTHIC_SKILLS / "README.md"
    if safe_is_empty_dir(KINTHIC_SKILLS) or not readme_path.exists():
        try:
            readme_path.write_text(
                "Add .md files to this directory to extend Kinthic with new skills.\n"
                "Each file should describe a workflow or capability.\n"
                "Restart Kinthic after adding a skill for it to take effect.\n",
                encoding="utf-8",
            )
        except Exception as exc:
            log.warning("Could not write skills README (non-fatal): %s", exc)

    bundled_skills_dir = PROJECT_ROOT / "skills"
    if bundled_skills_dir.is_dir():
        for src in bundled_skills_dir.glob("*.md"):
            if src.stem.lower() == "readme":
                continue
            dest = KINTHIC_SKILLS / src.name
            if not dest.exists():
                try:
                    shutil.copy2(src, dest)
                except OSError as exc:
                    log.debug("Could not seed skill %s: %s", src.name, exc)
            sidecar = bundled_skills_dir / f"{src.stem}.yaml"
            if sidecar.exists():
                dest_yaml = KINTHIC_SKILLS / sidecar.name
                if not dest_yaml.exists():
                    try:
                        shutil.copy2(sidecar, dest_yaml)
                    except OSError as exc:
                        log.debug(
                            "Could not seed skill sidecar %s: %s", sidecar.name, exc
                        )

    if not KINTHIC_DIRECTIVES_FILE.exists():
        try:
            KINTHIC_DIRECTIVES_FILE.write_text(
                "# Kinthic Core Directives\n\n"
                "This file contains unbreakable rules and behavioral guidelines. "
                "Any instructions here override general knowledge and normal operating procedures.\n",
                encoding="utf-8",
            )
        except Exception:
            pass

    # 6. Phantom Cleanup
    if KINTHIC_PHANTOM.exists():
        try:
            shutil.rmtree(KINTHIC_PHANTOM)
            log.info("Cleaned up leftover phantom directory from previous crash")
        except Exception as e:
            log.error(f"Failed to clean up phantom directory: {e}")

    # 7. Migrate old data from legacy project folders (e.g. data/kinthic.db)
    old_data_dir = PROJECT_ROOT / "data"
    old_db = old_data_dir / "kinthic.db"

    if old_db.exists() and not SILEX_DB.exists():
        try:
            shutil.copy2(old_db, SILEX_DB)
            log.info("Migrated existing database to ~/.kinthic/storage/silex.db")
        except Exception as exc:
            log.warning("Could not migrate legacy database (non-fatal): %s", exc)
    elif old_db.exists() and SILEX_DB.exists():
        log.warning(
            "WARNING: Both old database (data/kinthic.db) and new database (~/.kinthic/storage/silex.db) exist. Using new database."
        )

    old_vector_db1 = old_data_dir / "vector_db"
    old_vector_db2 = KINTHIC_HOME / "vector_db"
    for old_v in [old_vector_db1, old_vector_db2]:
        if old_v.exists() and old_v.is_dir():
            if safe_is_empty_dir(SILEX_VECTOR_DB):
                try:
                    shutil.copytree(old_v, SILEX_VECTOR_DB, dirs_exist_ok=True)
                    log.info(
                        f"Migrated existing ChromaDB from {old_v} to {SILEX_VECTOR_DB}"
                    )
                except Exception as exc:
                    log.warning("Could not migrate ChromaDB (non-fatal): %s", exc)
            break

    # Migrate settings/secrets
    old_settings = [old_data_dir / "settings.json", KINTHIC_HOME / "settings.json"]
    for osg in old_settings:
        if osg.exists() and not KINTHIC_CONFIG.exists():
            try:
                shutil.copy2(osg, KINTHIC_CONFIG)
                log.info(f"Migrated settings from {osg} to {KINTHIC_CONFIG}")
            except Exception as exc:
                log.warning("Could not migrate settings (non-fatal): %s", exc)
            break

    # Secrets permission
    if not KINTHIC_SECRETS.exists():
        try:
            KINTHIC_SECRETS.write_text("{}", encoding="utf-8")
        except Exception as exc:
            log.warning("Could not seed secrets.json (non-fatal): %s", exc)

    if os.name != "nt":
        try:
            os.chmod(KINTHIC_SECRETS, 0o600)
        except OSError:
            pass
    else:
        log.warning(
            "WARNING: secrets.json has no file permission protection on Windows. Store API keys as environment variables for better security."
        )

    if not KINTHIC_HMAC_KEY.exists():
        try:
            fd = os.open(str(KINTHIC_HMAC_KEY), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                key = os.urandom(32)
                os.write(fd, key)
            finally:
                os.close(fd)
            if os.name != "nt":
                os.chmod(KINTHIC_HMAC_KEY, 0o600)
            log.info("Generated plugin HMAC key at ~/.kinthic/config/hmac_key.bin")
        except FileExistsError:
            pass  # Another process created it first — that's fine
        except Exception as e:
            log.error(f"Failed to generate HMAC key: {e}")

    # 9. Ensure persona.yaml exists
    if not KINTHIC_PERSONA.exists():
        import yaml

        default_persona = {
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
        try:
            with open(KINTHIC_PERSONA, "w", encoding="utf-8") as f:
                yaml.safe_dump(default_persona, f, sort_keys=False, allow_unicode=True)
            log.info(
                "Initialized default persona.yaml at ~/.kinthic/config/persona.yaml"
            )
        except Exception as e:
            log.error(f"Failed to initialize default persona.yaml: {e}")

    # 10. Enforce Absolute Path Warning for WSL mounts (/mnt/)
    if str(WORKSPACE_DIR).startswith("/mnt/"):
        import sys

        sys.stderr.write(
            "\033[90m⚠️  Warning: Running Kinthic on virtualized Windows mounts (/mnt/...) "
            "severely impacts filesystem monitoring latency.\n"
            "   It is highly advised to move your files to the native Linux volume structure "
            "for optimal execution speeds.\033[0m\n"
        )


ensure_kinthic_home()


def load_persona_config() -> dict:
    """Load the persona configuration from ~/.kinthic/persona.yaml."""
    ensure_kinthic_home()
    if not KINTHIC_PERSONA.exists():
        return {
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
    import yaml

    try:
        with open(KINTHIC_PERSONA, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logging.getLogger("kinthic.init").error(f"Failed to load persona.yaml: {e}")
        return {}


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

# Load .env from project root, then ~/.kinthic/.env (installer default location)
_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    load_dotenv(_env_file)
_kinthic_env = KINTHIC_HOME / ".env"
if _kinthic_env.exists():
    load_dotenv(_kinthic_env, override=True)

_settings_store = None


def get_settings_store() -> "RuntimeSettingsStore":
    global _settings_store
    if _settings_store is None:
        from silex_core.runtime.settings import RuntimeSettingsStore

        _settings_store = RuntimeSettingsStore()
    return _settings_store


def get_provider_settings(settings_store=None) -> dict:
    store = settings_store or get_settings_store()
    saved = store.load_settings()

    # Priority: Env Var > Saved Settings > Hardcoded Default
    # KINTHIC_* is the canonical name; SILEX_* and ARIA_* are legacy aliases.
    provider = (
        os.getenv("KINTHIC_PROVIDER")
        or os.getenv("SILEX_PROVIDER")
        or os.getenv("ARIA_PROVIDER")
        or saved.get("provider", "gemini")
    )
    model = (
        os.getenv("KINTHIC_MODEL")
        or os.getenv("SILEX_MODEL")
        or os.getenv("ARIA_MODEL")
        or saved.get("model", "gemini-2.5-flash")
    )

    if provider == "custom":
        model = saved.get("model", model)

    fast_model = (
        os.getenv("KINTHIC_FAST_MODEL")
        or os.getenv("SILEX_FAST_MODEL")
        or os.getenv("ARIA_FAST_MODEL")
        or saved.get("fast_model", model)
    )
    reasoning_model = (
        os.getenv("KINTHIC_REASONING_MODEL")
        or os.getenv("SILEX_REASONING_MODEL")
        or os.getenv("ARIA_REASONING_MODEL")
        or saved.get("reasoning_model", fast_model)
    )
    critic_model = (
        os.getenv("KINTHIC_CRITIC_MODEL")
        or os.getenv("SILEX_CRITIC_MODEL")
        or os.getenv("ARIA_CRITIC_MODEL")
        or saved.get("critic_model", reasoning_model)
    )

    return {
        "provider": provider,
        "model": model,
        "fast_model": fast_model,
        "reasoning_model": reasoning_model,
        "critic_model": critic_model,
        "base_url": saved.get("base_url", ""),
    }


def get_provider_secret(provider_id: str, settings_store=None) -> str | None:
    store = settings_store or get_settings_store()
    stored = store.get_provider_secret(provider_id)
    if stored:
        return stored

    from silex_core.llm.registry import get_provider_profile

    profile = get_provider_profile(provider_id)
    if not profile or not profile.env_vars:
        return ""
    env_name = profile.env_vars[0]
    value = os.getenv(env_name, "")
    if not value or value.endswith("_here"):
        return ""
    return value


def get_search_secret(provider_id: str, settings_store=None) -> str:
    store = settings_store or get_settings_store()
    stored = store.get_provider_secret(provider_id)
    if stored:
        return stored

    # Env fallbacks
    env_map = {
        "tavily": "TAVILY_API_KEY",
        "brave": "BRAVE_API_KEY",
        "xai": "XAI_API_KEY",
        "x_search": "XAI_API_KEY",
    }
    env_var = env_map.get(provider_id.lower())
    if env_var:
        val = os.getenv(env_var, "")
        if val and not val.endswith("_here"):
            return val
    return ""


def get_api_key() -> str:
    """Backward-compatible provider key lookup."""
    provider = get_provider_settings()["provider"]
    key = get_provider_secret(provider)
    if key:
        return key
    raise EnvironmentError(
        f"{provider} API key is not set.\n"
        "Run `kinthic setup`, use the web onboarding flow, or configure the matching env var."
    )


def get_model() -> str:
    """Get the active model."""
    return get_provider_settings()["model"]


def get_log_level() -> str:
    """Get the logging level."""
    return (
        os.getenv("KINTHIC_LOG_LEVEL") or os.getenv("SILEX_LOG_LEVEL") or os.getenv("ARIA_LOG_LEVEL") or "INFO"
    ).upper()


def env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean feature flag from the environment."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _saved_security_flag(name: str, default: bool) -> bool:
    settings = get_settings_store().load_settings()
    return bool(settings.get("security", {}).get(name, default))


def terminal_execution_enabled() -> bool:
    """Whether Kinthic may run sandboxed terminal commands."""
    return (
        env_flag("KINTHIC_ENABLE_TERMINAL_EXECUTION")
        or env_flag("SILEX_ENABLE_TERMINAL_EXECUTION")
        or env_flag("ARIA_ENABLE_TERMINAL_EXECUTION", _saved_security_flag("terminal_execution", True))
    )


def terminal_host_fallback_enabled() -> bool:
    """Whether terminal commands may run directly on the host when Docker is
    unavailable.
    """
    return env_flag("KINTHIC_ALLOW_HOST_TERMINAL_FALLBACK", True)


def code_apply_enabled() -> bool:
    """Whether Kinthic may apply code edits without a human approval step."""
    return (
        env_flag("KINTHIC_ENABLE_CODE_APPLY")
        or env_flag("SILEX_ENABLE_CODE_APPLY")
        or env_flag("ARIA_ENABLE_CODE_APPLY", _saved_security_flag("code_apply", False))
    )


def browser_actions_enabled() -> bool:
    """Whether Kinthic may use the browser automation tool."""
    return (
        env_flag("KINTHIC_ENABLE_BROWSER_ACTIONS")
        or env_flag("SILEX_ENABLE_BROWSER_ACTIONS")
        or env_flag("ARIA_ENABLE_BROWSER_ACTIONS", _saved_security_flag("browser_actions", True))
    )


def background_actions_enabled() -> bool:
    """Whether Kinthic may wake itself up to work on active goals."""
    return (
        env_flag("KINTHIC_ENABLE_BACKGROUND_LOOP")
        or env_flag("SILEX_ENABLE_BACKGROUND_LOOP")
        or env_flag("ARIA_ENABLE_BACKGROUND_LOOP", _saved_security_flag("background_actions", False))
    )


def require_tool_approvals() -> bool:
    """Whether high-risk tools should enter a pending approval queue."""
    return (
        env_flag("KINTHIC_REQUIRE_TOOL_APPROVALS")
        or env_flag("SILEX_REQUIRE_TOOL_APPROVALS")
        or env_flag("ARIA_REQUIRE_TOOL_APPROVALS", _saved_security_flag("require_tool_approvals", True))
    )


def max_tool_calls_per_turn() -> int:
    """Hard ceiling for model-requested tool calls in a single turn."""
    raw = os.getenv("SILEX_MAX_TOOL_CALLS_PER_TURN") or os.getenv(
        "ARIA_MAX_TOOL_CALLS_PER_TURN", "8"
    )
    try:
        return max(1, int(raw))
    except ValueError:
        return 8


def gateway_host() -> str:
    """Bind address for the HTTP gateway. Defaults to loopback-only."""
    return os.getenv("KINTHIC_GATEWAY_HOST", "127.0.0.1")


def gateway_port() -> int:
    raw = os.getenv("KINTHIC_GATEWAY_PORT", "8000")
    try:
        return int(raw)
    except ValueError:
        return 8000


def gateway_allowed_origins() -> list[str]:
    """Explicit browser Origins allowed to call the local gateway (no wildcards)."""
    extra = os.getenv("KINTHIC_DASHBOARD_ORIGIN", "")
    origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    if extra:
        origins.extend(o.strip() for o in extra.split(",") if o.strip())
    return origins


def gateway_auth_required() -> bool:
    """Whether the gateway must validate the web API key on every request."""
    return env_flag("KINTHIC_GATEWAY_AUTH_REQUIRED", True)


def get_process_role() -> str:
    """Identify this process for single-writer deployment checks."""
    return os.getenv("SILEX_PROCESS_ROLE") or os.getenv(
        "ARIA_PROCESS_ROLE", "standalone"
    )


def allow_multi_writer() -> bool:
    """Whether multiple Kinthic processes may share a data directory."""
    return env_flag("SILEX_ALLOW_MULTI_WRITER") or env_flag(
        "ARIA_ALLOW_MULTI_WRITER", False
    )





def telegram_public_mode_enabled() -> bool:
    settings_value = bool(
        get_settings_store().load_settings().get("telegram", {}).get("public_mode", False)
    )
    return env_flag("TELEGRAM_PUBLIC_MODE", settings_value)


def autonomy_policy_snapshot() -> dict:
    """Operator-facing summary of the active autonomy policy."""
    return {
        "terminal_execution": terminal_execution_enabled(),
        "code_apply": code_apply_enabled(),
        "browser_actions": browser_actions_enabled(),
        "background_actions": background_actions_enabled(),
        "require_tool_approvals": require_tool_approvals(),
        "max_tool_calls_per_turn": max_tool_calls_per_turn(),
        "process_role": get_process_role(),
        "provider": get_provider_settings()["provider"],
        "model": get_provider_settings()["model"],
    }


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Memory retrieval budget per turn
MAX_RECENT_MEMORIES = 5
MAX_IMPORTANT_MEMORIES = 5
MAX_RELEVANT_MEMORIES = 5

# Hard cap on the retrieval query text itself (chars).
MAX_RETRIEVAL_QUERY_CHARS = int(os.getenv("KINTHIC_MAX_RETRIEVAL_QUERY_CHARS", "2000"))

# Hard cap on total memory content (chars) returned by retrieve_context
MAX_CONTEXT_MEMORY_CHARS = int(os.getenv("KINTHIC_MAX_CONTEXT_MEMORY_CHARS", "12000"))

# Conversation context
MAX_HISTORY_TURNS = 10

# Memory pruning
MEMORY_ARCHIVE_THRESHOLD = 0.1  # Importance below this gets archived eventually
MEMORY_MAX_AGE_DAYS = 365  # For future use

# ---------------------------------------------------------------------------
# Epistemic Memory Orchestration Constants
# ---------------------------------------------------------------------------

# A-MAC (Adaptive Memory Admission Control)
AMAC_THRESHOLD = float(os.getenv("KINTHIC_AMAC_THRESHOLD", "0.40"))
AMAC_WEIGHTS = [
    0.3,
    0.3,
    0.25,
    0.05,
    0.1,
]  # utility, confidence, novelty, recency, type_prior

# Bayesian Trust Engine
TRUST_CUTOFF = float(os.getenv("KINTHIC_TRUST_CUTOFF", "0.50"))
TRUST_FLOOR = float(os.getenv("KINTHIC_TRUST_FLOOR", "0.30"))

# MemoryGuard Middleware
MEMORY_GUARD_STRICT = env_flag("KINTHIC_MEMORY_GUARD_STRICT", True)
