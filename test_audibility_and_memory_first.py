"""
Test Suite: Audibility Check and Memory-First Protocol Verification
Validates that:
1. Queries like "can you hear me" or "am i audible" route to SYSTEM_AUDIBILITY_CHECK.
2. Microphone and speaker hardware diagnostics inspect audio input and output devices.
3. Neither Gemini nor Groq APIs are called for audibility checks.
4. Memory-First protocol answers known queries from memory before resorting to LLM APIs.
"""

import unittest
from unittest.mock import patch, MagicMock
from brain.intent_router import route_intent, IntentType
from memory.memory_manager import MemoryManager
from brain.conversation import generate_ai_response
from neura import check_microphone_and_speaker_status, execute_audibility_check_intent, ask_neura


class TestAudibilityRouting(unittest.TestCase):
    def test_audibility_intent_variations(self):
        test_queries = [
            "can you hear me",
            "am i audible",
            "are you able to hear me",
            "can you hear my voice",
            "can you hear properly or not",
            "can you hear me or am i audible",
            "check microphone and speaker is working properly or not",
            "is my microphone working",
            "check microphone",
            "check speaker",
            "am i audible to you",
            "can you listen to me",
            "check if you can hear me"
        ]
        for query in test_queries:
            with self.subTest(query=query):
                intent, meta = route_intent(query)
                self.assertEqual(
                    intent,
                    IntentType.SYSTEM_AUDIBILITY_CHECK,
                    f"Query '{query}' should route to SYSTEM_AUDIBILITY_CHECK but got '{intent}'"
                )


class TestAudioHardwareDiagnostic(unittest.TestCase):
    def test_check_microphone_and_speaker_status_returns_valid_structure(self):
        healthy, details, speech = check_microphone_and_speaker_status()
        self.assertIsInstance(healthy, bool)
        self.assertIn("microphone", details)
        self.assertIn("speaker", details)
        self.assertIn("can_hear", details)
        self.assertIn("can_speak", details)

        mic = details["microphone"]
        spk = details["speaker"]
        self.assertIn("name", mic)
        self.assertIn("healthy", mic)
        self.assertIn("name", spk)
        self.assertIn("volume", spk)
        self.assertIn("is_muted", spk)

        # Speech response should contain diagnostic details and confirmation
        self.assertIsInstance(speech, str)
        self.assertTrue(len(speech) > 10)
        self.assertTrue(
            "hear" in speech.lower() or "microphone" in speech.lower() or "speaker" in speech.lower()
        )

    def test_execute_audibility_check_intent_success(self):
        handled, msg = execute_audibility_check_intent(IntentType.SYSTEM_AUDIBILITY_CHECK)
        self.assertTrue(handled)
        self.assertIsInstance(msg, str)
        self.assertTrue("microphone" in msg.lower() or "hear" in msg.lower())


class TestMemoryFirstAndZeroApiCalls(unittest.TestCase):
    @patch("brain.conversation.gemini_model")
    @patch("brain.conversation.groq_client")
    def test_audibility_zero_api_calls_in_conversation(self, mock_groq, mock_gemini):
        """Even if generate_ai_response is directly called with audibility query, 0 API calls happen."""
        mem_mgr = MemoryManager()
        response = generate_ai_response("can you hear me or am i audible", mem_mgr)
        
        # Verify neither model nor client was invoked
        if mock_gemini:
            mock_gemini.generate_content.assert_not_called()
        if mock_groq:
            mock_groq.chat.completions.create.assert_not_called()
        
        self.assertIn("hear", response.lower())

    @patch("brain.conversation.gemini_model")
    @patch("brain.conversation.groq_client")
    def test_memory_first_known_facts_zero_api_calls(self, mock_groq, mock_gemini):
        """When memory has user facts or preferences, return from memory without calling LLM."""
        mem_mgr = MemoryManager()
        mem_mgr.add_fact("name", "Rohit")
        mem_mgr.add_fact("profession", "Software Architect")

        resp_name = generate_ai_response("what is my name", mem_mgr)
        self.assertIn("Rohit", resp_name)

        resp_prof = generate_ai_response("what is my profession", mem_mgr)
        self.assertIn("Software Architect", resp_prof)

        # Verify 0 API calls occurred
        if mock_gemini:
            mock_gemini.generate_content.assert_not_called()
        if mock_groq:
            mock_groq.chat.completions.create.assert_not_called()

    @patch("brain.conversation.gemini_model")
    @patch("brain.conversation.groq_client")
    def test_ask_neura_audibility_zero_api_calls(self, mock_groq, mock_gemini):
        """ask_neura intercepts audibility checks immediately with zero LLM API calls."""
        with patch("neura.speak") as mock_speak:
            res = ask_neura("can you hear me")
            self.assertTrue(len(res) > 0)
            self.assertTrue("hear" in res.lower() or "microphone" in res.lower())

            res2 = ask_neura("am i audible")
            self.assertTrue(len(res2) > 0)
            self.assertTrue("hear" in res2.lower() or "audible" in res2.lower() or "microphone" in res2.lower())

        if mock_gemini:
            mock_gemini.generate_content.assert_not_called()
        if mock_groq:
            mock_groq.chat.completions.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
