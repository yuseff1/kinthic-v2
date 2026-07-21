import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
from silex_core.plugins.loader import load_tool_plugins
from silex_core.utils.config import WORKSPACE_DIR

def _get_plugin_tools():
    # Load plugins from local workspace (plugins/tools/x_social)
    plugins_dir = WORKSPACE_DIR / "plugins" / "tools"
    tools = load_tool_plugins(plugins_dir)
    post_tool = next((t for t in tools if t.name == "post_x_status"), None)
    login_tool = next((t for t in tools if t.name == "x_interactive_login"), None)
    engage_tool = next((t for t in tools if t.name == "x_auto_engage"), None)
    return post_tool, login_tool, engage_tool

@pytest.mark.asyncio
async def test_post_x_status_schema_and_basic_validation():
    post_tool, _, _ = _get_plugin_tools()
    assert post_tool is not None
    assert post_tool.name == "post_x_status"
    assert post_tool.risk_level == "network"

    # Test missing text argument
    res = await post_tool.execute()
    assert "Error: 'text' argument is required" in res

    # Test exceeding character limit
    long_text = "A" * 281
    res = await post_tool.execute(text=long_text)
    assert "Error: Text exceeds the 280 character limit" in res

    # Test invalid method
    res = await post_tool.execute(text="Hello", method="telepathy")
    assert "Error: Invalid posting method" in res


@pytest.mark.asyncio
async def test_post_x_status_api_missing_keys():
    post_tool, _, _ = _get_plugin_tools()
    assert post_tool is not None
    with patch.dict("os.environ", {}, clear=True):
        res = await post_tool.execute(text="Hello", method="api")
        assert "Error: Missing X API credentials" in res


@pytest.mark.asyncio
async def test_post_x_status_api_success():
    post_tool, _, _ = _get_plugin_tools()
    assert post_tool is not None
    mock_env = {
        "X_API_KEY": "key",
        "X_API_SECRET": "secret",
        "X_ACCESS_TOKEN": "token",
        "X_ACCESS_TOKEN_SECRET": "token_secret"
    }

    # Mock tweepy.Client
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = {"id": "1234567890"}
    mock_client.create_tweet.return_value = mock_response

    with patch.dict("os.environ", mock_env), \
         patch("sys.modules", {"tweepy": MagicMock()}), \
         patch("tweepy.Client", return_value=mock_client):
         
        res = await post_tool.execute(text="Hello world", method="api")
        assert "Successfully posted tweet via API v2" in res
        mock_client.create_tweet.assert_called_once_with(text="Hello world")


@pytest.mark.asyncio
async def test_x_interactive_login_success():
    _, login_tool, _ = _get_plugin_tools()
    assert login_tool is not None
    assert login_tool.name == "x_interactive_login"

    # Mock playwright async context
    mock_playwright = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()

    # Configure async chain
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.storage_state = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.is_closed = MagicMock(return_value=False)
    mock_browser.close = AsyncMock()
    
    # Mock compose button found
    mock_btn = MagicMock()
    mock_page.query_selector = AsyncMock(return_value=mock_btn)

    mock_context_manager = MagicMock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_playwright)
    mock_context_manager.__aexit__ = AsyncMock()

    async def mock_sleep(*args, **kwargs):
        pass

    with patch("playwright.async_api.async_playwright", return_value=mock_context_manager), \
         patch("asyncio.sleep", side_effect=mock_sleep):
        res = await login_tool.execute()
        assert "SUCCESS: Logged in and saved cookies" in res


@pytest.mark.asyncio
async def test_x_auto_engage_tool():
    _, _, engage_tool = _get_plugin_tools()
    assert engage_tool is not None
    assert engage_tool.name == "x_auto_engage"

    # Test missing action
    res = await engage_tool.execute()
    assert "Error: 'action' argument is required" in res

    # Test search topic action
    res = await engage_tool.execute(action="search", topic="AI Agents")
    assert "Topic Search Results for 'AI Agents'" in res or "Top recent tweets" in res

    # Test draft reply action
    res = await engage_tool.execute(action="draft_reply", topic="AI Memory")
    assert "Drafted High-Signal Reply for 'AI Memory'" in res

    # Test post reply validation
    res = await engage_tool.execute(action="post_reply", tweet_id="123")
    assert "Error: Both 'tweet_id' and 'reply_text' are required" in res

    # Test post reply success
    res = await engage_tool.execute(action="post_reply", tweet_id="123", reply_text="Great post!")
    assert "queued reply to Tweet 123" in res or "Successfully posted reply" in res

    # Test growth stats
    res = await engage_tool.execute(action="growth_stats")
    assert "X Growth & Audience Engagement Metrics" in res
