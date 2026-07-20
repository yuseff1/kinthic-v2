from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider

profile = ProviderProfile(
    name='mistral',
    display_name='Mistral',
    env_vars=('MISTRAL_API_KEY',),
    base_url='https://api.mistral.ai/v1',
    api_mode='chat_completions',
    default_aux_model='mistral-small-latest'
)
register_provider(profile, None)
