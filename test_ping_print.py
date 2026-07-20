from urllib.parse import urlparse, parse_qs
base_url = "https://yuseff.openai.azure.com/openai/responses?api-version=2025-04-01-preview"
base_url = base_url.rstrip("/")
parsed = urlparse(base_url)
endpoint = f"{parsed.scheme}://{parsed.netloc}"
print("ENDPOINT IS:", endpoint)
