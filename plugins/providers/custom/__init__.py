from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider

profile = ProviderProfile(
    name='custom',
    display_name='Custom Provider',
    env_vars=('CUSTOM_API_KEY',),
    base_url='',
    api_mode='chat_completions',
    default_aux_model='custom-model'
)
register_provider(profile, None)
