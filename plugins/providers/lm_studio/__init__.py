from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider

profile = ProviderProfile(
    name='lm_studio',
    display_name='LM Studio',
    env_vars=(),
    base_url='http://127.0.0.1:1234/v1',
    api_mode='chat_completions',
    default_aux_model='meta-llama-3-8b-instruct'
)
register_provider(profile, None)
