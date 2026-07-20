import pytest
import os
import shlex
from pathlib import Path
from silex_core.tools.system import RunTerminalCommandTool, _SAFE_HOST_ENV_PASSTHROUGH
from silex_core.harness.tool_dispatcher import ToolDispatcher

@pytest.fixture
def terminal_tool(monkeypatch):
    monkeypatch.setattr("silex_core.tools.system.WORKSPACE_ROOT", Path("/workspace"))
    return RunTerminalCommandTool()

def test_workspace_path_escape(terminal_tool):
    """
    Test 2.1: Workspace Path Escape.
    Verify that `_validate_execution_bounds` rejects attempts to traverse outside the workspace.
    """
    # 1. Directory traversal
    argv = shlex.split("ls ../../etc")
    with pytest.raises(PermissionError, match="Directory traversal"):
        terminal_tool._validate_execution_bounds(argv)
        
    # 2. Absolute path outside workspace
    argv = shlex.split("cat /etc/shadow")
    with pytest.raises(PermissionError, match="outside workspace"):
        terminal_tool._validate_execution_bounds(argv)
        
    # 3. Path via flag
    argv = shlex.split("grep -f /root/secret.txt")
    with pytest.raises(PermissionError, match="outside workspace"):
        terminal_tool._validate_execution_bounds(argv)

def test_sandbox_fallback_secret_scrubbing():
    """
    Test 2.2: Sandbox Fallback Secret Scrubbing.
    Ensure `_SAFE_HOST_ENV_PASSTHROUGH` does not leak sensitive environment variables.
    """
    assert "API_KEY" not in _SAFE_HOST_ENV_PASSTHROUGH
    assert "AWS_SECRET_ACCESS_KEY" not in _SAFE_HOST_ENV_PASSTHROUGH
    assert "OPENAI_API_KEY" not in _SAFE_HOST_ENV_PASSTHROUGH
    assert "KINTHIC_DB_PASSWORD" not in _SAFE_HOST_ENV_PASSTHROUGH
    
    # Safe variables should be present
    assert "PATH" in _SAFE_HOST_ENV_PASSTHROUGH
    assert "HOME" in _SAFE_HOST_ENV_PASSTHROUGH
    
def test_inline_script_rejection(terminal_tool):
    """
    Verify interpreters are blocked from running inline scripts in fallback mode.
    """
    argv = shlex.split("python -c 'print(1)'")
    with pytest.raises(PermissionError, match="inline script execution"):
        terminal_tool._check_safety("python -c 'print(1)'", argv, sandboxed=False)

def test_metacharacter_rejection(terminal_tool):
    """
    Verify shell chaining is blocked.
    """
    argv = shlex.split("echo hello && cat /etc/passwd")
    with pytest.raises(PermissionError, match="Shell chaining"):
        terminal_tool._check_safety("echo hello && cat /etc/passwd", argv, sandboxed=False)

def test_tool_error_formatting():
    """
    Test 2.3: Tool Error Formatting.
    Verify that ToolDispatcher._format_error maps raw exceptions to actionable guidance.
    """
    dispatcher = ToolDispatcher(registry=None, approval_notifier=None)
    
    # 1. PermissionError -> "Actionable instruction: Check if you need elevated privileges..."
    err1 = PermissionError("Permission denied: '/etc/shadow'")
    msg1 = dispatcher._format_error("read_file", err1)
    assert "Permission denied" in msg1
    assert "Actionable instruction: Check if you need elevated privileges" in msg1
    
    # 2. FileNotFoundError -> "Actionable instruction: Use list_dir..."
    err2 = FileNotFoundError("No such file or directory: 'missing.txt'")
    msg2 = dispatcher._format_error("read_file", err2)
    assert "File not found" in msg2
    assert "Actionable instruction: Use list_dir" in msg2

