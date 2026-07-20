from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider

profile = ProviderProfile(
    name='azure',
    display_name='Azure OpenAI',
    env_vars=('AZURE_OPENAI_API_KEY', 'AZURE_OPENAI_ENDPOINT', 'AZURE_OPENAI_API_VERSION', 'AZURE_OPENAI_MODEL'),
    base_url='',
    api_mode='chat_completions',
    default_aux_model='gpt-4o-mini'
)
register_provider(profile, None)
