"""
silex_core/plugins/loader.py — Discovers and loads user tool plugins.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

log = logging.getLogger("silex.plugins.loader")

if TYPE_CHECKING:
    from silex_core.tools.base import BaseTool

# Registry of successfully loaded plugins: {plugin_dir_name: tool_instance}
_loaded_plugins: dict[str, "BaseTool"] = {}


def load_tool_plugins(plugins_dir: Path) -> list["BaseTool"]:
    """
    Scan plugins_dir and return instantiated BaseTool objects.

    Safe to call multiple times — will re-scan on each call.
    Errors in individual plugins are logged and skipped without
    crashing the entire registry.
    """
    from silex_core.tools.base import BaseTool  # local import to avoid circular deps

    tools: list[BaseTool] = []

    if not plugins_dir.is_dir():
        log.debug("Plugin tools directory does not exist: %s", plugins_dir)
        return tools

    for plugin_dir in sorted(plugins_dir.iterdir()):
        if not plugin_dir.is_dir():
            continue
        if plugin_dir.name.startswith(("_", ".")):
            continue

        manifest_path = plugin_dir / "plugin.yaml"
        tool_py = plugin_dir / "tool.py"

        if not manifest_path.exists():
            log.debug("Skipping %s — missing plugin.yaml", plugin_dir.name)
            continue
        if not tool_py.exists():
            log.debug("Skipping %s — missing tool.py", plugin_dir.name)
            continue

        try:
            # Read manifest for logging/diagnostics
            try:
                import yaml

                with open(manifest_path, encoding="utf-8") as f:
                    manifest = yaml.safe_load(f) or {}
            except Exception as exc:
                log.warning(
                    "Plugin %s: could not parse plugin.yaml: %s", plugin_dir.name, exc
                )
                manifest = {}

            plugin_label = manifest.get("name", plugin_dir.name)
            plugin_version = manifest.get("version", "?")

            # Load tool.py as an isolated module
            module_name = f"kinthic_user_plugins.tools.{plugin_dir.name}"

            # Remove stale cached version so hot-reload works
            if module_name in sys.modules:
                del sys.modules[module_name]

            spec = importlib.util.spec_from_file_location(module_name, tool_py)
            if spec is None or spec.loader is None:
                log.warning("Plugin %s: could not create module spec", plugin_dir.name)
                continue

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)  # type: ignore[union-attr]

            # Find the first BaseTool subclass (skip the base itself)
            tool_class = None
            for obj in module.__dict__.values():
                if (
                    isinstance(obj, type)
                    and issubclass(obj, BaseTool)
                    and obj is not BaseTool
                ):
                    tool_class = obj
                    break

            if tool_class is None:
                log.warning(
                    "Plugin %s: no BaseTool subclass found in tool.py", plugin_dir.name
                )
                continue

            tool_instance = tool_class()
            tools.append(tool_instance)
            _loaded_plugins[plugin_dir.name] = tool_instance

            log.info(
                "Loaded plugin tool: %s v%s → tool '%s'",
                plugin_label,
                plugin_version,
                tool_instance.name,
            )

        except Exception as exc:
            log.warning("Failed to load plugin '%s': %s", plugin_dir.name, exc)

    return tools


def list_loaded_plugins() -> list[dict]:
    """
    Return metadata about every plugin that was loaded in the last call to
    load_tool_plugins(). Used by /plugins command.
    """
    result = []
    for dir_name, tool in _loaded_plugins.items():
        result.append(
            {
                "dir_name": dir_name,
                "tool_name": tool.name,
                "description": tool.description,
                "risk_level": getattr(tool, "risk_level", "unknown"),
            }
        )
    return result


def read_manifest(plugin_dir: "Path") -> dict:
    """
    Read and return the plugin.yaml manifest from a plugin directory.
    Returns an empty dict if the file is missing or unparseable.
    """
    manifest_path = plugin_dir / "plugin.yaml"
    if not manifest_path.exists():
        return {}
    try:
        import yaml

        with open(manifest_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:
        log.debug("Could not read manifest %s: %s", manifest_path, exc)
        return {}
