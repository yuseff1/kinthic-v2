import unittest
from silex_core.llm.base import repair_json
import json

class TestJsonRepairRobust(unittest.TestCase):
    def test_standard_json(self):
        content = '{"reasoning": "simple", "response": "hello"}'
        result = repair_json(content)
        self.assertEqual(json.loads(result), {"reasoning": "simple", "response": "hello"})

    def test_markdown_wrapped_json(self):
        content = '```json\n{"reasoning": "markdown", "response": "hello"}\n```'
        result = repair_json(content)
        self.assertEqual(json.loads(result), {"reasoning": "markdown", "response": "hello"})

    def test_prose_before_and_after(self):
        content = 'Here is the response:\n{"reasoning": "prose", "response": "hello"}\nHope this helps!'
        result = repair_json(content)
        self.assertEqual(json.loads(result), {"reasoning": "prose", "response": "hello"})

    def test_duplicate_json_blocks(self):
        # This simulates the "Extra data: line 2 column 1" issue where two complete blocks are returned
        content = '{"reasoning": "first", "response": "one"}\n{"reasoning": "second", "response": "two"}'
        result = repair_json(content)
        self.assertEqual(json.loads(result), {"reasoning": "first", "response": "one"})

    def test_duplicate_json_blocks_with_markdown(self):
        content = '```json\n{"reasoning": "first", "response": "one"}\n```\n```json\n{"reasoning": "second", "response": "two"}\n```'
        result = repair_json(content)
        self.assertEqual(json.loads(result), {"reasoning": "first", "response": "one"})

    def test_trailing_garbage(self):
        content = '{"reasoning": "garbage", "response": "hello"}some extra text'
        result = repair_json(content)
        self.assertEqual(json.loads(result), {"reasoning": "garbage", "response": "hello"})

    def test_unrepairable_malformed_json(self):
        # A completely malformed string should fall back gracefully (not crash the repair function)
        content = 'not json at all'
        result = repair_json(content)
        self.assertEqual(result, 'not json at all')

if __name__ == "__main__":
    unittest.main()
