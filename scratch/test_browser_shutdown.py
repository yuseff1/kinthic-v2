import asyncio
import sys
from pathlib import Path

# Setup path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from silex_core.harness.wrapper import LoopWrapper

async def main():
    print("Initializing LoopWrapper...")
    wrapper = LoopWrapper()
    await wrapper.startup()
    
    # Get BrowserTool and force ensure_started
    browser_tool = wrapper.tool_registry.tools.get("browser")
    if browser_tool:
        print("Lazy-starting browser...")
        try:
            # We call execute with a dummy action to ensure_started runs
            # but we won't navigate to avoid internet requirements.
            # Scrape action will just trigger ensure_started
            await browser_tool.execute(action="scrape", accessibility_tree=False)
            print("Browser started successfully.")
        except Exception as e:
            print("Failed to start browser (might be missing dependencies):", e)
            
    print("Shutting down LoopWrapper...")
    await wrapper.shutdown()
    print("SUCCESS! Wrapper shut down cleanly.")

if __name__ == "__main__":
    asyncio.run(main())
