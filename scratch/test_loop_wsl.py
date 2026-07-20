import asyncio
import logging
import sys
from pathlib import Path

# Setup path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from silex_core.harness.wrapper import LoopWrapper

async def main():
    logging.basicConfig(level=logging.INFO)
    wrapper = LoopWrapper()
    await wrapper.startup()
    print("ENGINE STARTED UP.")
    
    # Process turn
    print("SENDING: can u search, how much is bitcoin today?")
    res = await wrapper.process("can u search, how much is bitcoin today?")
    print("RESPONSE TEXT:", res.response)
    
    await wrapper.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
