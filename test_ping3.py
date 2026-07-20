import asyncio
import logging
import httpx
from silex_core.llm.provider_test import ping_provider

logging.basicConfig(level=logging.DEBUG)
# Enable httpx debug logging
logging.getLogger("httpx").setLevel(logging.DEBUG)
logging.getLogger("httpcore").setLevel(logging.DEBUG)

async def main():
    res = await ping_provider(
        provider_id="azure",
        api_key="fake-key",
        model_id="gpt-5.4-mini",
        base_url="https://yuseff.openai.azure.com/openai/responses?api-version=2025-04-01-preview"
    )

asyncio.run(main())
