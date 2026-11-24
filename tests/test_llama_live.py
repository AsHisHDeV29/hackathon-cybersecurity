"""Opt-in smoke evaluation against an actual locally installed Llama model."""
import os
import unittest
from unittest.mock import patch

from backend.detection import analyze, model_status

@unittest.skipUnless(os.environ.get("NETRA_LIVE_TESTS") == "1", "Set NETRA_LIVE_TESTS=1 to run local model inference")
class LiveLlamaTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"NETRA_ENGINE": "llama"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.assertTrue(model_status()["model_ready"], "Local Ollama must have the configured Llama model installed")

    def check(self, text, expected, language_hint="auto"):
        result = analyze(text, language_hint)
        self.assertIsNone(result["model_error"], result)
        self.assertEqual(result["verdict"], expected, result)
        self.assertTrue(result["engine"].startswith("Llama ·"), result)
        return result

    def test_hinglish_drug_request(self):
        result = self.check("Bhai 5 gram ganja lena hai, home delivery kar doge?", "flagged", "hinglish")
        self.assertEqual(result["language"], "Hinglish")
        self.assertIn("Drugs", result["categories"])

    def test_hinglish_bank_account_rental(self):
        result = self.check("Kisi ko bank account aur ATM card kiraye par chahiye toh inbox karo", "flagged", "hinglish")
        self.assertIn("Financial fraud", result["categories"])

    def test_routine_hinglish(self):
        self.check("Yaar aaj shaam library aa jana, assignment saath mein complete karte hain", "no_flags", "hinglish")

    def test_ambiguous_hinglish(self):
        self.check("Bhai woh wala maal aa gaya, baaki baat inbox mein", "unclear", "hinglish")

    def test_hinglish_news(self):
        self.check("Aaj ki khabar: police ne drugs bechne wale ko giraftar kiya. Nasha se door raho.", "no_flags", "hinglish")

    def test_romanized_local_language(self):
        result = self.check("Vanakkam nanba, naalaikku kaalai sandhippom", "unclear")
        self.assertEqual(result["review_reason"], "unsupported_language")

if __name__ == "__main__":
    unittest.main()
