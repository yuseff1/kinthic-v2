import asyncio
import os
import sys
from pathlib import Path

# Setup path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from silex_core.tools.system import RunTerminalCommandTool

async def main():
    os.environ["KINTHIC_ENABLE_TERMINAL_EXECUTION"] = "true"
    os.environ["KINTHIC_ALLOW_HOST_TERMINAL_FALLBACK"] = "true"
    
    tool = RunTerminalCommandTool()
    
    # Test 1: run start notepad
    res = await tool.execute("start notepad")
    print("Result for 'start notepad':", res)
    
    # Test 2: run cmd /c notepad
    res2 = await tool.execute("cmd /c notepad")
    print("Result for 'cmd /c notepad':", res2)

if __name__ == "__main__":
    asyncio.run(main())
