from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider

profile = ProviderProfile(
    name='together',
    display_name='Together AI',
    env_vars=('TOGETHER_API_KEY',),
    base_url='https://api.together.xyz/v1',
    api_mode='chat_completions',
    default_aux_model=''
)
register_provider(profile, None)
