from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider

profile = ProviderProfile(
    name='openrouter',
    display_name='OpenRouter',
    env_vars=('OPENROUTER_API_KEY',),
    base_url='https://openrouter.ai/api/v1',
    api_mode='chat_completions',
    default_aux_model=''
)
register_provider(profile, None)
