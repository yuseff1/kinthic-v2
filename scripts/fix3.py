with open('d:/varsen/kinthic/scripts/cli.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('provider.base_url or  "http://127.0.0.1:11434/v1")', 'provider.base_url or "http://127.0.0.1:11434/v1"')
content = content.replace('provider.base_url or  "http://127.0.0.1:1234/v1")', 'provider.base_url or "http://127.0.0.1:1234/v1"')

with open('d:/varsen/kinthic/scripts/cli.py', 'w', encoding='utf-8') as f:
    f.write(content)
