from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider

profile = ProviderProfile(
    name='deepseek',
    display_name='DeepSeek',
    env_vars=('DEEPSEEK_API_KEY',),
    base_url='https://api.deepseek.com/v1',
    api_mode='chat_completions',
    default_aux_model='deepseek-chat'
)
register_provider(profile, None)
