import json
import traceback
from typing import List, Any
from silex_core.tools.registry import ToolRegistry

class LoopDetectedException(Exception):
    pass

class ToolDispatcher:
    def __init__(self, tool_registry: ToolRegistry = None, *args, **kwargs):
        self.tool_registry = tool_registry or kwargs.get("registry")
        # session_id -> list of (tool_name, arguments) to detect loops
        self.history = {}

    async def dispatch(self, tool_calls: List[Any], turn_context) -> List[dict]:
        """
        Executes tool calls, catches errors, reformats them, and prevents looping.
        """
        observations = []
        
        if turn_context.session_id not in self.history:
            self.history[turn_context.session_id] = []
            
        history = self.history[turn_context.session_id]

        for tc in tool_calls:
            name = (
                getattr(tc, "tool_name", None)
                or getattr(tc, "name", None)
                or (tc.get("tool_name") or tc.get("name") if isinstance(tc, dict) else None)
            )
            raw_args = (
                getattr(tc, "arguments", None)
                or (tc.get("arguments") if isinstance(tc, dict) else None)
                or {}
            )
            if isinstance(raw_args, str):
                try:
                    arguments = json.loads(raw_args)
                except json.JSONDecodeError:
                    arguments = {}
            else:
                arguments = raw_args
            
            if not name:
                continue
                
            call_signature = (name, str(arguments))
            history.append(call_signature)
            
            # Loop Detection
            if len(history) >= 3:
                last_3 = history[-3:]
                if last_3[0] == last_3[1] == last_3[2]:
                    obs = {
                        "tool": name,
                        "error": f"LOOP_DETECTED: You have called {name} with these exact arguments 3 times in a row without progress. You MUST stop and think of a different approach.",
                        "is_error": True
                    }
                    observations.append(obs)
                    continue

            try:
                # Dispatch to tool registry
                tool = self.tool_registry.tools.get(name)
                if not tool:
                    raise ValueError(f"Tool {name} not found in registry.")
                
                # Execute (assuming all tools are async for now, or handle sync)
                result = await tool.execute(**arguments)
                
                observations.append({
                    "tool": name,
                    "result": result,
                    "is_error": False
                })
                
            except Exception as e:
                # Reformat errors nicely
                err_msg = self._format_error(name, e)
                obs = {
                    "tool": name,
                    "error": err_msg,
                    "is_error": True
                }
                observations.append(obs)

        return observations

    def _format_error(self, tool_name: str, exc: Exception) -> str:
        err_msg = str(exc)
        if isinstance(exc, PermissionError):
            return f"Permission denied when executing tool {tool_name}: {err_msg}. Actionable instruction: Check if you need elevated privileges or try a different path."
        elif isinstance(exc, FileNotFoundError):
            return f"File not found when executing tool {tool_name}: {err_msg}. Actionable instruction: Use list_dir to inspect the directory contents first."
        return f"Error executing tool: {err_msg}. Review your arguments and try again."
