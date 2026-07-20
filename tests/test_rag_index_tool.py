import unittest
import asyncio
from pathlib import Path
from unittest.mock import MagicMock
from silex_core.tools.rag_index import RAGIndexTool, _is_path_allowed
from silex_core.utils.config import WORKSPACE_DIR

class TestRAGIndexTool(unittest.TestCase):
    def test_path_allowance(self):
        # 1. Test workspace paths (should be allowed)
        ws_file = WORKSPACE_DIR / "some_file.txt"
        self.assertTrue(_is_path_allowed(ws_file))
        
        # 2. Test second-brain paths (should be allowed)
        sb_paths = [
            Path("D:/second-brain/articles/my-note.md"),
            Path("D:\\second-brain\\wiki\\page.md"),
            Path("/mnt/d/second-brain/inbox/doc.txt"),
        ]
        for p in sb_paths:
            self.assertTrue(_is_path_allowed(p), f"Path not allowed: {p}")
            
        # 3. Test unauthorized paths (should be blocked)
        unauthorized_paths = [
            Path("C:/Windows/System32/cmd.exe"),
            Path("/etc/passwd"),
            Path("/usr/bin/env"),
            WORKSPACE_DIR / ".." / "outside.txt",  # Traversal escape
        ]
        for p in unauthorized_paths:
            self.assertFalse(_is_path_allowed(p), f"Path allowed but should be blocked: {p}")

    def test_tool_execute_safety_block(self):
        mock_indexer = MagicMock()
        tool = RAGIndexTool(mock_indexer)
        
        # Call execute asynchronously
        loop = asyncio.get_event_loop()
        
        # Unsafe path should return access denied error
        res = loop.run_until_complete(tool.execute(path="C:/Windows/System32/cmd.exe"))
        self.assertIn("Access denied", res)
        mock_indexer.index_file.assert_not_called()
        mock_indexer.index_folder.assert_not_called()

    def test_tool_execute_missing_args(self):
        mock_indexer = MagicMock()
        tool = RAGIndexTool(mock_indexer)
        loop = asyncio.get_event_loop()
        
        res = loop.run_until_complete(tool.execute())
        self.assertIn("Error: 'path' argument is required.", res)

    def test_case_insensitive_resolution(self):
        # This checks that mismatched casings of second-brain paths map successfully
        import sys
        if sys.platform != "win32":
            # Test that uppercase second-brain matches whitelisted path allowed check
            uppercase_p = Path("D:/SECOND-BRAIN/ARTICLES/some-note.md")
            self.assertTrue(_is_path_allowed(uppercase_p))

if __name__ == "__main__":
    unittest.main()
