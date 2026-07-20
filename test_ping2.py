import asyncio
from silex_core.llm.provider_test import ping_provider
import silex_core.llm.provider_test
from unittest.mock import patch

original_humanize = silex_core.llm.provider_test.humanize_llm_error

def my_humanize(exc, provider_id):
    import traceback
    traceback.print_exception(type(exc), exc, exc.__traceback__)
    return original_humanize(exc, provider_id)

async def main():
    with patch('silex_core.llm.provider_test.humanize_llm_error', my_humanize):
        res = await ping_provider(
            provider_id="azure",
            api_key="fake-key",
            model_id="gpt-5.4-mini",
            base_url="https://yuseff.openai.azure.com/openai/responses?api-version=2025-04-01-preview"
        )

asyncio.run(main())
