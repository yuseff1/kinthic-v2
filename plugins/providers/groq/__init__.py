from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider

profile = ProviderProfile(
    name='groq',
    display_name='Groq',
    env_vars=('GROQ_API_KEY',),
    base_url='https://api.groq.com/openai/v1',
    api_mode='chat_completions',
    default_aux_model='llama-3.3-70b-versatile'
)
register_provider(profile, None)
