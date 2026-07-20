import sys
import asyncio
import uvicorn
from silex_engine.config import PORT
from silex_engine.logger import setup_logger

log = setup_logger("silex_engine.main")

async def main_async():
    from silex_engine.mcp.server.lifecycle import create_standalone_context
    from silex_engine.mcp.server.app import create_mcp_app, set_mcp_context
    
    ctx = await create_standalone_context()
    set_mcp_context(ctx)
    app = create_mcp_app(ctx)
    
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

def main():
    asyncio.run(main_async())

if __name__ == '__main__':
    main()
