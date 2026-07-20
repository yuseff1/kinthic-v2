from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider

profile = ProviderProfile(
    name='fireworks',
    display_name='Fireworks AI',
    env_vars=('FIREWORKS_API_KEY',),
    base_url='https://api.fireworks.ai/inference/v1',
    api_mode='chat_completions',
    default_aux_model=''
)
register_provider(profile, None)
