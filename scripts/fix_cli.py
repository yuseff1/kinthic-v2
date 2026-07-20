import re

with open('d:/varsen/kinthic/scripts/cli.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace provider dict accesses with object accesses
content = content.replace('provider["id"]', 'provider.name')
content = content.replace('provider["label"]', 'provider.display_name')
content = content.replace("provider['label']", "provider.display_name")
content = content.replace('provider.get("base_url",', 'provider.base_url or ')

# Replace provider["models"] with provider.fetch_models()
content = content.replace('models = provider["models"]', 'models = provider.fetch_models()')

# Also fix the initial mapping loop:
#     provider_labels = []
#     for p in providers:
#         profile = get_provider_profile(p["id"])
content = content.replace('p["id"]', 'p.name')
content = content.replace('p["label"]', 'p.display_name')

# Also fix get_provider_defaults mapping
def_pattern = re.compile(r'defaults = get_provider_defaults\(provider\.name\)')
# Actually, the original was defaults = get_provider_defaults(provider["id"]) -> provider.name

with open('d:/varsen/kinthic/scripts/cli.py', 'w', encoding='utf-8') as f:
    f.write(content)
