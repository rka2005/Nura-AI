"""
Unit & Integration Tests for Neura Project Testing & Terminal Permission System.
Verifies:
1. Intent routing for all user variations (screen project, specific file, named project, current project)
2. Screen target resolution (detect_target_from_screen)
3. Automated traceback debugger (debug_execution_failure)
4. File testing in General (Static) mode vs Dynamic Terminal mode
5. Project testing in General (Static) mode vs Dynamic Terminal mode
6. Terminal permission gating & report generation
7. Orchestrator integration and context memory categorization
"""

import os
import json
import unittest
from brain.intent_router import route_intent, IntentType
from brain.desktop_controller import DesktopController
from brain.agents.project_agent import ProjectAgent
from brain.agents.orchestrator import AgentOrchestrator, get_orchestrator
from brain.agents.task_manager import Task, PermissionLevel

class TestProjectTestingAndTerminalPermission(unittest.TestCase):

    def setUp(self):
        self.workspace = os.path.dirname(os.path.abspath(__file__))
        self.agent = ProjectAgent(default_workspace=self.workspace)
        self.desktop_ctrl = DesktopController()

    def test_01_intent_routing_variations(self):
        """Verify all requested query variations correctly route to AGENT_PROJECT_TEST with metadata."""
        test_cases = [
            ("can you please test this current project", "project", None, False, None),
            ("can you test this whatsapp boat project", "named_project", "whatsapp boat", False, None),
            ("test current project that you can see", "screen", "screen_project", True, None),
            ("test current project on the screen", "screen", "screen_project", True, None),
            ("test what you see on the screen", "screen", "screen_project", True, None),
            ("test specific file test_screen_vision.py", "file", "test_screen_vision.py", False, None),
            ("test file neura.py", "file", "neura.py", False, None),
            ("test this file", "file", "current_file", True, None),
            ("test this project with terminal access", "project", "current_project", False, True),
            ("test this project without terminal", "project", "current_project", False, False),
        ]

        for query, expected_type, expected_name, expected_screen, expected_perm in test_cases:
            intent, meta = route_intent(query)
            self.assertEqual(intent, IntentType.AGENT_PROJECT_TEST, f"Query '{query}' failed to route to AGENT_PROJECT_TEST")
            if expected_type:
                self.assertEqual(meta.get("target_type"), expected_type, f"Target type mismatch for '{query}'")
            if expected_name:
                self.assertEqual(meta.get("target_name"), expected_name, f"Target name mismatch for '{query}'")
            if expected_screen is not None:
                self.assertEqual(meta.get("from_screen"), expected_screen, f"Screen flag mismatch for '{query}'")
            if expected_perm is not None:
                self.assertEqual(meta.get("terminal_permission_granted"), expected_perm, f"Permission flag mismatch for '{query}'")

    def test_02_screen_target_detection(self):
        """Verify detect_target_from_screen parses window titles properly."""
        target = self.desktop_ctrl.detect_target_from_screen()
        self.assertIsInstance(target, dict)
        self.assertIn("project_name", target)
        self.assertIn("file_name", target)
        self.assertIn("window_title", target)

    def test_03_automated_traceback_debugger(self):
        """Verify automated debugger extracts exception details, root causes, and fixes."""
        sample_traceback = """
Traceback (most recent call last):
  File "D:\\VS Code\\Neura_test_ai\\test_sample.py", line 42, in test_something
    import non_existent_super_library
ModuleNotFoundError: No module named 'non_existent_super_library'
"""
        diag = self.agent.debug_execution_failure(sample_traceback, exit_code=1, target_file="test_sample.py")
        self.assertEqual(diag["error_type"], "ModuleNotFoundError")
        self.assertEqual(diag["failing_line"], 42)
        self.assertEqual(diag["failing_file"], "test_sample.py")
        self.assertIn("non_existent_super_library", diag["root_cause"])
        self.assertIn("pip install", diag["suggested_fix"])

    def test_04_specific_file_general_test(self):
        """Verify file testing in General Static mode (terminal_allowed=False)."""
        res = self.agent.test_file("brain/intent_router.py", terminal_allowed=False)
        self.assertTrue(res["success"])
        self.assertFalse(res["terminal_allowed"])
        self.assertIn("Project testing completed", res["summary"])
        self.assertIn("General Static Test", res["full_report"])
        self.assertFalse(res["exec_result"]["executed"])
        self.assertTrue(os.path.exists(res["report_file"]))

    def test_05_specific_file_terminal_test(self):
        """Verify file testing in Dynamic Terminal mode (terminal_allowed=True)."""
        res = self.agent.test_file("test_voice.py", terminal_allowed=True)
        self.assertTrue(res["success"])
        self.assertTrue(res["terminal_allowed"])
        self.assertIn("Project testing completed", res["summary"])
        self.assertIn("Dynamic Terminal Test", res["full_report"])
        self.assertTrue(res["exec_result"]["executed"])
        self.assertIsNotNone(res["exec_result"]["exit_code"])
        self.assertTrue(os.path.exists(res["report_file"]))

    def test_06_project_testing_general_mode_skips_subprocess(self):
        """Verify project testing in General Static mode skips running terminal test subprocesses."""
        res = self.agent.test_project_with_permission(self.workspace, terminal_allowed=False)
        self.assertTrue(res["success"])
        self.assertFalse(res["terminal_allowed"])
        self.assertIn("Project testing completed", res["summary"])
        self.assertIn("General Static Test (Terminal Access: DENIED)", res["summary"])
        self.assertEqual(res["test_results"]["executed_suites"], 0)
        self.assertIn("skipped_reason", res["test_results"])
        self.assertTrue(os.path.exists(res["report_file"]))

    def test_07_orchestrator_integration(self):
        """Verify orchestrator coordinates test_file and test_project properly."""
        orch = get_orchestrator()
        
        # Test file through orchestrator
        file_summary = orch.test_file("brain/desktop_controller.py", terminal_allowed=False)
        self.assertIn("Project testing completed", file_summary)
        self.assertTrue(hasattr(orch, "last_test_result"))
        self.assertIn("full_report", orch.last_test_result)

        # Test project general mode through orchestrator
        proj_summary = orch.test_project(workspace=self.workspace, terminal_allowed=False)
        self.assertIn("Project testing completed", proj_summary)
        self.assertIn("General Static Test", proj_summary)

    def test_08_prompt_user_for_terminal_permission_resilience(self):
        """Verify prompt_user_for_terminal_permission executes cleanly without NameError."""
        from neura import prompt_user_for_terminal_permission, INPUT_BRIDGE_FILE

        # Test permission granted via input bridge
        with open(INPUT_BRIDGE_FILE, "w", encoding="utf-8") as f:
            json.dump(["yes"], f)
        perm = prompt_user_for_terminal_permission("test target project", timeout=1.0)
        self.assertTrue(perm)

        # Test permission denied via input bridge
        with open(INPUT_BRIDGE_FILE, "w", encoding="utf-8") as f:
            json.dump(["no"], f)
        perm = prompt_user_for_terminal_permission("test target project", timeout=1.0)
        self.assertFalse(perm)

    def test_09_execute_agent_intent_project_test(self):
        """Verify execute_agent_intent handles AGENT_PROJECT_TEST with screen target and permission."""
        from neura import execute_agent_intent
        intent, metadata = route_intent("test current project you can see")
        self.assertEqual(intent, IntentType.AGENT_PROJECT_TEST)
        self.assertTrue(metadata.get("from_screen"))

        # Test execution with terminal permission disabled (safe general test)
        metadata["terminal_permission_granted"] = False
        handled, res = execute_agent_intent(intent, metadata, "test current project you can see")
        self.assertTrue(handled)
        self.assertIn("Project testing completed", res)

    def test_10_context_memory_categorization(self):
        """Verify context memory agent categorizes project and file testing properly."""
        from brain.agents.context_memory_agent import ContextMemoryAgent
        mem_agent = ContextMemoryAgent()
        ctx = mem_agent.analyze_command("test current project you can see")
        mem_agent.stop()
        self.assertEqual(ctx["task"], "project_or_file_testing")
        self.assertEqual(ctx["type"], "code")
        self.assertEqual(ctx["name"], "test_subsystem")

if __name__ == "__main__":
    unittest.main()
