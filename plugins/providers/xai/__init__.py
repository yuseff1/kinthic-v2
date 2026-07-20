from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider

profile = ProviderProfile(
    name='xai',
    display_name='xAI (Grok)',
    env_vars=('XAI_API_KEY',),
    base_url='https://api.x.ai/v1',
    api_mode='chat_completions',
    default_aux_model=''
)
register_provider(profile, None)
