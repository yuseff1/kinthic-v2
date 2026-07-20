from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider
from .client import GeminiClient

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
register_provider(profile, GeminiClient)
