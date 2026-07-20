import asyncio
from silex_core.llm.provider_test import ping_provider

async def main():
    res = await ping_provider(
        provider_id="azure",
        api_key="fake-key",
        model_id="gpt-5.4-mini",
        base_url="https://yuseff.openai.azure.com/openai/responses?api-version=2025-04-01-preview"
    )
    print("PING RESULT:", res)

asyncio.run(main())
