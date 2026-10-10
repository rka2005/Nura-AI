"""
Unit & Integration Tests for GPU Selection and Live Terminal Testing in Neura.
Verifies:
1. Dedicated vs System GPU auto-detection and fallback logic
2. Hardware environment variable configuration
3. Intent routing for project tests and live terminal view toggles
4. Sibling directory project resolution (e.g., Mail_automation)
5. Live terminal status bridge reporting and compute acceleration telemetry
"""

import os
import json
import unittest
from brain.hardware_manager import (
    get_hardware_gpus,
    select_compute_device,
    get_gpu_environment,
    format_compute_banner
)
from brain.intent_router import route_intent, IntentType
from brain.agents.project_agent import ProjectAgent
from brain.agents.orchestrator import get_orchestrator


class TestGpuAndLiveTerminalTesting(unittest.TestCase):

    def setUp(self):
        self.workspace = os.path.dirname(os.path.abspath(__file__))
        self.agent = ProjectAgent(default_workspace=self.workspace)

    def test_01_gpu_detection(self):
        """Verify hardware manager discovers available GPUs."""
        gpus = get_hardware_gpus()
        self.assertGreaterEqual(len(gpus), 1, "At least one GPU device must be detected on system")
        
        # Verify detected device properties
        has_dedicated = any(d.get("is_dedicated") for d in gpus)
        has_system = any(not d.get("is_dedicated") for d in gpus)

        # On this machine, NVIDIA RTX 4050 is dedicated, Intel UHD is system
        for g in gpus:
            self.assertIn("name", g)
            self.assertIn("is_dedicated", g)
            self.assertIn("type", g)

    def test_02_gpu_selection_dedicated_preferred_and_fallback(self):
        """Verify select_compute_device returns dedicated GPU when preferred, or falls back to system GPU."""
        # 1. Prefer dedicated
        pref_dev = select_compute_device(prefer_dedicated=True)
        self.assertIsNotNone(pref_dev)
        all_gpus = get_hardware_gpus()
        has_dedicated = any(g.get("is_dedicated") for g in all_gpus)
        if has_dedicated:
            self.assertTrue(pref_dev["is_dedicated"])
            self.assertEqual(pref_dev["device_type"], "DEDICATED")

        # 2. Prefer system (prefer_dedicated=False)
        sys_dev = select_compute_device(prefer_dedicated=False)
        self.assertIsNotNone(sys_dev)
        self.assertFalse(sys_dev["is_dedicated"])
        self.assertEqual(sys_dev["device_type"], "SYSTEM_DEFAULT")

        # 3. Environment variables
        env = get_gpu_environment(pref_dev)
        self.assertIn("NEURA_COMPUTE_DEVICE", env)
        self.assertIn("NEURA_GPU_TYPE", env)

    def test_03_compute_banner_formatting(self):
        """Verify visual ASCII/telemetry banner formatting for live console."""
        dev = select_compute_device(prefer_dedicated=True)
        banner = format_compute_banner(dev, "Test Task Suite")
        self.assertIn("NEURA HARDWARE ACCELERATION", banner)
        self.assertIn(dev["name"], banner)
        self.assertIn("Test Task Suite", banner)

    def test_04_intent_routing_with_named_project_and_terminal_views(self):
        """Verify routing for commands like 'test and debug project Mail_automation' and terminal views."""
        queries = [
            ("test and debug project Mail_automation", IntentType.AGENT_PROJECT_TEST, "Mail_automation"),
            ("test and debug project 'Mail_automation'", IntentType.AGENT_PROJECT_TEST, "Mail_automation"),
            ("test project Mail_automation", IntentType.AGENT_PROJECT_TEST, "Mail_automation"),
            ("test project 'Mail_automation'", IntentType.AGENT_PROJECT_TEST, "Mail_automation"),
            ("show live terminal", IntentType.AGENT_TERMINAL_VIEW_SHOW, None),
            ("open terminal view", IntentType.AGENT_TERMINAL_VIEW_SHOW, None),
            ("close live terminal", IntentType.AGENT_TERMINAL_VIEW_CLOSE, None),
            ("hide terminal view", IntentType.AGENT_TERMINAL_VIEW_CLOSE, None),
        ]

        for query, expected_intent, expected_name in queries:
            intent, meta = route_intent(query)
            self.assertEqual(intent, expected_intent, f"Query '{query}' failed intent check")
            if expected_name:
                self.assertEqual(meta.get("target_name"), expected_name, f"Target name mismatch for '{query}'")

    def test_05_sibling_project_resolution(self):
        """Verify ProjectAgent resolves sibling projects like Mail_automation."""
        parent_dir = os.path.dirname(self.workspace)
        mail_auto_path = os.path.join(parent_dir, "Mail_automation")

        if os.path.exists(mail_auto_path):
            resolved = self.agent.resolve_workspace_target("Mail_automation")
            self.assertEqual(os.path.normpath(resolved), os.path.normpath(mail_auto_path))

    def test_06_live_terminal_status_bridge(self):
        """Verify status_bridge.json receives live_terminal telemetry updates."""
        bridge_file = os.path.join(self.workspace, "status_bridge.json")
        dev = select_compute_device(prefer_dedicated=True)

        self.agent._update_live_terminal_bridge(
            active=True,
            title="Unit Test Runner",
            command="pytest test_sample.py",
            compute_device=dev["summary"],
            status="RUNNING",
            lines=["Line 1", "Line 2", "Line 3"],
            exit_code=None
        )

        self.assertTrue(os.path.exists(bridge_file))
        with open(bridge_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("live_terminal", data)
        term_data = data["live_terminal"]
        self.assertTrue(term_data["active"])
        self.assertEqual(term_data["compute_device"], dev["summary"])
        self.assertEqual(term_data["status"], "RUNNING")
        self.assertEqual(term_data["last_lines"], ["Line 1", "Line 2", "Line 3"])

        # Reset active status
        self.agent._update_live_terminal_bridge(
            active=False,
            title="Unit Test Completed",
            command="pytest test_sample.py",
            compute_device=dev["summary"],
            status="PASSED",
            lines=["Line 1", "Line 2", "Line 3", "PASSED"],
            exit_code=0
        )

    def test_07_test_file_records_compute_acceleration(self):
        """Verify test_file includes compute device telemetry and hardware acceleration report."""
        res = self.agent.test_file("brain/hardware_manager.py", terminal_allowed=False, prefer_dedicated_gpu=True)
        self.assertTrue(res["success"])
        self.assertIn("compute_device", res)
        self.assertIn("Compute Acceleration", res["full_report"])
        self.assertTrue(os.path.exists(res["report_file"]))


if __name__ == "__main__":
    unittest.main()
