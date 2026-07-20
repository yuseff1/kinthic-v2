from typing import Protocol, Any, List

class Session(Protocol):
    id: str
    user_input: str
    def add_observations(self, observations: List[Any]) -> None: ...
    def final_response(self) -> Any: ...

class LLM(Protocol):
    async def complete_text(self, context: str) -> Any: ...

class ContextBuilder(Protocol):
    async def build_context(self, session: Session) -> str: ...

class ToolDispatcher(Protocol):
    async def dispatch(self, tool_calls: List[Any], session: Session) -> List[Any]: ...

class MemoryWriter(Protocol):
    async def write(self, response: Any, session: Session) -> None: ...

class StopEvaluator(Protocol):
    async def is_done(self, session: Session, response: Any) -> bool: ...

async def run(
    session: Session, 
    context_builder: ContextBuilder, 
    tool_dispatcher: ToolDispatcher,
    memory_writer: MemoryWriter,
    stop_eval: StopEvaluator,
    llm: LLM,
    images: List[Any] | None = None,
) -> Any:
    """
    The Cognitive Loop.
    This orchestrates the interaction between the LLM and the Agent Harness components.
    """
    # Track turns
    session.turn_count = getattr(session, "turn_count", 0)
    
    while True:
        session.turn_count += 1
        
        # 1. Build the system prompt and full context for the LLM
        context = await context_builder.build_context(session)
        
        # 2. Get the next completion from the LLM
        # We assume llm is the smart_router or base provider
        try:
            # We are calling complete_text for now because it returns a string response that we can parse,
            # or complete_json if we want structured output. We'll use whatever the client supports.
            if hasattr(llm, "think"):
                response = await llm.think(
                    system_prompt=context,
                    user_input=session.user_input,
                    images=images,
                )
            elif hasattr(llm, "complete"):
                response = await llm.complete(context)
            else:
                response = await llm.complete_text(context)
        except Exception as e:
            # Handle LLM failure
            class ErrorResponse:
                text = f"LLM Error: {str(e)}"
                has_tool_calls = False
            response = ErrorResponse()
            
        session.response = response
        
        # 3. Check for tool calls
        # BaseLLMClient doesn't have has_tool_calls natively but the provider might
        tool_calls = getattr(response, "tool_calls", [])
        has_tool_calls = getattr(response, "has_tool_calls", bool(tool_calls))
        
        if has_tool_calls:
            # Execute tools and append observations to the session
            observations = await tool_dispatcher.dispatch(tool_calls, session)
            session.add_observations(observations)
        else:
            # 4. Evaluate if the conversation turn is complete
            if await stop_eval.is_done(session, response):
                # 5. Persist relevant information to the Silex Engine
                await memory_writer.write(response, session)
                break
                
    # 6. Return the final structured response
    if hasattr(session, "final_response"):
        return session.final_response()
    return getattr(response, "text", str(response))
