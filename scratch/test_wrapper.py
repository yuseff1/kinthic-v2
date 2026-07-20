import asyncio
from silex_core.harness.wrapper import LoopWrapper

async def main():
    w = LoopWrapper()
    await w.startup()
    r = await w.process('hello')
    print("Response:", r.response)
    await w.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
