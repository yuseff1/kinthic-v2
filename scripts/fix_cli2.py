import re

with open('d:/varsen/kinthic/scripts/cli.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix list_providers loop in run_models
content = content.replace('provider["id"]', 'provider.name')
content = content.replace('provider["models"]', 'provider.fetch_models()')
content = content.replace('provider["label"]', 'provider.display_name')
content = content.replace("provider['label']", "provider.display_name")
content = content.replace('provider.get("base_url", "http', 'provider.base_url or "http')

# Fix provider_sort_key
content = content.replace('p_id = p["id"]', 'p_id = p.name')

# Fix initial mapping loop
content = content.replace('profile = get_provider_profile(p["id"])', 'profile = get_provider_profile(p.name)')
content = content.replace('label = p["label"]', 'label = p.display_name')

# Fix other dictionary accesses to p.name
content = content.replace('p["id"]', 'p.name')

with open('d:/varsen/kinthic/scripts/cli.py', 'w', encoding='utf-8') as f:
    f.write(content)
