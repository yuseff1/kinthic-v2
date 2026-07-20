from __future__ import annotations

import json
import time
from base64 import b64encode
from typing import Any

from silex_core.llm.base import (
    BaseLLMProvider,
    SchemaT,
    retry_on_transient,
    repair_json,
    ProviderProfile,
)
from silex_core.runtime.usage import UsageTracker
from silex_core.runtime.settings import RuntimeSettingsStore
from silex_core.llm.catalog import calculate_cost_usd
from silex_core.llm.base import get_provider_secret, get_provider_settings
from silex_engine.logger import setup_logger

log = setup_logger("silex.llm.openai_compat")


def _make_schema_strict(obj: Any) -> Any:
    """Recursively enforce strict JSON Schema requirements for OpenAI compatible strict schemas:
    1. additionalProperties: False must be specified on all objects.
    2. All fields in 'properties' must be listed in the 'required' array.
    """
    if isinstance(obj, dict):
        res = {}
        for k, v in obj.items():
            res[k] = _make_schema_strict(v)

        if res.get("type") == "object":
            res["additionalProperties"] = False
            if "properties" in res:
                props = res["properties"]
                res["required"] = list(props.keys())
        return res
    elif isinstance(obj, list):
        return [_make_schema_strict(x) for x in obj]
    return obj


def _generate_json_blueprint(schema: type) -> str:
    """Generate a clean structural JSON blueprint of the Pydantic schema, detailing exact field names."""
    try:
        schema_dict = schema.model_json_schema()

        def resolve_ref(ref: str, root_defs: dict) -> dict:
            if not ref:
                return {}
            parts = ref.split("/")
            name = parts[-1]
            return root_defs.get(name, {})

        def get_type_desc(field_schema: dict, root_defs: dict) -> str:
            if "$ref" in field_schema:
                ref_schema = resolve_ref(field_schema["$ref"], root_defs)
                return get_type_desc(ref_schema, root_defs)

            t = field_schema.get("type", "any")
            if "anyOf" in field_schema:
                types = []
                for sub in field_schema["anyOf"]:
                    if "$ref" in sub:
                        ref_schema = resolve_ref(sub["$ref"], root_defs)
                        types.append(ref_schema.get("type", "object"))
                    else:
                        types.append(sub.get("type", "null"))
                t = " | ".join(types)
            return t

        root_defs = schema_dict.get("$defs", {})

        def build_blueprint_node(
            properties: dict, required_fields: list, root_defs: dict
        ) -> dict:
            node = {}
            for name, prop in properties.items():
                is_req = " (required)" if name in required_fields else " (optional)"
                prop_type = get_type_desc(prop, root_defs)

                if prop.get("type") == "array" and "items" in prop:
                    items = prop["items"]
                    if "$ref" in items:
                        ref_schema = resolve_ref(items["$ref"], root_defs)
                        node[name] = [
                            build_blueprint_node(
                                ref_schema.get("properties", {}),
                                ref_schema.get("required", []),
                                root_defs,
                            )
                        ]
                    elif "properties" in items:
                        node[name] = [
                            build_blueprint_node(
                                items.get("properties", {}),
                                items.get("required", []),
                                root_defs,
                            )
                        ]
                    else:
                        node[name] = [f"({items.get('type', 'any')})"]
                elif prop_type == "object" or ("properties" in prop):
                    sub_props = prop.get("properties", {})
                    sub_req = prop.get("required", [])
                    if not sub_props and "$ref" in prop:
                        ref_schema = resolve_ref(prop["$ref"], root_defs)
                        sub_props = ref_schema.get("properties", {})
                        sub_req = ref_schema.get("required", [])
                    node[name] = build_blueprint_node(sub_props, sub_req, root_defs)
                else:
                    node[name] = (
                        f"({prop_type}){is_req} - {prop.get('description', '')}"
                    )
            return node

        blueprint = build_blueprint_node(
            schema_dict.get("properties", {}),
            schema_dict.get("required", []),
            root_defs,
        )
        return json.dumps(blueprint, indent=2)
    except Exception as e:
        log.warning("Failed to generate blueprint dynamically: %s", e)
        return json.dumps(
            {
                "reasoning": "(string) (required) - KINTHIC's internal thought process.",
                "working_scratchpad": "(string | null) (optional) - temporary workspace.",
                "response": "(string) (required) - Clear, direct response to show the user.",
                "new_memories": [
                    {
                        "content": "(string) (required) - Fact/knowledge to remember.",
                        "importance": "(number) (required) - Rating 1 to 5.",
                        "from_concept": "(string) (required) - Concept key link.",
                        "to_concept": "(string) (required) - Concept key link.",
                        "relationship": "(string) (required) - Relationship type.",
                        "evidence": "(string) (required) - Why the relationship exists.",
                    }
                ],
                "goal_updates": [
                    {
                        "goal_id": "(string) (required) - ID of the goal.",
                        "description": "(string) (required) - Description of goal.",
                        "action": "(string) (required) - 'create', 'complete', 'abandon' or 'progress'",
                    }
                ],
                "self_reflection": "(string) (required) - Honests metacognitive self reflection.",
                "confidence": "(number) (required) - Confidence metric from 0.0 to 1.0.",
            },
            indent=2,
        )


