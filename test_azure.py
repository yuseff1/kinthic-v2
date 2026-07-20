import asyncio
from openai import AsyncAzureOpenAI
async def main():
    client = AsyncAzureOpenAI(api_key='test', azure_endpoint='https://this-domain-does-not-exist-12345.openai.azure.com', api_version='2024-02-15-preview')
    await client.chat.completions.create(model='gpt-4', messages=[{'role': 'user', 'content': 'test'}])
asyncio.run(main())
