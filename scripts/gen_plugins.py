import os
import shutil
from pathlib import Path

plugins_dir = Path('d:/varsen/kinthic/plugins/providers')

def make_plugin(name, display_name, env_vars, base_url, api_mode, default_aux_model=''):
    d = plugins_dir / name
    d.mkdir(exist_ok=True)
    with open(d / 'plugin.yaml', 'w') as f:
        f.write(f"name: {name}\nversion: 1.0.0\n")
    with open(d / '__init__.py', 'w') as f:
        f.write(f"""from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider

profile = ProviderProfile(
    name='{name}',
    display_name='{display_name}',
    env_vars={tuple(env_vars)},
    base_url='{base_url}',
    api_mode='{api_mode}',
    default_aux_model='{default_aux_model}'
)
register_provider(profile, None)
""")

# Create specific Python plugins for OpenAI Compatibles
make_plugin('openrouter', 'OpenRouter', ['OPENROUTER_API_KEY'], 'https://openrouter.ai/api/v1', 'chat_completions', '')
make_plugin('openai', 'OpenAI', ['OPENAI_API_KEY'], 'https://api.openai.com/v1', 'chat_completions', 'gpt-4o-mini')
make_plugin('deepseek', 'DeepSeek', ['DEEPSEEK_API_KEY'], 'https://api.deepseek.com/v1', 'chat_completions', 'deepseek-chat')
make_plugin('mistral', 'Mistral', ['MISTRAL_API_KEY'], 'https://api.mistral.ai/v1', 'chat_completions', 'mistral-small-latest')
make_plugin('groq', 'Groq', ['GROQ_API_KEY'], 'https://api.groq.com/openai/v1', 'chat_completions', 'llama-3.3-70b-versatile')
make_plugin('xai', 'xAI (Grok)', ['XAI_API_KEY'], 'https://api.x.ai/v1', 'chat_completions', '')
make_plugin('cohere', 'Cohere', ['COHERE_API_KEY'], 'https://api.cohere.ai/compatibility/v1', 'chat_completions', 'command-r')
make_plugin('together', 'Together AI', ['TOGETHER_API_KEY'], 'https://api.together.xyz/v1', 'chat_completions', '')
make_plugin('fireworks', 'Fireworks AI', ['FIREWORKS_API_KEY'], 'https://api.fireworks.ai/inference/v1', 'chat_completions', '')
make_plugin('perplexity', 'Perplexity', ['PERPLEXITY_API_KEY'], 'https://api.perplexity.ai', 'chat_completions', 'sonar')
make_plugin('ollama', 'Ollama', [], 'http://127.0.0.1:11434/v1', 'chat_completions', 'llama3.3')
make_plugin('lm_studio', 'LM Studio', [], 'http://127.0.0.1:1234/v1', 'chat_completions', 'meta-llama-3-8b-instruct')
make_plugin('custom', 'Custom Provider', ['CUSTOM_API_KEY'], '', 'chat_completions', 'custom-model')

# Azure
azure_dir = plugins_dir / 'azure'
azure_dir.mkdir(exist_ok=True)
with open(azure_dir / 'plugin.yaml', 'w') as f:
    f.write('name: azure\nversion: 1.0.0\n')
with open(azure_dir / '__init__.py', 'w') as f:
    f.write("""from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider

profile = ProviderProfile(
    name='azure',
    display_name='Azure OpenAI',
    env_vars=('AZURE_OPENAI_API_KEY', 'AZURE_OPENAI_ENDPOINT', 'AZURE_OPENAI_API_VERSION', 'AZURE_OPENAI_MODEL'),
    base_url='',
    api_mode='chat_completions',
    default_aux_model='gpt-4o-mini'
)
register_provider(profile, None)
""")

# openai_compat (keeps the generic client class)
with open(plugins_dir / 'openai_compat' / '__init__.py', 'w') as f:
    f.write("""from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider
from .client import OpenAICompatProvider

profile = ProviderProfile(name='openai_compat', display_name='OpenAI API Compatible', env_vars=(), api_mode='chat_completions')
register_provider(profile, OpenAICompatProvider)
""")

# anthropic
with open(plugins_dir / 'anthropic' / '__init__.py', 'w') as f:
    f.write("""from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider
from .client import AnthropicProvider

class AnthropicProfile(ProviderProfile):
    def fetch_models(self, *, api_key=None):
        return [
            {"id": "claude-fable-5", "label": "Claude Fable 5", "tier": "reasoning"},
            {"id": "claude-sonnet-5", "label": "Claude Sonnet 5", "tier": "reasoning"},
            {"id": "claude-opus-4.8", "label": "Claude Opus 4.8", "tier": "reasoning"}
        ]

profile = AnthropicProfile(
    name='anthropic',
    display_name='Anthropic',
    env_vars=('ANTHROPIC_API_KEY',),
    base_url='https://api.anthropic.com',
    api_mode='anthropic_native',
    default_aux_model='claude-sonnet-5'
)
register_provider(profile, AnthropicProvider)
""")

# gemini
with open(plugins_dir / 'gemini' / '__init__.py', 'w') as f:
    f.write("""from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider
from .client import GeminiProvider

class GeminiProfile(ProviderProfile):
    def fetch_models(self, *, api_key=None):
        return [
            {"id": "gemini-3.1-pro", "label": "Gemini 3.1 Pro", "tier": "reasoning"},
            {"id": "gemini-3.5-flash", "label": "Gemini 3.5 Flash", "tier": "fast"},
            {"id": "gemini-3.1-flash-lite", "label": "Gemini 3.1 Flash Lite", "tier": "fast"}
        ]

profile = GeminiProfile(
    name='gemini',
    display_name='Google Gemini',
    env_vars=('GEMINI_API_KEY',),
    base_url='https://generativelanguage.googleapis.com/v1beta',
    api_mode='gemini_native',
    default_aux_model='gemini-3.5-flash'
)
register_provider(profile, GeminiProvider)
""")
