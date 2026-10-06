"""
Neura Multi-Agent System - Project Agent.
Specialized in project inspection, syntax validation, test execution,
architecture analysis, dependency auditing, and code defect detection.
"""

import os
import re
import ast
import sys
import glob
import json
import subprocess
from typing import Dict, Any, List, Optional, Tuple
from brain.agents.base_agent import BaseAgent, AgentStatus
from brain.agents.task_manager import Task, PermissionLevel, TaskState
from brain.agents.event_system import (
    Finding,
    FindingCategory,
    Severity,
    EventType,
)

class ProjectAgent(BaseAgent):
    """
    Project Agent analyzes codebases, runs test suites, verifies dependencies,
    identifies architectural concerns, and detects software bugs safely.
    """
    def __init__(self, event_bus=None, task_manager=None, default_workspace=None):
        super().__init__(
            name="ProjectAgent",
            description="Analyzes project structures, executes test suites, inspects dependencies and detects architectural or code bugs.",
            capabilities=[
                "project_inspection",
                "test_execution",
                "dependency_audit",
                "ast_syntax_check",
                "architecture_analysis",
                "code_defect_detection",
                "endpoint_mapping",
            ],
            event_bus=event_bus,
            task_manager=task_manager,
        )
        self.default_workspace = default_workspace or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

    def execute_task(self, task: Task) -> Dict[str, Any]:
        """
        Main entry point for project tasks.
        Supports:
        - 'project_test' / 'test_project': comprehensive inspection + tests + architecture
        - 'inspect_project': structural and dependency overview
        - 'run_tests': test suite execution
        - 'analyze_code': code defect & architecture scan
        """
        task_type = task.task_type.lower()
        workspace = task.metadata.get("workspace") or self.default_workspace
        
        self.emit_progress(task.task_id, 10.0, f"Identifying project at {os.path.basename(workspace)}...")
        project_info = self.inspect_project_structure(workspace)

        findings: List[Finding] = []

        if task_type in ["project_test", "test_project", "full_test"]:
            self.emit_progress(task.task_id, 25.0, "Auditing dependencies and environment...")
            dep_findings = self.check_dependencies(workspace)
            for f in dep_findings:
                self.emit_finding(task.task_id, f)
                findings.append(f)

            self.emit_progress(task.task_id, 45.0, "Running AST syntax and code validation...")
            code_findings = self.analyze_code_and_architecture(workspace)
            for f in code_findings:
                self.emit_finding(task.task_id, f)
                findings.append(f)

            self.emit_progress(task.task_id, 70.0, "Discovering and executing project tests...")
            test_results, test_findings = self.run_tests(workspace)
            for f in test_findings:
                self.emit_finding(task.task_id, f)
                findings.append(f)

            self.emit_progress(task.task_id, 95.0, "Synthesizing test and inspection results...")
            
            summary = self._generate_testing_summary(project_info, test_results, findings)
            return {
                "success": True,
                "project_info": project_info,
                "test_results": test_results,
                "findings": [f.to_dict() for f in findings],
                "summary": summary,
            }

        elif task_type in ["inspect_project", "project_inspect"]:
            dep_findings = self.check_dependencies(workspace)
            for f in dep_findings:
                self.emit_finding(task.task_id, f)
                findings.append(f)
            return {
                "success": True,
                "project_info": project_info,
                "findings": [f.to_dict() for f in findings],
            }

        elif task_type in ["run_tests", "test_run"]:
            test_results, test_findings = self.run_tests(workspace)
            for f in test_findings:
                self.emit_finding(task.task_id, f)
                findings.append(f)
            return {
                "success": True,
                "test_results": test_results,
                "findings": [f.to_dict() for f in findings],
            }

        elif task_type in ["analyze_code", "code_analysis", "architecture_check"]:
            code_findings = self.analyze_code_and_architecture(workspace)
            for f in code_findings:
                self.emit_finding(task.task_id, f)
                findings.append(f)
            return {
                "success": True,
                "findings": [f.to_dict() for f in findings],
            }

        else:
            # Default fallback: do full inspection
            return self.execute_task(
                Task(
                    task_id=task.task_id,
                    task_type="project_test",
                    description=task.description,
                    metadata=task.metadata,
                )
            )

    def inspect_project_structure(self, root_dir: str) -> Dict[str, Any]:
        """Examines the project directory, languages, frameworks, and configuration."""
        languages = set()
        frameworks = set()
        file_counts = {"python": 0, "javascript": 0, "html": 0, "css": 0, "json": 0, "markdown": 0, "other": 0}
        total_files = 0
        oversized_files = []

        ignore_dirs = {".git", ".agents", "venv", "__pycache__", "node_modules", ".pytest_cache", "build", "dist"}

        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
            for f in filenames:
                total_files += 1
                ext = os.path.splitext(f)[1].lower()
                fpath = os.path.join(dirpath, f)

                if ext == ".py":
                    languages.add("Python")
                    file_counts["python"] += 1
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as fp:
                            lines = len(fp.readlines())
                            if lines > 600:
                                oversized_files.append({"file": os.path.relpath(fpath, root_dir), "lines": lines})
                    except Exception:
                        pass
                elif ext in [".js", ".jsx", ".ts", ".tsx"]:
                    languages.add("JavaScript/TypeScript")
                    file_counts["javascript"] += 1
                elif ext == ".html":
                    file_counts["html"] += 1
                elif ext == ".css":
                    file_counts["css"] += 1
                elif ext == ".json":
                    file_counts["json"] += 1
                elif ext in [".md", ".txt"]:
                    file_counts["markdown"] += 1
                else:
                    file_counts["other"] += 1

        # Framework detection by inspecting root files or requirements
        req_path = os.path.join(root_dir, "requirements.txt")
        if os.path.exists(req_path):
            try:
                with open(req_path, "r", encoding="utf-8", errors="ignore") as f:
                    req_content = f.read().lower()
                    if "fastapi" in req_content:
                        frameworks.add("FastAPI")
                    if "flask" in req_content:
                        frameworks.add("Flask")
                    if "django" in req_content:
                        frameworks.add("Django")
                    if "pygame" in req_content:
                        frameworks.add("Pygame")
                    if "speechrecognition" in req_content or "pyttsx3" in req_content:
                        frameworks.add("Speech/Voice AI")
                    if "google-generativeai" in req_content or "groq" in req_content:
                        frameworks.add("LLM/Generative AI")
            except Exception:
                pass

        if os.path.exists(os.path.join(root_dir, "package.json")):
            frameworks.add("Node.js/npm")

        return {
            "root_dir": root_dir,
            "project_name": os.path.basename(root_dir),
            "languages": sorted(list(languages)),
            "frameworks": sorted(list(frameworks)),
            "total_files": total_files,
            "file_distribution": file_counts,
            "oversized_files": oversized_files,
        }

    def check_dependencies(self, root_dir: str) -> List[Finding]:
        """Audits requirements.txt against the active Python environment."""
        findings = []
        req_path = os.path.join(root_dir, "requirements.txt")
        if not os.path.exists(req_path):
            findings.append(
                Finding(
                    category=FindingCategory.WARNING,
                    severity=Severity.MEDIUM,
                    title="Missing requirements.txt",
                    description="No requirements.txt file was found in the project root.",
                    file_path="requirements.txt",
                    suggestion="Generate requirements.txt with pinned dependencies.",
                )
            )
            return findings

        try:
            with open(req_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        except Exception as e:
            findings.append(
                Finding(
                    category=FindingCategory.BUG,
                    severity=Severity.HIGH,
                    title="Unreadable requirements.txt",
                    description=f"Error reading requirements.txt: {e}",
                    file_path="requirements.txt",
                )
            )
            return findings

        # Test import of listed dependencies
        package_import_map = {
            "speechrecognition": "speech_recognition",
            "opencv-python": "cv2",
            "pillow": "PIL",
            "google-generativeai": "google.generativeai",
            "python-multipart": "multipart",
        }

        for req in lines:
            # Clean version specifiers like fastapi>=0.100.0 or ==2.0
            pkg_name = re.split(r"[><=~]", req)[0].strip().lower()
            if not pkg_name:
                continue

            import_name = package_import_map.get(pkg_name, pkg_name.replace("-", "_"))
            try:
                __import__(import_name)
            except ImportError:
                findings.append(
                    Finding(
                        category=FindingCategory.BUG,
                        severity=Severity.HIGH,
                        title=f"Missing Dependency: {req}",
                        description=f"Package '{req}' is listed in requirements.txt but cannot be imported in the active environment.",
                        file_path="requirements.txt",
                        suggestion=f"Run 'pip install {req}' in your environment.",
                    )
                )

        return findings

    def analyze_code_and_architecture(self, root_dir: str) -> List[Finding]:
        """
        Parses all Python files with AST to discover syntax bugs,
        architecture concerns, duplicated functions, and oversized modules.
        """
        findings = []
        ignore_dirs = {".git", ".agents", "venv", "__pycache__", "build", "dist"}

        functions_seen: Dict[str, List[str]] = {}

        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
            for f in filenames:
                if not f.endswith(".py"):
                    continue
                fpath = os.path.join(dirpath, f)
                rel_path = os.path.relpath(fpath, root_dir)

                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as fp:
                        content = fp.read()
                except Exception as e:
                    findings.append(
                        Finding(
                            category=FindingCategory.BUG,
                            severity=Severity.HIGH,
                            title=f"File Read Error: {rel_path}",
                            description=str(e),
                            file_path=rel_path,
                        )
                    )
                    continue

                # 1. AST Syntax Check
                try:
                    tree = ast.parse(content, filename=rel_path)
                except SyntaxError as se:
                    findings.append(
                        Finding(
                            category=FindingCategory.BUG,
                            severity=Severity.CRITICAL,
                            title=f"Syntax Error in {rel_path}",
                            description=f"Syntax error at line {se.lineno}: {se.msg}",
                            file_path=rel_path,
                            line_number=se.lineno,
                            suggestion="Fix the syntax error to prevent runtime crash.",
                        )
                    )
                    continue

                # 2. Check Oversized Files / High Complexity (Architecture Concern)
                lines_count = len(content.splitlines())
                if lines_count > 1500 and "screen_vision" not in rel_path:
                    findings.append(
                        Finding(
                            category=FindingCategory.ARCHITECTURE_CONCERN,
                            severity=Severity.MEDIUM,
                            title=f"Large Monolithic Module: {rel_path}",
                            description=f"File contains {lines_count} lines. Holding too many responsibilities in one file hinders maintainability.",
                            file_path=rel_path,
                            suggestion="Consider decomposing secondary handlers into specialized submodules or agents.",
                        )
                    )

                # 3. Detect duplicate function definitions across codebase
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        # Skip dunder and trivial helpers
                        if node.name.startswith("__") or node.name in ["test", "setup", "teardown", "main", "run"]:
                            continue
                        if node.name not in functions_seen:
                            functions_seen[node.name] = []
                        functions_seen[node.name].append(rel_path)

        # Flag duplicated function names appearing in 3+ unrelated modules
        for fname, files in functions_seen.items():
            unique_files = list(set(files))
            if len(unique_files) >= 3:
                findings.append(
                    Finding(
                        category=FindingCategory.IMPROVEMENT_SUGGESTION,
                        severity=Severity.LOW,
                        title=f"Duplicated function identifier: '{fname}'",
                        description=f"The function '{fname}' is defined in {len(unique_files)} separate files: {', '.join(unique_files[:3])}.",
                        suggestion=f"Consolidate shared logic into a common utility or service module.",
                    )
                )

        return findings

    def run_tests(self, root_dir: str) -> Tuple[Dict[str, Any], List[Finding]]:
        """
        Locates test files and executes them safely using Python subprocess with timeout.
        Parses results, returns summary dict and test failure findings.
        """
        findings = []
        test_files = glob.glob(os.path.join(root_dir, "test_*.py"))
        test_results = {
            "total_suites": len(test_files),
            "executed_suites": 0,
            "passed_suites": 0,
            "failed_suites": 0,
            "suite_details": [],
        }

        py_exec = sys.executable

        for tf in test_files:
            rel_name = os.path.basename(tf)
            test_results["executed_suites"] += 1
            cmd = [py_exec, "-m", "unittest", rel_name]

            try:
                # Run with timeout to prevent hung GUI tests
                proc = subprocess.run(
                    cmd,
                    cwd=root_dir,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                stdout = proc.stdout + proc.stderr
                is_success = (proc.returncode == 0)

                if is_success:
                    test_results["passed_suites"] += 1
                    test_results["suite_details"].append({
                        "suite": rel_name,
                        "status": "PASSED",
                        "output": stdout[:300],
                    })
                else:
                    test_results["failed_suites"] += 1
                    test_results["suite_details"].append({
                        "suite": rel_name,
                        "status": "FAILED",
                        "output": stdout[:300],
                    })
                    findings.append(
                        Finding(
                            category=FindingCategory.BUG,
                            severity=Severity.HIGH,
                            title=f"Test Suite Failed: {rel_name}",
                            description=f"Subprocess returned exit code {proc.returncode}. Snippet:\n{stdout[-300:]}",
                            file_path=rel_name,
                            suggestion="Inspect test stack trace and fix the underlying assertion or runtime error.",
                        )
                    )
            except subprocess.TimeoutExpired:
                test_results["failed_suites"] += 1
                test_results["suite_details"].append({
                    "suite": rel_name,
                    "status": "TIMEOUT",
                    "output": "Test suite timed out after 15 seconds.",
                })
                findings.append(
                    Finding(
                        category=FindingCategory.WARNING,
                        severity=Severity.MEDIUM,
                        title=f"Test Suite Timed Out: {rel_name}",
                        description="Test execution exceeded the 15-second safety limit.",
                        file_path=rel_name,
                        suggestion="Ensure test suites do not block on modal windows or infinite loops.",
                    )
                )
            except Exception as e:
                test_results["failed_suites"] += 1
                findings.append(
                    Finding(
                        category=FindingCategory.BUG,
                        severity=Severity.HIGH,
                        title=f"Test Execution Error: {rel_name}",
                        description=str(e),
                        file_path=rel_name,
                    )
                )

        return test_results, findings

    def _generate_testing_summary(
        self,
        project_info: Dict[str, Any],
        test_results: Dict[str, Any],
        findings: List[Finding]
    ) -> str:
        """Formulates an executive summary of testing outcomes."""
        crit = sum(1 for f in findings if f.severity == Severity.CRITICAL)
        high = sum(1 for f in findings if f.severity == Severity.HIGH)
        med = sum(1 for f in findings if f.severity == Severity.MEDIUM)
        low = sum(1 for f in findings if f.severity == Severity.LOW)
        info = sum(1 for f in findings if f.severity == Severity.INFO)

        total_issues = len(findings)
        pname = project_info.get("project_name", "Current Project")
        suites_passed = test_results.get("passed_suites", 0)
        suites_total = test_results.get("executed_suites", 0)

        lines = [
            f"Project testing completed for '{pname}'.",
            f"Test suites: {suites_passed}/{suites_total} passed.",
        ]

        if total_issues == 0:
            lines.append("I found no critical issues or test failures. The project is healthy.")
        else:
            issue_breakdown = []
            if crit > 0:
                issue_breakdown.append(f"{crit} CRITICAL")
            if high > 0:
                issue_breakdown.append(f"{high} HIGH")
            if med > 0:
                issue_breakdown.append(f"{med} MEDIUM")
            if low > 0:
                issue_breakdown.append(f"{low} LOW")
            if info > 0:
                issue_breakdown.append(f"{info} informational")

            lines.append(f"I found {', '.join(issue_breakdown)} issue{'s' if total_issues > 1 else ''}.")

            # Highlight top issues
            top_issues = [f for f in findings if f.severity in [Severity.CRITICAL, Severity.HIGH]][:3]
            if not top_issues:
                top_issues = findings[:2]

            for issue in top_issues:
                lines.append(f"• [{issue.severity.value}] {issue.title}: {issue.description}")

            if crit > 0 or high > 0:
                lines.append("I recommend addressing the CRITICAL and HIGH priority issues first.")

        return "\n\n".join(lines)
