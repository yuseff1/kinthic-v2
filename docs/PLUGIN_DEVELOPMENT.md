# Plugin Development & Architecture Guide

Kinthic supports dynamically loaded user plugins for custom tools, APIs, and integrations.

---

## Plugin Architecture

Plugins are located under `plugins/tools/<plugin_dir>/`.

Each plugin directory contains:
1. `plugin.yaml`: Manifest file specifying metadata (name, version, description, tags).
2. `tool.py`: Python module containing `BaseTool` subclass implementations.

---

## Multi-Tool Plugin Packages

A single plugin package directory can export **multiple** `BaseTool` subclasses. Kinthic's plugin loader (`silex_core/plugins/loader.py`) automatically discovers and registers all non-abstract `BaseTool` subclasses within `tool.py`.

### Example 1: `x_social` Plugin Suite (`plugins/tools/x_social/`)
Exports 3 tools:
* `post_x_status`: Posts updates to X (Twitter) via API v2 or Playwright fallback.
* `x_interactive_login`: Opens visible Chromium window for manual login and cookie capturing.
* `x_auto_engage`: Topic search, reply drafting, reply posting, and growth metrics.

### Example 2: `browser_session_manager` Plugin (`plugins/tools/browser_session_manager/`)
Exports stealth multi-platform session management:
* Actions: `list_sessions`, `interactive_login`, `check_session`, `fetch_page`.
* Supported platforms: LinkedIn, Reddit, GitHub, X (Twitter), custom URLs.
* Persistent storage: Saved to `~/.kinthic/browser_sessions/<platform>_cookies.json`.

---

## Creating a Custom Tool Plugin

1. Create a subfolder: `plugins/tools/my_tool_plugin/`
2. Create `plugin.yaml`:
   ```yaml
   name: "my_tool_plugin"
   version: "1.0.0"
   description: "My custom integration plugin."
   tags: ["custom", "api"]
   ```
3. Create `tool.py`:
   ```python
   from silex_core.tools.base import BaseTool

   class MyCustomTool(BaseTool):
       name = "my_custom_tool"
       risk_level = "read_only"
       description = "Description of what this tool does."
       schema = {
           "param1": "string (description of param1)"
       }

       async def execute(self, **kwargs) -> str:
           param1 = kwargs.get("param1", "default")
           return f"Executed my_custom_tool with {param1}"
   ```
4. Kinthic automatically loads `my_custom_tool` into the active tool registry!
