from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider

profile = ProviderProfile(
    name='ollama',
    display_name='Ollama',
    env_vars=(),
    base_url='http://127.0.0.1:11434/v1',
    api_mode='chat_completions',
    default_aux_model='llama3.3'
)
register_provider(profile, None)
