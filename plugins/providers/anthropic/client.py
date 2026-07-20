"""
Anthropic provider implementation.
"""

from __future__ import annotations

import json
import time
from base64 import b64encode

from silex_core.llm.base import (
    BaseLLMProvider,
    SchemaT,
    retry_on_transient,
    repair_json,
    ProviderProfile,
)
from silex_core.runtime.settings import RuntimeSettingsStore
from silex_core.runtime.usage import UsageTracker
from silex_core.llm.catalog import calculate_cost_usd
from silex_core.llm.base import get_provider_secret, get_provider_settings
from silex_engine.logger import setup_logger

log = setup_logger("silex.llm.anthropic")


class AnthropicProvider(BaseLLMProvider):
    """Anthropic provider with JSON-mode prompting."""

    def __init__(
        self,
        provider_profile: ProviderProfile,
        settings_store: RuntimeSettingsStore | None = None,
        usage_tracker: UsageTracker | None = None,
    ):
        settings = get_provider_settings(settings_store)
        super().__init__(default_model=settings["model"])
        self.provider_profile = provider_profile
        self._settings_store = settings_store
        self.api_key = get_provider_secret(
            provider_profile.name, settings_store=settings_store
        )
        self._usage_tracker = usage_tracker
        self._client = None
        self.provider_name = provider_profile.name

    def connect(self) -> None:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise RuntimeError("Install kinthic[providers] to use Anthropic.") from exc
        self._client = AsyncAnthropic(api_key=self.api_key)
        log.info("Anthropic provider ready: %s", self.default_model)

    @property
    def client(self):
        if self._client is None:
            raise RuntimeError("Anthropic client not connected.")
        return self._client

    @retry_on_transient(max_retries=3, base_delay=1.5)
    async def complete_json(
        self,
        *,
        schema: type[SchemaT],
        system_prompt: str,
        user_input: str,
        images: list[dict] | None = None,
        model_override: str | None = None,
        temperature: float = 0.7,
        request_kind: str = "chat",
    ) -> SchemaT:
        model = model_override or self.default_model
        messages: list[dict] = []
        content: list[dict] = [{"type": "text", "text": user_input}]
        if images:
            for image in images:
                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image["mime"],
                            "data": b64encode(image["bytes"]).decode("ascii"),
                        },
                    }
                )
        messages.append({"role": "user", "content": content})

        prompt = (
            f"{system_prompt}\n\n"
            "Respond only with valid JSON matching this schema:\n"
            f"{json.dumps(schema.model_json_schema(), indent=2)}"
        )
        started = time.perf_counter()
        error_text: str | None = None
        response = None
        try:
            response = await self.client.messages.create(
                model=model,
                max_tokens=4096,
                temperature=temperature,
                system=prompt,
                messages=messages,
            )
            text = "".join(
                block.text
                for block in response.content
                if getattr(block, "type", "") == "text"
            )

            # Try direct parse first, then repair if needed
            try:
                return schema.model_validate(json.loads(text))
            except (json.JSONDecodeError, Exception):
                log.warning(
                    "Anthropic returned non-parseable JSON. Attempting repair..."
                )
                repaired = repair_json(text)
                return schema.model_validate(json.loads(repaired))
        except Exception as exc:
            error_text = str(exc)
            raise
        finally:
            if self._usage_tracker:
                usage = getattr(response, "usage", None) if response else None
                p_tok = getattr(usage, "input_tokens", 0) if usage else 0
                c_tok = getattr(usage, "output_tokens", 0) if usage else 0
                await self._usage_tracker.log_llm_call(
                    provider=self.provider_name,
                    model=model,
                    request_kind=request_kind,
                    input_tokens=p_tok if usage else None,
                    output_tokens=c_tok if usage else None,
                    estimated_cost_usd=calculate_cost_usd(model, p_tok, c_tok),
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    success=error_text is None,
                    error=error_text,
                )
