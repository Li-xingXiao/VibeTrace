import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "skills/claude-vibe-heatmap/scripts/vibe_heatmap.py"
SPEC = importlib.util.spec_from_file_location("vibe_heatmap", SCRIPT)
VIBE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = VIBE
SPEC.loader.exec_module(VIBE)


class CodexTokenUsageTest(unittest.TestCase):
    def test_ignores_invalid_utf8_in_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history = Path(temp_dir) / "history.jsonl"
            history.write_bytes(b'{"ts": 1, "session_id": "x", "text": "\xff"}\n')

            events = VIBE.load_codex_events(history, VIBE.resolve_tz("UTC"))

        self.assertEqual(len(events), 1)

    def test_groups_last_token_usage_by_model_without_counting_cache_twice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = Path(temp_dir) / "2026/08/rollout.jsonl"
            session.parent.mkdir(parents=True)
            session.write_text("\n".join([
                json.dumps({"type": "turn_context", "payload": {"model": "gpt-5.6-terra"}}),
                json.dumps({"type": "event_msg", "payload": {"info": {"last_token_usage": {"input_tokens": 100, "cached_input_tokens": 60, "cache_write_input_tokens": 10, "output_tokens": 7}}}}),
                json.dumps({"type": "turn_context", "payload": {"model": "gpt-5.6-sol"}}),
                json.dumps({"type": "event_msg", "payload": {"info": {"last_token_usage": {"input_tokens": 20, "cached_input_tokens": 0, "cache_write_input_tokens": 0, "output_tokens": 3}}}}),
            ]), encoding="utf-8")

            usage = VIBE.load_codex_session_token_usage(Path(temp_dir), 2026)

        self.assertEqual(usage["gpt-5.6-terra"], {
            "inputTokens": 30, "outputTokens": 7,
            "cacheReadInputTokens": 60, "cacheCreationInputTokens": 10,
        })
        self.assertEqual(usage["gpt-5.6-sol"]["inputTokens"], 20)
        self.assertEqual(usage["gpt-5.6-sol"]["outputTokens"], 3)
