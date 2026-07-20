from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider

profile = ProviderProfile(
    name='cohere',
    display_name='Cohere',
    env_vars=('COHERE_API_KEY',),
    base_url='https://api.cohere.ai/compatibility/v1',
    api_mode='chat_completions',
    default_aux_model='command-r'
)
register_provider(profile, None)
