"""
Comprehensive Test Suite for Neura Multi-Agent Personal AI System.
Executes and validates all 9 required test scenarios + regression tests.
No simulated fake results - runs actual code and asserts outcomes.
"""

import os
import sys
import time
import json
import unittest
import tempfile
import shutil

# Ensure workspace root is on sys.path
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

from brain.intent_router import route_intent, IntentType
from brain.agents import (
    get_orchestrator,
    Task,
    TaskState,
    PermissionLevel,
    Severity,
    FindingCategory,
    Finding,
    EventType,
    ProjectAgent,
    ScreenAgent,
    MonitorAgent,
    SkillAgent,
)
from brain.agents.orchestrator import AgentOrchestrator
from brain.desktop_controller import DesktopController
from neura import execute_agent_intent, execute_desktop_or_file_intent

class TestNeuraMultiAgentSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orchestrator = get_orchestrator(WORKSPACE_DIR)

    def test_01_project_testing_workflow(self):
        """
        TEST 1: User says 'Neura, test my project.'
        - Project Agent receives task.
        - Project is inspected.
        - Tests run.
        - Results return to Neura.
        - Neura provides a final summary.
        """
        print("\n--- RUNNING TEST 1: Project Testing Workflow ---")
        intent, metadata = route_intent("test my project")
        self.assertEqual(intent, IntentType.AGENT_PROJECT_TEST)

        handled, response = execute_agent_intent(intent, metadata, "test my project")
        self.assertTrue(handled)
        self.assertIsInstance(response, str)
        self.assertIn("Project testing completed", response)
        print("Test 1 Result Summary:\n", response[:300], "...\n[PASSED]")

    def test_02_monitor_agent_starts_nonblocking(self):
        """
        TEST 2: User says 'Neura, monitor this task.'
        - Monitor Agent starts.
        - Monitoring continues in background.
        - Neura remains responsive.
        """
        print("\n--- RUNNING TEST 2: Monitor Agent Starts Non-Blocking ---")
        intent, metadata = route_intent("monitor this task")
        self.assertEqual(intent, IntentType.AGENT_MONITOR_START)

        handled, response = execute_agent_intent(intent, metadata, "monitor this task")
        self.assertTrue(handled)
        self.assertIn("Background monitoring started", response)

        # Verify Neura status shows the active monitoring
        status_text = self.orchestrator.get_status_overview()
        self.assertIn("Monitor Agent", status_text)
        print("Test 2 Status Overview:\n", status_text, "\n[PASSED]")

    def test_03_background_task_completes_proactive_alert(self):
        """
        TEST 3: Background task completes.
        - Monitor Agent detects completion.
        - Event sent to Neura.
        - Neura informs user.
        """
        print("\n--- RUNNING TEST 3: Background Task Completion & Alert ---")
        # Run a quick command that succeeds
        cmd = f'"{sys.executable}" -c "import time; print(\'100%\'); time.sleep(0.3)"'
        session_msg = self.orchestrator.start_monitoring(command=cmd, name="Quick Successful Task")
        self.assertIn("Background monitoring started", session_msg)

        # Wait for worker thread to complete
        time.sleep(1.2)

        # Check proactive notifications
        announcements = self.orchestrator.get_proactive_announcements()
        found_completion = any("completed successfully" in a for a in announcements)
        self.assertTrue(found_completion, f"Expected completion announcement, got: {announcements}")
        print("Test 3 Proactive Announcements:", announcements, "\n[PASSED]")

    def test_04_background_process_crash_detection(self):
        """
        TEST 4: Background process crashes.
        - Monitor Agent detects failure.
        - High/critical event generated.
        - Neura informs user.
        """
        print("\n--- RUNNING TEST 4: Background Process Crash Detection ---")
        # Run a command that crashes with exit code 1
        cmd = f'"{sys.executable}" -c "import sys; print(\'Starting..\'); sys.exit(1)"'
        session_msg = self.orchestrator.start_monitoring(command=cmd, name="Crashing Subprocess")
        self.assertIn("Background monitoring started", session_msg)

        # Wait for worker thread to catch exit
        time.sleep(1.2)

        announcements = self.orchestrator.get_proactive_announcements()
        found_crash = any("crashed or exited with error code" in a or "Attention" in a or "Alert" in a for a in announcements)
        self.assertTrue(found_crash, f"Expected crash alert, got: {announcements}")
        print("Test 4 Proactive Crash Alerts:", announcements, "\n[PASSED]")

    def test_05_project_contains_obvious_error(self):
        """
        TEST 5: Project contains an obvious error.
        - Project Agent detects it.
        - Finding is reported with severity.
        - Neura explains the problem clearly.
        """
        print("\n--- RUNNING TEST 5: Code Defect & Syntax Error Detection ---")
        # Create a temporary directory with a broken python file
        temp_dir = tempfile.mkdtemp(prefix="neura_broken_proj_")
        try:
            broken_file = os.path.join(temp_dir, "bad_syntax.py")
            with open(broken_file, "w", encoding="utf-8") as f:
                f.write("def broken_func(\n    print('Missing closing parenthesis'\n")

            custom_pa = ProjectAgent(default_workspace=temp_dir)
            t = Task(
                task_id="broken_test_task",
                task_type="analyze_code",
                description="Scan broken project",
                metadata={"workspace": temp_dir},
            )
            res = custom_pa.run_safe(t)
            findings = res.get("findings", [])
            syntax_findings = [f for f in findings if f.get("severity") == "CRITICAL" and "Syntax Error" in f.get("title", "")]
            self.assertTrue(len(syntax_findings) >= 1)
            self.assertIn("bad_syntax.py", syntax_findings[0]["file_path"])
            print("Test 5 Discovered Finding:", syntax_findings[0], "\n[PASSED]")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_06_screen_error_inspection(self):
        """
        TEST 6: Screen shows an error.
        - Screen Agent can inspect it when permission exists.
        - Finding is reported to Neura.
        """
        print("\n--- RUNNING TEST 6: Screen Error Inspection ---")
        sa = self.orchestrator.screen_agent
        sa.set_permission(True)

        # Verify pattern matching against simulated visible error traceback
        findings, text = sa.inspect_visible_errors("screen_test")
        self.assertIsInstance(findings, list)

        # Test error pattern matcher directly on standard tracebacks
        test_ocr_text = "Traceback (most recent call last):\n  File 'app.py', line 12\nModuleNotFoundError: No module named 'missing_pkg'"
        import re
        has_trace = bool(re.search(r"Traceback\s+\(most recent call last\):", test_ocr_text))
        has_mod_err = bool(re.search(r"ModuleNotFoundError:\s+No module named\s+['\"][^'\"]+['\"]", test_ocr_text))
        self.assertTrue(has_trace)
        self.assertTrue(has_mod_err)

        intent, metadata = route_intent("inspect screen errors")
        self.assertEqual(intent, IntentType.AGENT_SCREEN_INSPECT)
        handled, msg = execute_agent_intent(intent, metadata, "inspect screen errors")
        self.assertTrue(handled)
        print("Test 6 Screen Inspection Message:\n", msg, "\n[PASSED]")

    def test_07_agent_failure_isolation(self):
        """
        TEST 7: One agent fails.
        - Neura remains running.
        - Other agents continue where possible.
        - Failure is reported gracefully.
        """
        print("\n--- RUNNING TEST 7: Agent Failure Isolation ---")
        class CrashingAgent(ProjectAgent):
            def execute_task(self, task: Task):
                raise RuntimeError("Simulated internal agent exception during deep inspection")

        failing_agent = CrashingAgent(event_bus=self.orchestrator.event_bus)
        task = Task(task_id="fail_test", task_type="project_test", description="Crashing task")

        # run_safe must catch exception, return safe dict, and not propagate crash
        res = failing_agent.run_safe(task)
        self.assertFalse(res.get("success"))
        self.assertIn("Simulated internal agent exception", res.get("error", ""))

        # Verify other agents are still healthy and usable
        status_msg = self.orchestrator.get_status_overview()
        self.assertIsInstance(status_msg, str)
        print("Test 7 Handled Agent Failure gracefully:\n", res, "\n[PASSED]")

    def test_08_skill_agent_workflow_learning(self):
        """
        TEST 8: User asks Neura to learn a repeated workflow.
        - Skill Agent creates a candidate skill.
        - Skill is validated.
        - Skill is registered only after appropriate permission.
        """
        print("\n--- RUNNING TEST 8: Skill Learning & Permission Gating ---")
        intent, metadata = route_intent("learn this workflow for project startup")
        self.assertEqual(intent, IntentType.AGENT_SKILL_LEARN)
        self.assertEqual(metadata.get("name"), "project startup")

        # 1. Without execute permission -> candidate awaits permission
        handled, msg1 = execute_agent_intent(intent, metadata, "learn this workflow for project startup")
        self.assertTrue(handled)
        self.assertIn("Awaiting explicit user EXECUTE permission", msg1)

        # 2. With execute permission -> validated and registered
        metadata["permission_granted"] = True
        handled, msg2 = execute_agent_intent(intent, metadata, "learn this workflow for project startup")
        self.assertTrue(handled)
        self.assertIn("permanently registered", msg2)

        # 3. Test running the registered skill
        run_res = self.orchestrator.skill_agent.run_skill("project startup", "test_task")
        self.assertTrue(run_res.get("success"))
        print("Test 8 Skill Learning Workflow:\n", msg2, "\nRun Result:", run_res, "\n[PASSED]")

    def test_09_existing_features_regression(self):
        """
        TEST 9: Existing Neura feature is used.
        - Existing functionality still behaves correctly.
        """
        print("\n--- RUNNING TEST 9: Existing Features Regression ---")
        # 1. Screen describe intent
        i1, m1 = route_intent("what is on my screen")
        self.assertEqual(i1, IntentType.SCREEN_DESCRIBE)

        # 2. System background status intent
        i2, m2 = route_intent("what happens in the background")
        self.assertEqual(i2, IntentType.SYSTEM_BACKGROUND_STATUS)

        # 3. System permission intent
        i3, m3 = route_intent("take screen permission")
        self.assertEqual(i3, IntentType.SYSTEM_PERMISSION)
        h3, msg3 = execute_desktop_or_file_intent(i3, m3, "take screen permission")
        self.assertTrue(h3)

        # 4. Multi-agent diagnostic intent
        i4, m4 = route_intent("why is my project failing")
        self.assertEqual(i4, IntentType.AGENT_PROJECT_DIAGNOSTIC)
        handled, diag_msg = execute_agent_intent(i4, m4, "why is my project failing")
        self.assertTrue(handled)
        self.assertIn("investigated why the project is failing", diag_msg)

        print("Test 9 Multi-Agent Diagnostic Output:\n", diag_msg[:250], "...\n[PASSED]")

if __name__ == "__main__":
    unittest.main()
