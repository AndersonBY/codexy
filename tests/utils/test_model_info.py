import sys
import unittest
from io import StringIO

from codexy.utils.model_info import DEFAULT_MAX_TOKENS, MODEL_MAX_TOKENS, get_model_max_tokens


class TestGetModelMaxTokens(unittest.TestCase):
    def test_known_model_names(self):
        self.assertEqual(get_model_max_tokens("gpt-4"), MODEL_MAX_TOKENS["gpt-4"])
        self.assertEqual(get_model_max_tokens("gpt-3.5-turbo-16k"), MODEL_MAX_TOKENS["gpt-3.5-turbo-16k"])
        self.assertEqual(get_model_max_tokens("o4-mini"), MODEL_MAX_TOKENS["o4-mini"])
        self.assertEqual(get_model_max_tokens("gpt-4-turbo"), MODEL_MAX_TOKENS["gpt-4-turbo"])
        self.assertEqual(get_model_max_tokens("gpt-4-32k"), MODEL_MAX_TOKENS["gpt-4-32k"])

    def test_model_name_with_known_key_prefix(self):
        # Test variants that should match a more general key due to prefix matching logic
        self.assertEqual(get_model_max_tokens("gpt-4-turbo-preview"), MODEL_MAX_TOKENS["gpt-4-turbo"])
        self.assertEqual(get_model_max_tokens("gpt-4-0125-preview"), MODEL_MAX_TOKENS["gpt-4-turbo"])
        self.assertEqual(get_model_max_tokens("gpt-4-1106-preview"), MODEL_MAX_TOKENS["gpt-4-turbo"])
        self.assertEqual(get_model_max_tokens("custom-gpt-4-model"), MODEL_MAX_TOKENS["gpt-4"])
        self.assertEqual(get_model_max_tokens("gpt-3.5-turbo-instruct"), 4096)
        self.assertEqual(get_model_max_tokens("my-o4-mini-variant"), MODEL_MAX_TOKENS["o4-mini"])

    def test_unknown_model_name(self):
        original_stderr = sys.stderr
        sys.stderr = captured_stderr = StringIO()
        try:
            self.assertEqual(get_model_max_tokens("unknown-model-xyz"), DEFAULT_MAX_TOKENS)
            self.assertIn("Warning: Unknown model name 'unknown-model-xyz'", captured_stderr.getvalue())
        finally:
            sys.stderr = original_stderr

    def test_order_of_checking(self):
        # Ensure that "gpt-4-turbo" is checked before "gpt-4"
        self.assertEqual(get_model_max_tokens("gpt-4-turbo-specific-variant"), MODEL_MAX_TOKENS["gpt-4-turbo"])
        # Ensure "gpt-4-32k" is checked before "gpt-4"
        self.assertEqual(get_model_max_tokens("gpt-4-32k-specific-variant"), MODEL_MAX_TOKENS["gpt-4-32k"])
        # Ensure "gpt-3.5-turbo-16k" is checked before "gpt-3.5-turbo"
        self.assertEqual(get_model_max_tokens("gpt-3.5-turbo-16k-variant"), MODEL_MAX_TOKENS["gpt-3.5-turbo-16k"])


if __name__ == "__main__":
    unittest.main()
