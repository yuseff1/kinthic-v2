import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
from silex_core.plugins.loader import load_tool_plugins
from silex_core.utils.config import WORKSPACE_DIR

def _get_browser_tool():
    plugins_dir = WORKSPACE_DIR / "plugins" / "tools"
    tools = load_tool_plugins(plugins_dir)
    return next((t for t in tools if t.name == "browser_session_manager"), None)

@pytest.mark.asyncio
async def test_browser_session_manager_discovery_and_schema():
    tool = _get_browser_tool()
    assert tool is not None
    assert tool.name == "browser_session_manager"
    assert tool.risk_level == "network"

    # Missing action test
    res = await tool.execute()
    assert "Error: 'action' argument is required" in res

    # Unknown action test
    res = await tool.execute(action="teleport", platform="github")
    assert "Error: Unknown action 'teleport'" in res


@pytest.mark.asyncio
async def test_browser_session_manager_list_sessions():
    tool = _get_browser_tool()
    assert tool is not None

    res = await tool.execute(action="list_sessions")
    assert "Stored Browser Sessions" in res or "No active browser sessions found" in res


@pytest.mark.asyncio
async def test_browser_session_manager_check_session_no_cookie():
    tool = _get_browser_tool()
    assert tool is not None

    res = await tool.execute(action="check_session", platform="myservice")
    assert "No saved session state found for platform 'myservice'" in res


@pytest.mark.asyncio
async def test_browser_session_manager_interactive_login_mock():
    tool = _get_browser_tool()
    assert tool is not None

    mock_playwright = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()

    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.storage_state = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.url = "https://github.com/dashboard"
    mock_browser.close = AsyncMock()

    mock_context_manager = MagicMock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_playwright)
    mock_context_manager.__aexit__ = AsyncMock()

    async def mock_sleep(*args, **kwargs):
        pass

    with patch("playwright.async_api.async_playwright", return_value=mock_context_manager), \
         patch("asyncio.sleep", side_effect=mock_sleep):
        res = await tool.execute(action="interactive_login", platform="github")
        assert "SUCCESS: Logged into platform 'github'" in res
