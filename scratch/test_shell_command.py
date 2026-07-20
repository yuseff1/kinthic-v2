import asyncio
import os
import sys
import shutil
from pathlib import Path

# Setup path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from silex_core.tools.system import RunShellCommandTool
from silex_core.utils.config import WORKSPACE_DIR

async def main():
    os.environ["KINTHIC_ENABLE_TERMINAL_EXECUTION"] = "true"
    
    # Create test directory in workspace
    test_dir = WORKSPACE_DIR / "test_dir"
    test_dir.mkdir(exist_ok=True)
    
    tool = RunShellCommandTool()
    
    # Run command 1: Change directory
    print("Executing 'cd test_dir'...")
    res = await tool.execute("cd test_dir")
    print(res)
    
    # Run command 2: Print current working directory
    print("\nExecuting directory check...")
    if sys.platform == "win32":
        res2 = await tool.execute("echo %cd%")
    else:
        res2 = await tool.execute("pwd")
    print(res2)
    
    # Clean up
    await tool.close()
    
    try:
        shutil.rmtree(test_dir)
    except Exception:
        pass
        
    print("\nStateful Shell Test Completed.")

if __name__ == "__main__":
    asyncio.run(main())
