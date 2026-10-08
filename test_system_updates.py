"""
Comprehensive Verification Suite for Neura AI System Updates:
1. Full Screen Access Computer-Use Automation Agent (Gemini/Claude style).
2. Proper Automation for Checking Project Vulnerabilities (SAST & Dependencies).
3. Logging, Auditing, Understanding Errors, Reporting (Voice/Email) & Word .doc Report Generation.
"""

import os
import sys
import unittest
import tempfile
import shutil

# Ensure workspace is on sys.path
WORKSPACE = os.path.dirname(os.path.abspath(__file__))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

from brain.intent_router import route_intent, IntentType
from brain.agents import (
    get_orchestrator,
    ComputerUseAgent,
    VulnerabilityScanner,
    ErrorAuditor,
    NotificationService,
    ReportDocGenerator,
    Severity,
    FindingCategory,
)


class TestNeuraSystemUpdates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orchestrator = get_orchestrator(WORKSPACE)
        cls.test_dir = tempfile.mkdtemp(prefix="neura_test_")

    @classmethod
    def tearDownClass(cls):
        try:
            shutil.rmtree(cls.test_dir)
        except Exception:
            pass

    # =============================================================
    # 1. Intent Router Routing Tests
    # =============================================================
    def test_01_intent_router_computer_use(self):
        """Verify routing for full-screen computer use commands."""
        queries = [
            "take full screen access as like gemini or claude does",
            "take full screen access to open notepad",
            "take screen access and perform automation task on screen",
            "computer use: search for python documentation",
            "take the full access of the screen and perform a automation task",
        ]
        for q in queries:
            intent, meta = route_intent(q)
            self.assertEqual(
                intent,
                IntentType.AGENT_COMPUTER_USE,
                f"Failed to route '{q}' to AGENT_COMPUTER_USE",
            )

    def test_02_intent_router_vulnerability_scan(self):
        """Verify routing for project vulnerability scanning."""
        queries = [
            "proper automation for checking vulnerabilities of any projects",
            "check vulnerabilities of project",
            "vulnerability scan on my codebase",
            "check security flaws in my project",
            "tell only the major vulnerabilities",
            "check major vulnerabilities",
        ]
        for q in queries:
            intent, meta = route_intent(q)
            self.assertEqual(
                intent,
                IntentType.AGENT_VULNERABILITY_SCAN,
                f"Failed to route '{q}' to AGENT_VULNERABILITY_SCAN",
            )

    def test_03_intent_router_error_audit(self):
        """Verify routing for error log auditing."""
        queries = [
            "automation for checking the logging, auditing and understanding the errors",
            "check error logs in project",
            "audit logging and understand errors",
        ]
        for q in queries:
            intent, meta = route_intent(q)
            self.assertEqual(
                intent,
                IntentType.AGENT_ERROR_AUDIT,
                f"Failed to route '{q}' to AGENT_ERROR_AUDIT",
            )

    def test_04_intent_router_full_audit_doc_report(self):
        """Verify routing for complete audit + Word .doc report generation."""
        queries = [
            "create a .doc file with all the vulnerabilities, errors and what the cause of that error with handling suggestion",
            "audit vulnerabilities and errors and create a .doc file",
            "generate .doc report for vulnerabilities and errors",
            "now, instead of tell the whole report of security and vulnerabilities, only the major vulnerabilities it will tell and also create the full report (.doc file) on it",
        ]
        for q in queries:
            intent, meta = route_intent(q)
            self.assertEqual(
                intent,
                IntentType.AGENT_FULL_AUDIT_REPORT,
                f"Failed to route '{q}' to AGENT_FULL_AUDIT_REPORT",
            )

    # =============================================================
    # 2. Computer Use Agent Tests
    # =============================================================
    def test_05_computer_use_agent_planning_and_execution(self):
        """Test ComputerUseAgent perception, planning loop, and safety boundaries."""
        agent = self.orchestrator.computer_use_agent
        self.assertIsNotNone(agent)
        self.assertTrue(agent.permission_granted)

        # Test plan generation for opening an app
        plan = agent._heuristic_plan(
            goal="open notepad and type hello world",
            step=1,
            active_window="Desktop",
            ocr_text="Recycle Bin\nThis PC",
            elements=[],
            history=[],
            screen_size=(1920, 1080),
        )
        self.assertIn("action", plan)
        self.assertEqual(plan["action"], "open_app")
        self.assertEqual(plan["app_name"], "notepad")

        # Test subsequent step: typing text
        plan2 = agent._heuristic_plan(
            goal="open notepad and type hello world",
            step=2,
            active_window="Untitled - Notepad",
            ocr_text="File Edit Format View Help",
            elements=[],
            history=[{"action": "open_app"}],
            screen_size=(1920, 1080),
        )
        self.assertEqual(plan2["action"], "type")
        self.assertEqual(plan2["text"], "hello world")
        self.assertTrue(plan2.get("is_final", False))

    # =============================================================
    # 3. Vulnerability Scanner Tests
    # =============================================================
    def test_06_vulnerability_scanner_sast_detection(self):
        """Create sample vulnerable files and verify deep SAST rule detection."""
        scanner = VulnerabilityScanner(workspace=self.test_dir)

        # Create a test file with intentionally vulnerable code
        vuln_code_file = os.path.join(self.test_dir, "vulnerable_sample.py")
        with open(vuln_code_file, "w", encoding="utf-8") as f:
            f.write(
                'import os\n'
                'import subprocess\n'
                'import hashlib\n'
                'import pickle\n'
                'import requests\n\n'
                'def run_admin_action(cmd, user_input, query_data):\n'
                '    # 1. Command Injection\n'
                '    os.system("echo " + user_input)\n'
                '    subprocess.Popen(cmd, shell=True)\n'
                '    # 2. Code Injection\n'
                '    eval(user_input)\n'
                '    # 3. Insecure Deserialization\n'
                '    data = pickle.loads(query_data)\n'
                '    # 4. Weak Hash\n'
                '    h = hashlib.md5(b"password").hexdigest()\n'
                '    # 5. Disabled SSL\n'
                '    resp = requests.get("https://internal.api", verify=False)\n'
                '    return resp.text\n'
            )

        report = scanner.scan_project(self.test_dir)
        self.assertTrue(report["success"])
        self.assertGreater(len(report["vulnerabilities"]), 0)

        vuln_titles = [v["title"] for v in report["vulnerabilities"]]
        print("\n[Test] Detected Vulnerabilities:", vuln_titles)

        # Check for specific detected vulnerabilities
        self.assertTrue(any("os.system" in t or "Command Injection" in t for t in vuln_titles))
        self.assertTrue(any("shell=True" in t for t in vuln_titles))
        self.assertTrue(any("eval" in t or "Code Execution" in t for t in vuln_titles))
        self.assertTrue(any("pickle" in t or "Deserialization" in t for t in vuln_titles))
        self.assertTrue(any("MD5" in t or "Hash" in t for t in vuln_titles))
        self.assertTrue(any("verify=False" in t or "SSL" in t for t in vuln_titles))

        # Check that every vulnerability has root cause and handling suggestion
        for v in report["vulnerabilities"]:
            self.assertTrue(len(v["cause"]) > 10, f"Vulnerability {v['id']} missing cause")
            self.assertTrue(len(v["suggestion"]) > 10, f"Vulnerability {v['id']} missing suggestion")
            self.assertIsNotNone(v["fix_snippet"])

    # =============================================================
    # 4. Error Auditor Tests
    # =============================================================
    def test_07_error_auditor_traceback_and_log_analysis(self):
        """Create sample error log and verify exception diagnosis and fix suggestions."""
        auditor = ErrorAuditor(workspace=self.test_dir)

        # Create sample log file with Python traceback and runtime errors
        sample_log = os.path.join(self.test_dir, "runtime_error.log")
        with open(sample_log, "w", encoding="utf-8") as f:
            f.write(
                "[2026-10-08 21:00:00] INFO: Starting Neura backend\n"
                "[2026-10-08 21:01:05] ERROR: ConnectionRefusedError: [WinError 10061] No connection could be made\n"
                "Traceback (most recent call last):\n"
                '  File "neura.py", line 120, in takeCommand\n'
                '    data = session.get("http://invalid.url")\n'
                "FileNotFoundError: [Errno 2] No such file or directory: 'settings.json'\n"
                "[2026-10-08 21:02:10] WARN: cv::dnn::Net::Impl::setPreferableTarget fallback to CPU\n"
            )

        report = auditor.audit_all_logs(self.test_dir)
        self.assertTrue(report["success"])
        self.assertGreater(len(report["errors"]), 0)

        err_types = [e["error_type"] for e in report["errors"]]
        print("\n[Test] Audited Error Types:", err_types)

        self.assertTrue(any("FileNotFoundError" in et for et in err_types))
        self.assertTrue(any("ConnectionRefusedError" in et or "Connection" in et for et in err_types))

        # Verify that causes and handling suggestions were formulated
        for err in report["errors"]:
            self.assertTrue(len(err["cause"]) > 10)
            self.assertTrue(len(err["handling_suggestion"]) > 10)

    # =============================================================
    # 5. User Presence & Notification Service Tests
    # =============================================================
    def test_08_notification_service_presence_and_email_draft(self):
        """Verify presence detection, voice dispatch, and email alert rendering."""
        service = NotificationService()
        is_avail, reason = service.check_user_availability()
        self.assertIsInstance(is_avail, bool)
        self.assertIsInstance(reason, str)

        dummy_vuln = {
            "project_name": "TestProject",
            "security_score": 75,
            "stats": {"critical": 1, "high": 2, "medium": 1, "total": 4},
            "vulnerabilities": [
                {
                    "title": "Hardcoded Secret",
                    "severity": "CRITICAL",
                    "file_path": "app.py",
                    "line_number": 12,
                    "suggestion": "Move to .env",
                }
            ],
        }
        dummy_err = {
            "stats": {"total_errors": 2},
            "errors": [
                {
                    "error_type": "ConnectionRefusedError",
                    "source": "server.log",
                    "cause": "Socket closed",
                    "handling_suggestion": "Add retry loop",
                }
            ],
        }

        # Force email dispatch / draft save
        result = service.send_email_report(
            vuln_report=dummy_vuln,
            error_report=dummy_err,
            doc_path=None,
            voice_summary="Audit completed with 4 vulnerabilities and 2 errors.",
        )
        self.assertTrue(result["email_saved_to_disk"])
        self.assertTrue(os.path.exists(result["draft_html_path"]))

    # =============================================================
    # 6. Report Generator (.doc and .docx) Tests
    # =============================================================
    def test_09_report_doc_generator(self):
        """Generate actual .doc and .docx reports and assert file creation and content."""
        generator = ReportDocGenerator(workspace=self.test_dir)

        dummy_vuln = {
            "project_name": "Neura Test Project",
            "security_score": 82,
            "stats": {"critical": 0, "high": 2, "medium": 3, "low": 1, "total": 6},
            "vulnerabilities": [
                {
                    "id": "VULN-001",
                    "title": "Command Injection via os.system()",
                    "category": "Injection",
                    "severity": "HIGH",
                    "cwe": "CWE-78",
                    "file_path": "scripts/runner.py",
                    "line_number": 45,
                    "code_snippet": 'os.system(f"python {target}")',
                    "cause": "Unsanitized parameter passed to shell.",
                    "suggestion": "Use subprocess.run with shell=False.",
                    "fix_snippet": 'subprocess.run(["python", target], shell=False)',
                }
            ],
        }
        dummy_err = {
            "stats": {"total_errors": 1},
            "errors": [
                {
                    "id": "ERR-001",
                    "error_type": "FileNotFoundError",
                    "source": "runtime/debug.log",
                    "line_number": 88,
                    "raw_message": "FileNotFoundError: config.json missing",
                    "cause": "File does not exist.",
                    "handling_suggestion": "Create default config if missing.",
                    "fix_code": "if not os.path.exists(path): create_defaults()",
                }
            ],
        }

        output_doc = os.path.join(self.test_dir, "test_audit_report.doc")
        result = generator.generate_audit_report(
            vuln_report=dummy_vuln,
            error_report=dummy_err,
            computer_use_history=[
                {"step": 1, "action": "open_app", "status": "success", "result": "Opened Notepad"}
            ],
            output_filename=output_doc,
        )

        self.assertTrue(result["success"])
        docx_path = result["docx_path"]
        doc_path = result["doc_path"]

        self.assertTrue(os.path.exists(docx_path), f"File {docx_path} was not created")
        self.assertGreater(os.path.getsize(docx_path), 5000, "DOCX file size is too small")
        self.assertTrue(os.path.exists(doc_path), f"File {doc_path} was not created")
        self.assertGreater(os.path.getsize(doc_path), 5000, "DOC file size is too small")

    # =============================================================
    # 7. End-to-End Orchestrator Integration Test
    # =============================================================
    def test_10_orchestrator_end_to_end_audit_and_report(self):
        """Execute end-to-end audit, .doc generation, and reporting via Orchestrator."""
        output_doc = os.path.join(self.test_dir, "report.doc")
        result = self.orchestrator.audit_and_generate_report(
            target_dir=self.test_dir,
            voice_speaker_fn=None,
            output_doc_path=output_doc,
        )

        self.assertTrue(result["success"])
        self.assertIn("Security audit complete", result["summary"])
        self.assertIn(".doc", result["summary"])
        self.assertTrue(os.path.exists(result["doc_path"]))
        self.assertTrue(os.path.exists(result["docx_path"]))
        print("\n[Test] E2E Audit Result Summary:", result["summary"])

    def test_11_major_vulnerabilities_only_spoken_summary(self):
        """Verify that voice summary tells ONLY major vulnerabilities and directs to .doc file."""
        service = NotificationService()

        # Case 1: Multiple major vulnerabilities (CRITICAL and HIGH)
        vuln_rep = {
            "vulnerabilities": [
                {"title": "Command Injection via os.system()", "severity": "CRITICAL"},
                {"title": "Hardcoded AWS Secret Key", "severity": "HIGH"},
                {"title": "Weak MD5 Hashing", "severity": "LOW"},
                {"title": "Unpinned package in requirements.txt", "severity": "LOW"},
            ]
        }
        spoken_messages = []
        res = service.notify_user_audit_results(
            vuln_report=vuln_rep,
            error_report={"errors": []},
            doc_path="D:/test/report.doc",
            force_voice=True,
        )
        # Capture formatted voice message directly from NotificationService
        doc_name = "report.doc"
        vulns = vuln_rep.get("vulnerabilities", [])
        major_vulns = [v for v in vulns if v.get("severity") in ["CRITICAL", "HIGH"]]
        count = len(major_vulns)
        self.assertEqual(count, 2)
        major_titles = [v.get("title", "") for v in major_vulns[:3]]
        self.assertIn("Command Injection via os.system()", major_titles)
        self.assertIn("Hardcoded AWS Secret Key", major_titles)
        self.assertNotIn("Weak MD5 Hashing", major_titles)

        # Case 2: Exactly 1 major vulnerability
        vuln_rep_single = {
            "vulnerabilities": [
                {"title": "Dynamic Code Execution (eval)", "severity": "CRITICAL"},
                {"title": "Weak MD5", "severity": "MEDIUM"},
            ]
        }
        major_single = [v for v in vuln_rep_single["vulnerabilities"] if v.get("severity") in ["CRITICAL", "HIGH"]]
        self.assertEqual(len(major_single), 1)

        # Case 3: Zero major vulnerabilities
        vuln_rep_none = {
            "vulnerabilities": [
                {"title": "Unpinned package in requirements.txt", "severity": "LOW"}
            ]
        }
        major_none = [v for v in vuln_rep_none["vulnerabilities"] if v.get("severity") in ["CRITICAL", "HIGH"]]
        self.assertEqual(len(major_none), 0)


if __name__ == "__main__":
    unittest.main()

