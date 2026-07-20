class MemoryGuardMiddleware:
    def validate_write_attempt(self, memory_id: str, content: str) -> dict:
        return {"allowed": True, "flagged": False, "signature": None}

    def validate_read_attempt(self, memory_id: str, content: str, signature: str | None) -> bool:
        return True
