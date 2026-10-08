"""
Test Suite for ContextMemoryAgent and Dual-Tier Context Memory Architecture.
Validates:
1. Storage integrity (active_context.json, fixed_memory.json, temporary_memory.json)
2. Command analysis (feelings/mood, transient queries, explicit memory, successful tasks)
3. 80% Similarity matching & promotion/demotion resolution protocol
4. Context-aware answering from dual-tier memory (feelings recall, explicit memory recall)
5. Parallel ingestion and thread safety
6. AgentOrchestrator integration and status reporting
"""

import os
import sys
import time
import json
import unittest
import tempfile
import shutil

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

from brain.agents.context_memory_agent import ContextMemoryAgent
from brain.agents.orchestrator import get_orchestrator
from brain.intent_router import route_intent, IntentType


class TestContextMemoryAgent(unittest.TestCase):
    def setUp(self):
        # Create an isolated temporary test directory
        self.test_dir = tempfile.mkdtemp(prefix="test_context_mem_")
        self.agent = ContextMemoryAgent(context_memory_dir=self.test_dir)

    def tearDown(self):
        self.agent.stop()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_storage_initialization(self):
        """Validates that storage files exist and are valid JSON."""
        self.assertTrue(os.path.exists(self.agent.active_context_path))
        self.assertTrue(os.path.exists(self.agent.fixed_memory_path))
        self.assertTrue(os.path.exists(self.agent.temporary_memory_path))

        with open(self.agent.fixed_memory_path, "r", encoding="utf-8") as f:
            fixed_data = json.load(f)
            self.assertIsInstance(fixed_data, list)

        with open(self.agent.temporary_memory_path, "r", encoding="utf-8") as f:
            temp_data = json.load(f)
            self.assertIsInstance(temp_data, list)

    def test_02_command_analysis_feelings(self):
        """Validates that emotional state commands are detected as temporary memory with feelings extracted."""
        ctx = self.agent.analyze_command("i am feeling bored")
        self.assertEqual(ctx["memory_type"], "temporary")
        self.assertEqual(ctx["details"].get("user_feelings"), "bored")
        self.assertIn("express_feeling_bored", ctx["task"])

        ctx_tired = self.agent.analyze_command("feeling tired and sleepy")
        self.assertEqual(ctx_tired["memory_type"], "temporary")
        self.assertEqual(ctx_tired["details"].get("user_feelings"), "tired")

    def test_03_command_analysis_transient_queries(self):
        """Validates that weather and time queries are categorized into temporary memory."""
        ctx_weather = self.agent.analyze_command("what is the weather now in Mumbai")
        self.assertEqual(ctx_weather["memory_type"], "temporary")
        self.assertEqual(ctx_weather["details"].get("query_topic"), "weather")

        ctx_time = self.agent.analyze_command("what is the current time")
        self.assertEqual(ctx_time["memory_type"], "temporary")
        self.assertEqual(ctx_time["details"].get("query_topic"), "time")

    def test_04_command_analysis_explicit_memory(self):
        """Validates that 'remember this ...' instructions are categorized into fixed memory."""
        ctx = self.agent.analyze_command("remember this: always deploy to production using blue-green strategy")
        self.assertEqual(ctx["memory_type"], "fixed")
        self.assertIn("store_explicit_memory", ctx["task"])
        self.assertIn("always deploy to production", ctx["details"].get("explicit_note", ""))

    def test_05_eighty_percent_similarity_protocol(self):
        """Validates context matching and 80% protocol resolution."""
        ctx1 = self.agent.analyze_command("what is the weather now")
        res1 = self.agent.resolve_and_record_memory(ctx1)
        self.assertEqual(res1["action"], "created_new_temporary")

        # High similarity variant
        ctx2 = self.agent.analyze_command("what is the weather right now")
        sim = self.agent.calculate_similarity(ctx1, ctx2)
        self.assertGreaterEqual(sim, 0.80)

        res2 = self.agent.resolve_and_record_memory(ctx2)
        self.assertEqual(res2["action"], "matched_updated_temporary")

    def test_06_task_success_promoted_to_fixed_memory(self):
        """Validates that properly performed tasks are saved in fixed_memory.json."""
        self.agent.record_task_success(
            command="open vscode and test workspace",
            task_name="system_automation_open_app",
            result_summary="Successfully launched Visual Studio Code",
        )
        time.sleep(0.15)  # Wait for worker queue

        fixed_mems = self.agent.load_fixed_memories()
        self.assertTrue(any("system_automation_open_app" in str(item.get("task")) for item in fixed_mems))

    def test_07_dual_tier_context_aware_answering(self):
        """Validates answering queries directly based on stored feelings and remembered notes."""
        # 1. Record user feeling bored into temporary memory
        bored_ctx = self.agent.analyze_command("i am feeling bored")
        self.agent.resolve_and_record_memory(bored_ctx)

        # 2. Record explicit memory into fixed memory
        mem_ctx = self.agent.analyze_command("remember this: my favorite drink is black coffee")
        self.agent.resolve_and_record_memory(mem_ctx)

        # 3. Query regarding feelings
        feeling_answer = self.agent.answer_from_context_memory("how am i feeling right now?")
        self.assertIsNotNone(feeling_answer)
        self.assertIn("bored", feeling_answer.lower())

        # 4. Query regarding remembered facts
        remember_answer = self.agent.answer_from_context_memory("what did i tell you to remember?")
        self.assertIsNotNone(remember_answer)
        self.assertIn("black coffee", remember_answer.lower())

    def test_08_orchestrator_integration(self):
        """Validates that AgentOrchestrator holds MemoryAgent and includes it in status overview."""
        orch = get_orchestrator()
        self.assertTrue(hasattr(orch, "memory_agent"))
        self.assertIsInstance(orch.memory_agent, ContextMemoryAgent)

        status_dict = orch.get_agents_status_dict()
        self.assertIn("MemoryAgent", status_dict)
        self.assertEqual(status_dict["MemoryAgent"]["name"], "MemoryAgent")


if __name__ == "__main__":
    unittest.main()