class OpenAICompatibleProvider(BaseLLMProvider):
    """OpenAI-compatible provider for OpenAI, OpenRouter, DeepSeek, Mistral, Groq, and Ollama."""

    def __init__(
        self,
        provider_profile: ProviderProfile,
        settings_store: RuntimeSettingsStore | None = None,
        usage_tracker: UsageTracker | None = None,
    ):
        settings = get_provider_settings(settings_store)
        global_settings = settings_store.load_settings() if settings_store else {}
        provider_name = provider_profile.name
        model = settings.get("model") or global_settings.get("model") or provider_profile.default_aux_model
        base_url = provider_profile.base_url
        if provider_name in ("custom", "azure"):
            base_url = settings.get("base_url") or global_settings.get("base_url", "") or base_url
            model = settings.get("model") or global_settings.get("model", model)

        super().__init__(default_model=model)
        self.provider_profile = provider_profile
        self._settings_store = settings_store
        self.provider_name = provider_name
        self.api_key = get_provider_secret(provider_name, settings_store=settings_store)
        self.base_url = base_url.rstrip("/")
        self.extra_headers = dict(provider_profile.default_headers)
        self._usage_tracker = usage_tracker
        self._client = None

    def connect(self) -> None:
        import os

        is_azure = self.provider_name == "azure" or "openai.azure.com" in self.base_url
        if is_azure:
            try:
                from openai import AsyncAzureOpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "Install kinthic[providers] to use OpenAI-compatible providers."
                ) from exc

            # Parse and clean Azure Endpoint URL (extract scheme and host, ignoring paths/queries)
            from urllib.parse import urlparse, parse_qs

            base_url = self.base_url
            if not base_url.startswith(("http://", "https://")):
                base_url = f"https://{base_url}"

            parsed = urlparse(base_url)
            endpoint = f"{parsed.scheme}://{parsed.netloc}"

            # Extract API version from pasted query parameters if present
            queries = parse_qs(parsed.query)
            api_version_param = queries.get("api-version")
            api_version = os.getenv("AZURE_OPENAI_API_VERSION")
            if not api_version and api_version_param:
                api_version = api_version_param[0]
            if not api_version:
                api_version = "2024-12-01-preview"

            self._client = AsyncAzureOpenAI(
                api_key=self.api_key or "",
                azure_endpoint=endpoint,
                api_version=api_version,
                default_headers=self.extra_headers or None,
            )
            log.info(
                "Azure OpenAI provider ready: %s (%s)",
                self.provider_name,
                self.default_model,
            )
        else:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "Install kinthic[providers] to use OpenAI-compatible providers."
                ) from exc

            self._client = AsyncOpenAI(
                api_key=self.api_key or "local-kinthic",
                base_url=self.base_url,
                default_headers=self.extra_headers or None,
            )
            log.info(
                "OpenAI-compatible provider ready: %s (%s)",
                self.provider_name,
                self.default_model,
            )

    @property
    def client(self):
        if self._client is None:
            raise RuntimeError(f"{self.provider_name} client not connected.")
        return self._client

    def _simplify_schema_for_grammar(
        self, schema_dict: dict[str, Any]
    ) -> dict[str, Any]:
        import copy

        schema = copy.deepcopy(schema_dict)
        schema.pop("$defs", None)
        schema.pop("definitions", None)

        def walk(obj: Any) -> Any:
            if isinstance(obj, dict):
                obj.pop("description", None)
                obj.pop("title", None)
                if obj.get("type") == "array":
                    items = obj.get("items")
                    if isinstance(items, dict) and "$ref" in items:
                        obj["items"] = {"type": "object"}
                if "$ref" in obj:
                    obj.pop("$ref")
                    obj["type"] = "object"
                for k, v in list(obj.items()):
                    obj[k] = walk(v)
                return obj
            elif isinstance(obj, list):
                return [walk(x) for x in obj]
            return obj

        return walk(schema)

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
        user_content: list[dict[str, object]] | str = user_input
        if images:
            user_content = [{"type": "text", "text": user_input}]
            for image in images:
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image['mime']};base64,{b64encode(image['bytes']).decode('ascii')}",
                        },
                    }
                )

        is_azure = self.provider_name == "azure" or "openai.azure.com" in self.base_url
        is_openai = self.provider_name == "openai" or "api.openai.com" in self.base_url

        if is_azure:
            blueprint = _generate_json_blueprint(schema)
            system_prompt = (
                f"{system_prompt}\n\n"
                f"[CRITICAL STRUCTURED OUTPUT PARAMETERS]\n"
                f"You MUST format your final response strictly as a valid JSON object matching the blueprint defined below. "
                f"Ensure you populate all required validation keys precisely without changes to spelling or casing, "
                f"specifically including fields like 'action', 'description', 'from_concept', 'to_concept', 'relationship', and 'evidence' where defined.\n"
                f"JSON Output Structure Blueprint:\n{blueprint}\n"
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        # Apply profile-specific message preparation if present
        if self.provider_profile:
            messages = self.provider_profile.prepare_messages(messages)

        create_kwargs = {
            "model": model,
            "messages": messages,
        }
        if self.provider_name == "lm_studio":
            schema_dict = schema.model_json_schema()
            simplified_schema = self._simplify_schema_for_grammar(schema_dict)
            create_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": simplified_schema},
            }
        elif is_openai or is_azure:
            strict_schema = _make_schema_strict(schema.model_json_schema())
            create_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "strict": True,
                    "schema": strict_schema,
                },
            }
        else:
            create_kwargs["response_format"] = {"type": "json_object"}

        # Apply profile-specific overrides
        if self.provider_profile:
            from silex_core.llm.base import OMIT_TEMPERATURE

            if self.provider_profile.fixed_temperature is OMIT_TEMPERATURE:
                pass
            elif self.provider_profile.fixed_temperature is not None:
                create_kwargs["temperature"] = self.provider_profile.fixed_temperature
            else:
                create_kwargs["temperature"] = temperature

            extra_body = self.provider_profile.build_extra_body(
                model=model,
                base_url=self.base_url,
            )

            extra_body_additions, top_level_kwargs = (
                self.provider_profile.build_api_kwargs_extras(
                    model=model,
                )
            )
            extra_body.update(extra_body_additions)
            create_kwargs.update(top_level_kwargs)

            if extra_body:
                create_kwargs["extra_body"] = extra_body
        else:
            create_kwargs["temperature"] = temperature

        started = time.perf_counter()
        error_text: str | None = None
        response = None
        try:
            response = await self.client.chat.completions.create(**create_kwargs)
            choice = response.choices[0].message
            content = choice.content or ""
            if (
                not content.strip()
                and hasattr(choice, "reasoning_content")
                and choice.reasoning_content
            ):
                content = choice.reasoning_content
            if not content.strip():
                content = "{}"

            # Try direct parse first, then repair if needed
            try:
                return schema.model_validate(json.loads(content))
            except (json.JSONDecodeError, Exception):
                log.warning(
                    "%s returned non-parseable JSON. Attempting repair...",
                    self.provider_name,
                )
                repaired = repair_json(content)
                return schema.model_validate(json.loads(repaired))
        except Exception as exc:
            error_text = str(exc)
            raise
        finally:
            if self._usage_tracker:
                usage = getattr(response, "usage", None) if response else None
                p_tok = getattr(usage, "prompt_tokens", 0) if usage else 0
                c_tok = getattr(usage, "completion_tokens", 0) if usage else 0
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
