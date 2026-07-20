from silex_core.llm.base import ProviderProfile
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
