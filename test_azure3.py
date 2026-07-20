import asyncio
from openai import AsyncAzureOpenAI
async def main():
    client = AsyncAzureOpenAI(api_key='fake-key', azure_endpoint='https://yuseff.openai.azure.com', api_version='2024-12-01-preview')
    try:
        await client.chat.completions.create(model='gpt-5.4-mini', messages=[{'role': 'user', 'content': 'test'}], response_format={"type": "json_schema", "json_schema": {"name": "test", "strict": True, "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "additionalProperties": False, "required": ["ok"]}}})
    except Exception as e:
        print(f"Exception Type: {type(e).__name__}")
        print(f"Exception message: {e}")
asyncio.run(main())
