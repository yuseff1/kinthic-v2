"""Load and validate ~/.kinthic/config/mcp.yaml."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("silex.mcp.config")

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _expand_env(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return os.environ.get(key, "")

    return _ENV_PATTERN.sub(repl, value)


def _expand_value(obj: Any) -> Any:
    if isinstance(obj, str):
        return _expand_env(obj)
    if isinstance(obj, list):
        return [_expand_value(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _expand_value(v) for k, v in obj.items()}
    return obj


class McpConfig:
    """Parsed MCP server configuration."""

    def __init__(self, path: Path, raw: dict[str, Any]) -> None:
        self.path = path
        self.servers: dict[str, dict[str, Any]] = dict(raw.get("servers") or {})

    def get_server(self, name: str) -> dict[str, Any] | None:
        return self.servers.get(name)

    def list_servers(self) -> list[str]:
        return sorted(self.servers.keys())

    def enabled_servers(self) -> dict[str, dict[str, Any]]:
        return {
            name: cfg for name, cfg in self.servers.items() if cfg.get("enabled", True)
        }

    def save(self) -> None:
        import yaml

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"servers": self.servers}
        with open(self.path, "w", encoding="utf-8") as f:
            yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True)


def get_mcp_config_path() -> Path:
    from silex_core.utils.config import KINTHIC_HOME

    return KINTHIC_HOME / "config" / "mcp.yaml"


def load_mcp_config() -> McpConfig:
    path = get_mcp_config_path()
    if not path.exists():
        return McpConfig(path, {"servers": {}})
    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        raw = _expand_value(raw)
        return McpConfig(path, raw)
    except Exception as exc:
        log.warning("Could not load MCP config: %s", exc)
        return McpConfig(path, {"servers": {}})


def write_server(name: str, server_cfg: dict[str, Any]) -> None:
    cfg = load_mcp_config()
    cfg.servers[name] = server_cfg
    cfg.save()


def set_server_enabled(name: str, enabled: bool) -> bool:
    cfg = load_mcp_config()
    if name not in cfg.servers:
        return False
    cfg.servers[name]["enabled"] = enabled
    cfg.save()
    return True
