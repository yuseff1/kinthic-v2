from silex_core.llm.base import ProviderProfile
from silex_core.llm.registry import register_provider
from .client import OpenAICompatibleProvider

profile = ProviderProfile(name='openai_compat', display_name='OpenAI API Compatible', env_vars=(), api_mode='chat_completions')
register_provider(profile, OpenAICompatibleProvider)
