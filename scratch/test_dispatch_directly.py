import asyncio
import sys
from pathlib import Path

# Setup path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from silex_core.harness.wrapper import TurnContext
from silex_core.harness.tool_dispatcher import ToolDispatcher
from silex_core.tools.registry import ToolRegistry

async def main():
    # Instantiate TurnContext with a session ID
    turn = TurnContext("test_session_123", "hello")
    
    # Instantiate ToolDispatcher
    dispatcher = ToolDispatcher()
    
    # Create a mock tool call object (since the loop extracts tool_name and arguments)
    class MockToolCall:
        def __init__(self, name, args):
            self.name = name
            self.arguments = args
            
    tool_calls = [MockToolCall("search", '{"query": "bitcoin price"}')]
    
    print("Dispatching mock tool call...")
    try:
        results = await dispatcher.dispatch(tool_calls, turn)
        print("Dispatch results:", results)
        print("SUCCESS! No attribute errors.")
    except Exception as e:
        print("FAILED with error:", e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
