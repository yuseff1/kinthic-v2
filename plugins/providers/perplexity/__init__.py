from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider

profile = ProviderProfile(
    name='perplexity',
    display_name='Perplexity',
    env_vars=('PERPLEXITY_API_KEY',),
    base_url='https://api.perplexity.ai',
    api_mode='chat_completions',
    default_aux_model='sonar'
)
register_provider(profile, None)
