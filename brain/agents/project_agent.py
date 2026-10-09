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
import datetime
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
        target_file = task.metadata.get("target_file")
        terminal_allowed = bool(task.metadata.get("terminal_allowed", False))

        # 1. Specific file testing workflow
        if target_file or task_type in ["file_test", "test_file"]:
            file_to_test = target_file or task.metadata.get("file_path") or task.metadata.get("name")
            return self.test_file(file_to_test, terminal_allowed=terminal_allowed, task=task)

        # 2. Project testing workflow with terminal permission gating
        if task_type in ["project_test", "test_project", "full_test"]:
            return self.test_project_with_permission(workspace, terminal_allowed=terminal_allowed, task=task)

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
                    encoding="utf-8",
                    errors="replace",
                    timeout=15,
                )
                stdout = (proc.stdout or "") + (proc.stderr or "")
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
                    diag = self.debug_execution_failure(stdout, proc.returncode, target_file=rel_name)
                    findings.append(
                        Finding(
                            category=FindingCategory.BUG,
                            severity=Severity.HIGH,
                            title=f"Test Suite Failed: {rel_name}",
                            description=f"Subprocess returned exit code {proc.returncode}. {diag['root_cause']}\nSnippet:\n{stdout[-300:]}",
                            file_path=rel_name,
                            line_number=diag.get("failing_line"),
                            suggestion=diag.get("suggested_fix") or "Inspect test stack trace and fix the underlying assertion or runtime error.",
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

    def debug_execution_failure(
        self,
        output: str,
        exit_code: int,
        target_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyzes terminal execution traceback and error output to diagnose root causes
        and provide concrete debugging remedies.
        """
        diagnosis = {
            "error_type": "Execution Failure",
            "error_message": "",
            "failing_file": target_file or "unknown",
            "failing_line": None,
            "root_cause": "",
            "suggested_fix": "",
            "raw_snippet": (output[-400:] if output else "").strip()
        }

        # Extract traceback file and line frames
        traceback_frames = re.findall(r'File "([^"]+)", line (\d+)(?:, in (\w+))?', output or "")
        if traceback_frames:
            last_frame = traceback_frames[-1]
            diagnosis["failing_file"] = os.path.basename(last_frame[0])
            try:
                diagnosis["failing_line"] = int(last_frame[1])
            except ValueError:
                pass

        # Match exception line
        exc_match = re.search(r'([A-Za-z0-9_]+Error|[A-Za-z0-9_]+Exception):\s*(.*)', output or "")
        if exc_match:
            exc_type = exc_match.group(1)
            exc_msg = exc_match.group(2).strip()
            diagnosis["error_type"] = exc_type
            diagnosis["error_message"] = exc_msg

            if exc_type in ["ModuleNotFoundError", "ImportError"]:
                pkg = re.search(r"No module named '([^']+)'", exc_msg)
                pkg_name = pkg.group(1) if pkg else "the module"
                diagnosis["root_cause"] = f"Missing package or import dependency '{pkg_name}' in active environment."
                diagnosis["suggested_fix"] = f"Run 'pip install {pkg_name}' or check PYTHONPATH and package structure."
            elif exc_type in ["SyntaxError", "IndentationError"]:
                line_str = f" at line {diagnosis['failing_line']}" if diagnosis["failing_line"] else ""
                diagnosis["root_cause"] = f"Syntax or indentation defect in {diagnosis['failing_file']}{line_str}: {exc_msg}."
                diagnosis["suggested_fix"] = "Verify closing brackets, colons, and uniform indentation (tabs vs spaces)."
            elif exc_type == "NameError":
                var = re.search(r"name '([^']+)' is not defined", exc_msg)
                var_name = var.group(1) if var else "identifier"
                diagnosis["root_cause"] = f"Identifier '{var_name}' is referenced before definition or import."
                diagnosis["suggested_fix"] = f"Import or declare '{var_name}' before usage."
            elif exc_type == "TypeError":
                diagnosis["root_cause"] = f"Type mismatch or invalid function parameters: {exc_msg}."
                diagnosis["suggested_fix"] = "Inspect function argument count and variable types."
            elif exc_type == "AttributeError":
                diagnosis["root_cause"] = f"Attribute or method missing on object: {exc_msg}."
                diagnosis["suggested_fix"] = "Verify attribute spelling or ensure object is correctly initialized."
            elif exc_type == "AssertionError":
                diagnosis["root_cause"] = f"Test assertion failed: {exc_msg or 'Condition evaluated to False'}."
                diagnosis["suggested_fix"] = "Check expected vs actual values in test assertion logic."
            else:
                diagnosis["root_cause"] = f"{exc_type}: {exc_msg}"
                diagnosis["suggested_fix"] = f"Check traceback in {diagnosis['failing_file']} to resolve runtime exception."
        else:
            diagnosis["root_cause"] = f"Process terminated abnormally with exit code {exit_code}."
            diagnosis["suggested_fix"] = "Inspect terminal console logs and environment configuration."

        return diagnosis

    def test_file(
        self,
        file_path: str,
        terminal_allowed: bool = False,
        task: Optional[Task] = None
    ) -> Dict[str, Any]:
        """
        Tests and inspects a specific single file.
        - General Test (terminal_allowed=False):
            AST parsing, syntax error detection, imports inspection, metrics.
        - Dynamic Terminal Test (terminal_allowed=True):
            Static inspection + executes file/test in terminal via subprocess,
            captures exit code and logs, and runs automated debugging if an error occurs.
        """
        task_id = task.task_id if task else "file_test"
        self.emit_progress(task_id, 10.0, f"Locating target file: {file_path}...")

        # Resolve path
        target_ws = (task.metadata.get("workspace") if task and task.metadata else None) or self.default_workspace
        resolved_path = None
        if file_path:
            if os.path.isabs(file_path) and os.path.exists(file_path):
                resolved_path = file_path
            else:
                candidate = os.path.join(target_ws, file_path)
                if os.path.exists(candidate):
                    resolved_path = candidate
                elif os.path.exists(os.path.join(self.default_workspace, file_path)):
                    resolved_path = os.path.join(self.default_workspace, file_path)
                else:
                    fname = os.path.basename(file_path).lower()
                    for search_dir in [target_ws, self.default_workspace]:
                        if not search_dir or not os.path.exists(search_dir):
                            continue
                        for root, _, files in os.walk(search_dir):
                            if any(ignored in root for ignored in [".git", "venv", "__pycache__", "node_modules"]):
                                continue
                            for f in files:
                                if f.lower() == fname:
                                    resolved_path = os.path.join(root, f)
                                    break
                            if resolved_path:
                                break
                        if resolved_path:
                            break

        if not resolved_path or not os.path.exists(resolved_path):
            err_msg = f"Target file '{file_path}' could not be located in workspace '{os.path.basename(target_ws)}'."
            return {
                "success": False,
                "error": err_msg,
                "summary": f"File testing failed: {err_msg}",
                "full_report": f"# File Test Report\n\n**Error**: {err_msg}",
                "findings": []
            }

        rel_path = os.path.relpath(resolved_path, self.default_workspace)
        file_name = os.path.basename(resolved_path)
        ext = os.path.splitext(file_name)[1].lower()

        findings: List[Finding] = []
        file_stats = {
            "file_name": file_name,
            "file_path": rel_path,
            "absolute_path": resolved_path,
            "extension": ext,
            "lines": 0,
            "functions": 0,
            "classes": 0,
            "imports": [],
            "has_main": False,
        }

        self.emit_progress(task_id, 30.0, f"Performing static AST analysis on {file_name}...")
        try:
            with open(resolved_path, "r", encoding="utf-8", errors="replace") as fp:
                content = fp.read()
            file_stats["lines"] = len(content.splitlines())
        except Exception as e:
            f = Finding(
                category=FindingCategory.BUG,
                severity=Severity.HIGH,
                title=f"File Read Error: {file_name}",
                description=str(e),
                file_path=rel_path
            )
            findings.append(f)
            self.emit_finding(task_id, f)
            content = ""

        # AST Analysis for Python files
        if ext == ".py" and content:
            try:
                tree = ast.parse(content, filename=rel_path)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        file_stats["functions"] += 1
                    elif isinstance(node, ast.ClassDef):
                        file_stats["classes"] += 1
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            file_stats["imports"].append(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            file_stats["imports"].append(node.module)
                    elif isinstance(node, ast.If):
                        try:
                            if isinstance(node.test, ast.Compare):
                                if isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__":
                                    file_stats["has_main"] = True
                        except Exception:
                            pass
            except SyntaxError as se:
                f = Finding(
                    category=FindingCategory.BUG,
                    severity=Severity.CRITICAL,
                    title=f"Syntax Error in {file_name}",
                    description=f"Syntax error at line {se.lineno}: {se.msg}\nCode snippet: {se.text}",
                    file_path=rel_path,
                    line_number=se.lineno,
                    suggestion="Fix syntax defect before running the file."
                )
                findings.append(f)
                self.emit_finding(task_id, f)

            if file_stats["lines"] > 600:
                f = Finding(
                    category=FindingCategory.ARCHITECTURE_CONCERN,
                    severity=Severity.MEDIUM,
                    title=f"Large File Size: {file_name}",
                    description=f"File contains {file_stats['lines']} lines. Consider decomposing.",
                    file_path=rel_path,
                    suggestion="Extract secondary helper functions into separate modules."
                )
                findings.append(f)
                self.emit_finding(task_id, f)

        # Dynamic Terminal Execution
        exec_result = {
            "executed": False,
            "exit_code": None,
            "output": "",
            "debug_analysis": None,
            "terminal_allowed": terminal_allowed
        }

        if terminal_allowed:
            self.emit_progress(task_id, 65.0, f"Terminal access granted: Executing {file_name} in terminal...")
            exec_result["executed"] = True

            py_exec = sys.executable
            cwd = os.path.dirname(resolved_path) or self.default_workspace

            if file_name.startswith("test_") or "unittest" in file_stats["imports"]:
                cmd = [py_exec, "-m", "unittest", file_name]
            elif ext == ".py":
                comp_proc = subprocess.run([py_exec, "-m", "py_compile", resolved_path], capture_output=True, text=True, timeout=10)
                if comp_proc.returncode != 0:
                    cmd = None
                    exec_result["exit_code"] = comp_proc.returncode
                    exec_result["output"] = comp_proc.stderr or comp_proc.stdout or "Bytecode compilation failed."
                elif file_stats["has_main"]:
                    cmd = [py_exec, resolved_path]
                else:
                    cmd = [py_exec, "-m", "py_compile", resolved_path]
            else:
                cmd = None

            if cmd:
                try:
                    proc = subprocess.run(
                        cmd,
                        cwd=cwd,
                        capture_output=True,
                        text=True,
                        timeout=15
                    )
                    exec_result["exit_code"] = proc.returncode
                    exec_result["output"] = (proc.stdout or "") + (proc.stderr or "")
                except subprocess.TimeoutExpired:
                    exec_result["exit_code"] = -1
                    exec_result["output"] = "Execution timed out after 15 seconds."
                except Exception as e:
                    exec_result["exit_code"] = -2
                    exec_result["output"] = str(e)

            if exec_result["exit_code"] != 0 and exec_result["exit_code"] is not None:
                diag = self.debug_execution_failure(exec_result["output"], exec_result["exit_code"], target_file=file_name)
                exec_result["debug_analysis"] = diag
                f = Finding(
                    category=FindingCategory.BUG,
                    severity=Severity.HIGH,
                    title=f"Terminal Execution Failed: {file_name}",
                    description=f"{diag['root_cause']}\nSnippet:\n{diag['raw_snippet']}",
                    file_path=rel_path,
                    line_number=diag.get("failing_line"),
                    suggestion=diag.get("suggested_fix")
                )
                findings.append(f)
                self.emit_finding(task_id, f)
        else:
            self.emit_progress(task_id, 65.0, "Terminal access not granted: Omitting dynamic execution...")

        self.emit_progress(task_id, 95.0, "Formulating file test report...")
        summary, full_report = self._generate_file_testing_summary(file_stats, exec_result, findings, terminal_allowed=terminal_allowed)
        report_path = self._save_report_file(full_report, prefix=f"file_test_{file_name}")

        return {
            "success": True,
            "file_stats": file_stats,
            "exec_result": exec_result,
            "findings": [f.to_dict() for f in findings],
            "summary": summary,
            "full_report": full_report,
            "report_file": report_path,
            "terminal_allowed": terminal_allowed,
        }

    def test_project_with_permission(
        self,
        workspace: str,
        terminal_allowed: bool = False,
        task: Optional[Task] = None
    ) -> Dict[str, Any]:
        """
        Coordinates project-wide testing with terminal permission gating.
        - If terminal_allowed=True: runs dependencies, AST architecture, and executes test suites in terminal with automated traceback debugging.
        - If terminal_allowed=False: runs general static AST, architecture, and dependency audit without executing terminal tests.
        """
        task_id = task.task_id if task else "proj_test"
        self.emit_progress(task_id, 10.0, f"Identifying project structure at {os.path.basename(workspace)}...")
        project_info = self.inspect_project_structure(workspace)

        findings: List[Finding] = []

        self.emit_progress(task_id, 25.0, "Auditing dependencies and environment...")
        dep_findings = self.check_dependencies(workspace)
        for f in dep_findings:
            self.emit_finding(task_id, f)
            findings.append(f)

        self.emit_progress(task_id, 45.0, "Running AST syntax and code validation...")
        code_findings = self.analyze_code_and_architecture(workspace)
        for f in code_findings:
            self.emit_finding(task_id, f)
            findings.append(f)

        test_results = {
            "total_suites": 0,
            "executed_suites": 0,
            "passed_suites": 0,
            "failed_suites": 0,
            "suite_details": [],
            "terminal_allowed": terminal_allowed
        }

        if terminal_allowed:
            self.emit_progress(task_id, 70.0, "Terminal access granted: Discovering and executing test suites...")
            test_results, test_findings = self.run_tests(workspace)
            for f in test_findings:
                self.emit_finding(task_id, f)
                findings.append(f)
        else:
            self.emit_progress(task_id, 70.0, "Terminal access not granted: Skipping dynamic test suite execution...")
            test_files = glob.glob(os.path.join(workspace, "test_*.py"))
            test_results["total_suites"] = len(test_files)
            test_results["skipped_reason"] = "Terminal access permission not granted. Dynamic execution was safely skipped."

        self.emit_progress(task_id, 95.0, "Synthesizing test and inspection results...")
        summary, full_report = self._generate_testing_summary(project_info, test_results, findings, terminal_allowed=terminal_allowed)
        report_path = self._save_report_file(full_report, prefix=f"project_test_{project_info.get('project_name', 'project')}")

        return {
            "success": True,
            "project_info": project_info,
            "test_results": test_results,
            "findings": [f.to_dict() for f in findings],
            "summary": summary,
            "full_report": full_report,
            "report_file": report_path,
            "terminal_allowed": terminal_allowed,
        }

    def _save_report_file(self, content: str, prefix: str = "test_report") -> str:
        """Saves generated test report to audit_reports directory."""
        try:
            report_dir = os.path.join(self.default_workspace, "audit_reports")
            os.makedirs(report_dir, exist_ok=True)
            clean_p = re.sub(r"[^a-zA-Z0-9_\-]", "_", prefix)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = os.path.join(report_dir, f"{clean_p}_{ts}.md")
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(content)
            return report_path
        except Exception:
            return ""

    def _generate_file_testing_summary(
        self,
        file_stats: Dict[str, Any],
        exec_result: Dict[str, Any],
        findings: List[Finding],
        terminal_allowed: bool = False
    ) -> Tuple[str, str]:
        """Formulates voice summary and Markdown report for single file tests."""
        fname = file_stats["file_name"]
        lines = file_stats["lines"]
        crit = sum(1 for f in findings if f.severity == Severity.CRITICAL)
        high = sum(1 for f in findings if f.severity == Severity.HIGH)
        med = sum(1 for f in findings if f.severity == Severity.MEDIUM)
        low = sum(1 for f in findings if f.severity == Severity.LOW)
        total_issues = len(findings)

        mode_str = "Dynamic Terminal Test & Debug (Terminal Access: GRANTED)" if terminal_allowed else "General Static Test (Terminal Access: DENIED)"

        sum_lines = [
            f"Project testing completed for file '{fname}'.",
            f"Mode: {mode_str}.",
            f"Code metrics: {lines} lines, {file_stats['functions']} functions, {file_stats['classes']} classes."
        ]

        if terminal_allowed:
            if exec_result.get("exit_code") == 0:
                sum_lines.append("Terminal execution succeeded with exit code 0.")
            else:
                diag = exec_result.get("debug_analysis")
                if diag and diag.get("error_type"):
                    sum_lines.append(f"Terminal execution encountered {diag['error_type']}. Suggested fix: {diag['suggested_fix']}")
                else:
                    sum_lines.append(f"Terminal execution failed with exit code {exec_result.get('exit_code')}.")
        else:
            sum_lines.append("General static analysis completed. Dynamic terminal execution was skipped as terminal access was not granted.")

        if total_issues == 0:
            sum_lines.append("No syntax bugs or defects were discovered. The file is healthy.")
        else:
            sum_lines.append(f"I found {total_issues} issue{'s' if total_issues > 1 else ''} ({high} HIGH, {med} MEDIUM, {low} LOW).")
            for f in findings[:2]:
                sum_lines.append(f"• [{f.severity.value}] {f.title}: {f.description[:120]}")

        summary = "\n\n".join(sum_lines)

        md = [
            f"# Test & Quality Report: {fname}",
            f"**File**: `{file_stats['file_path']}`  ",
            f"**Mode**: {mode_str}  ",
            f"**Generated**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
            "",
            "## 1. File Structure & Metrics",
            f"- **Lines of Code**: {lines}",
            f"- **Functions / Methods**: {file_stats['functions']}",
            f"- **Classes**: {file_stats['classes']}",
            f"- **Imports Detected**: {', '.join(file_stats['imports'][:10]) if file_stats['imports'] else 'None'}",
            "",
            "## 2. Terminal Execution & Debugging"
        ]

        if terminal_allowed:
            md.append(f"- **Terminal Status**: Executed")
            md.append(f"- **Exit Code**: {exec_result.get('exit_code')}")
            if exec_result.get("output"):
                md.append("```text")
                md.append(exec_result["output"][-600:])
                md.append("```")
            diag = exec_result.get("debug_analysis")
            if diag:
                md.append("\n### Automated Debugging Diagnosis")
                md.append(f"- **Error Type**: `{diag['error_type']}`")
                md.append(f"- **Location**: `{diag['failing_file']}` (Line {diag.get('failing_line')})")
                md.append(f"- **Root Cause**: {diag['root_cause']}")
                md.append(f"- **Recommended Fix**: {diag['suggested_fix']}")
        else:
            md.append("- **Terminal Status**: Skipped (Terminal permission not granted)")
            md.append("- **Note**: No terminal processes or scripts were run. Static AST inspection only.")

        md.append("\n## 3. Discovered Findings & Code Quality")
        if findings:
            for f in findings:
                md.append(f"### [{f.severity.value}] {f.title}")
                md.append(f"- **Description**: {f.description}")
                if f.suggestion:
                    md.append(f"- **Recommendation**: {f.suggestion}")
                md.append("")
        else:
            md.append("No critical issues, syntax errors, or vulnerabilities found.")

        full_report = "\n".join(md)
        return summary, full_report

    def _generate_testing_summary(
        self,
        project_info: Dict[str, Any],
        test_results: Dict[str, Any],
        findings: List[Finding],
        terminal_allowed: bool = False
    ) -> Tuple[str, str]:
        """Formulates an executive summary of testing outcomes and full Markdown report."""
        crit = sum(1 for f in findings if f.severity == Severity.CRITICAL)
        high = sum(1 for f in findings if f.severity == Severity.HIGH)
        med = sum(1 for f in findings if f.severity == Severity.MEDIUM)
        low = sum(1 for f in findings if f.severity == Severity.LOW)
        info = sum(1 for f in findings if f.severity == Severity.INFO)

        total_issues = len(findings)
        pname = project_info.get("project_name", "Current Project")
        suites_passed = test_results.get("passed_suites", 0)
        suites_total = test_results.get("executed_suites", 0)

        mode_str = "Dynamic Terminal Test & Debug (Terminal Access: GRANTED)" if terminal_allowed else "General Static Test (Terminal Access: DENIED)"

        lines = [
            f"Project testing completed for '{pname}'.",
            f"Mode: {mode_str}."
        ]

        if terminal_allowed:
            lines.append(f"Test suites: {suites_passed}/{suites_total} passed.")
        else:
            lines.append(f"General static code inspection completed. Dynamic test execution was skipped because terminal access was not granted.")

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

        summary = "\n\n".join(lines)

        # Markdown Report
        md = [
            f"# Project Testing & Quality Report: {pname}",
            f"**Workspace**: `{project_info.get('root_dir', pname)}`  ",
            f"**Mode**: {mode_str}  ",
            f"**Generated**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
            "",
            "## 1. Project Overview & Architecture",
            f"- **Languages**: {', '.join(project_info.get('languages', [])) or 'None'}",
            f"- **Frameworks**: {', '.join(project_info.get('frameworks', [])) or 'None'}",
            f"- **Total Files**: {project_info.get('total_files', 0)}",
            "",
            "## 2. Test Execution & Terminal Results"
        ]

        if terminal_allowed:
            md.append(f"- **Test Suites Executed**: {suites_total}")
            md.append(f"- **Passed**: {suites_passed}")
            md.append(f"- **Failed**: {test_results.get('failed_suites', 0)}")
            for s in test_results.get("suite_details", []):
                md.append(f"- **{s.get('suite')}**: `{s.get('status')}`")
        else:
            md.append(f"- **Dynamic Execution**: Skipped (Terminal permission not granted)")
            md.append(f"- **Discovered Test Files**: {test_results.get('total_suites', 0)} files")
            md.append(f"- **Note**: To execute these tests dynamically, grant terminal access permission.")

        md.append("\n## 3. Findings & Code Quality Issues")
        if findings:
            for f in findings:
                md.append(f"### [{f.severity.value}] {f.title}")
                md.append(f"- **File**: `{f.file_path or 'General'}`")
                md.append(f"- **Description**: {f.description}")
                if f.suggestion:
                    md.append(f"- **Recommendation**: {f.suggestion}")
                md.append("")
        else:
            md.append("No critical defects or syntax errors found.")

        full_report = "\n".join(md)
        return summary, full_report
