import logging

log = logging.getLogger("silex.harness.stop_evaluator")

class StopEvaluator:
    def __init__(self, max_turns: int = 40):
        self.max_turns = max_turns

    async def is_done(self, turn_context, response) -> bool:
        """
        Determines whether the cognitive loop should stop based on explicit constraints.
        """
        # 1. Check Max Turns
        # We assume turn_context keeps track of how many turns have passed
        current_turns = getattr(turn_context, "turn_count", 0)
        if current_turns >= self.max_turns:
            log.warning(f"StopEvaluator: Max turns ({self.max_turns}) exceeded. Forcing stop.")
            return True

        # 2. Check for Tool Calls
        tool_calls = getattr(response, "tool_calls", [])
        if not tool_calls:
            # If the LLM didn't request any tools, it's done thinking and has answered the user.
            log.info("StopEvaluator: No tool calls requested. Turn is complete.")
            return True

        # 3. Check for specific errors like LOOP_DETECTED in observations
        if turn_context.observations:
            for obs in turn_context.observations:
                if isinstance(obs, dict) and obs.get("is_error"):
                    error_msg = obs.get("error", "")
                    if "LOOP_DETECTED" in error_msg:
                        # Optionally, we could stop entirely, or let the LLM see the error once.
                        # For now, let the LLM see the loop error so it can apologize or pivot.
                        pass

        # Let the loop continue
        return False
