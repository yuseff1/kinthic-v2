from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider

profile = ProviderProfile(
    name='openai',
    display_name='OpenAI',
    env_vars=('OPENAI_API_KEY',),
    base_url='https://api.openai.com/v1',
    api_mode='chat_completions',
    default_aux_model='gpt-4o-mini'
)
register_provider(profile, None)
