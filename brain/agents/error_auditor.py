"""
Neura Multi-Agent System - Error Auditor & Diagnostic Interpreter.
Scans and audits system log files, runtime exception dumps, terminal tracebacks,
and application outputs. Analyzes error root causes and produces actionable handling suggestions.
"""

import os
import re
import glob
import json
import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict, field

from brain.agents.event_system import Finding, FindingCategory, Severity


@dataclass
class AuditedError:
    """Represents an analyzed error entry from system or application logs."""
    id: str
    error_type: str
    severity: Severity
    source: str
    line_number: Optional[int]
    raw_message: str
    cause: str
    handling_suggestion: str
    fix_code: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value if isinstance(self.severity, Severity) else str(self.severity)
        return d

    def to_finding(self) -> Finding:
        return Finding(
            category=FindingCategory.ERROR_LOG,
            severity=self.severity,
            title=f"Audited Error: {self.error_type}",
            description=f"Source: {self.source}\nCause: {self.cause}\nRaw snippet: {self.raw_message[:150]}",
            file_path=self.source,
            line_number=self.line_number,
            suggestion=self.handling_suggestion,
        )


class ErrorAuditor:
    """
    Automated error monitoring, auditing, and diagnostic analysis engine.
    Ingests log files, active terminal exceptions, and execution tracebacks.
    """

    def __init__(self, workspace: Optional[str] = None):
        self.workspace = workspace or os.getcwd()
        self.ignore_dirs = {".git", ".agents", "venv", "__pycache__", "node_modules"}

    def audit_all_logs(self, target_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Discovers all log files, crash dumps, and runtime outputs across the workspace
        and performs deep error auditing.
        """
        scan_dir = target_dir or self.workspace
        print(f"\n📋 [ErrorAuditor] Commencing log auditing on: {scan_dir}")
        start_time = datetime.datetime.now()

        audited_errors: List[AuditedError] = []
        log_files_found: List[str] = []

        # 1. Discover log files (*.log, *.out, *.err, logs/, runtime/)
        for root, dirs, files in os.walk(scan_dir):
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in [".log", ".out", ".err", ".txt"] and any(k in f.lower() for k in ["log", "error", "debug", "crash", "trace", "output"]):
                    fpath = os.path.join(root, f)
                    log_files_found.append(fpath)
                    audited_errors.extend(self._audit_single_log_file(fpath, scan_dir))

        # 2. Check for recent frontend / runtime error logs or bridges
        status_file = os.path.join(scan_dir, "status_bridge.json")
        if os.path.exists(status_file):
            audited_errors.extend(self._audit_status_bridge(status_file))

        # Deduplicate identical errors
        unique_errors = []
        seen_keys = set()
        for err in audited_errors:
            key = (err.error_type, err.source, err.raw_message[:80])
            if key not in seen_keys:
                seen_keys.add(key)
                unique_errors.append(err)

        # Rank by severity
        rank_map = {Severity.CRITICAL: 4, Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1, Severity.INFO: 0}
        unique_errors.sort(key=lambda e: rank_map.get(e.severity, 0), reverse=True)

        stats = {
            "critical": sum(1 for e in unique_errors if e.severity == Severity.CRITICAL),
            "high": sum(1 for e in unique_errors if e.severity == Severity.HIGH),
            "medium": sum(1 for e in unique_errors if e.severity == Severity.MEDIUM),
            "low": sum(1 for e in unique_errors if e.severity == Severity.LOW),
            "total_errors": len(unique_errors),
            "log_files_scanned": len(log_files_found),
        }

        elapsed = (datetime.datetime.now() - start_time).total_seconds()
        print(f"📋 [ErrorAuditor] Log audit finished in {elapsed:.2f}s! Identified {stats['total_errors']} issues across {stats['log_files_scanned']} log files.\n")

        return {
            "success": True,
            "scan_dir": os.path.abspath(scan_dir),
            "elapsed_seconds": elapsed,
            "log_files_found": [os.path.relpath(f, scan_dir) for f in log_files_found],
            "stats": stats,
            "errors": [e.to_dict() for e in unique_errors],
            "findings_objects": [e.to_finding() for e in unique_errors],
        }

    def _audit_single_log_file(self, full_path: str, scan_root: str) -> List[AuditedError]:
        """Parses a log file for tracebacks, exceptions, fatal errors, and warnings."""
        errors: List[AuditedError] = []
        rel_path = os.path.relpath(full_path, scan_root)

        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            return errors

        lines = content.splitlines()

        # Pattern 1: Python Tracebacks
        tb_matches = re.finditer(r"Traceback \(most recent call last\):.*?(?:\n[A-Za-z0-9_]+Error:.*|\n[A-Za-z0-9_]+Exception:.*)", content, re.DOTALL)
        for m in tb_matches:
            tb_block = m.group(0).strip()
            # Extract final line
            last_line = tb_block.splitlines()[-1] if tb_block.splitlines() else "Unknown Error"
            err_type = last_line.split(":")[0].strip()

            cause, sugg, fix = self._diagnose_exception(err_type, tb_block)
            errors.append(
                AuditedError(
                    id=f"ERR-{len(errors)+1:03d}",
                    error_type=err_type,
                    severity=Severity.HIGH,
                    source=rel_path,
                    line_number=None,
                    raw_message=last_line,
                    cause=cause,
                    handling_suggestion=sugg,
                    fix_code=fix,
                )
            )

        # Pattern 2: Line-by-line Error / Exception signatures
        for idx, line in enumerate(lines, 1):
            line_clean = line.strip()
            if not line_clean:
                continue

            # Standard Python / System Exceptions
            exc_match = re.search(r"\b([A-Za-z0-9_]+(?:Error|Exception|Warning|Fault)):\s*(.*)", line_clean)
            if exc_match and "Traceback" not in line_clean:
                err_name = exc_match.group(1)
                err_msg = exc_match.group(2).strip()
                cause, sugg, fix = self._diagnose_exception(err_name, err_msg)
                
                # Determine severity
                sev = Severity.HIGH
                if "Warning" in err_name:
                    sev = Severity.MEDIUM
                elif err_name in ["KeyboardInterrupt", "SystemExit"]:
                    sev = Severity.INFO

                errors.append(
                    AuditedError(
                        id=f"ERR-{len(errors)+1:03d}",
                        error_type=err_name,
                        severity=sev,
                        source=rel_path,
                        line_number=idx,
                        raw_message=line_clean[:180],
                        cause=cause,
                        handling_suggestion=sugg,
                        fix_code=fix,
                    )
                )

            # OpenCV DNN backend warning / error
            if "cv::dnn" in line_clean and "WARN" in line_clean:
                errors.append(
                    AuditedError(
                        id=f"ERR-{len(errors)+1:03d}",
                        error_type="OpenCV DNN Backend Fallback",
                        severity=Severity.LOW,
                        source=rel_path,
                        line_number=idx,
                        raw_message=line_clean[:180],
                        cause="OpenCV DNN module setPreferableTarget requested an unsupported acceleration device (e.g. CUDA/OpenCL) and fell back to CPU default.",
                        handling_suggestion="Specify cv2.dnn.DNN_BACKEND_OPENCV and cv2.dnn.DNN_TARGET_CPU explicitly to avoid terminal warning logs.",
                        fix_code="net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)\nnet.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)"
                    )
                )

        return errors

    def _audit_status_bridge(self, bridge_path: str) -> List[AuditedError]:
        """Audits status_bridge.json for logged runtime crashes or agent failure states."""
        errors = []
        try:
            with open(bridge_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            last_err = data.get("last_error") or data.get("error")
            if last_err:
                cause, sugg, fix = self._diagnose_exception("Runtime Failure", str(last_err))
                errors.append(
                    AuditedError(
                        id=f"ERR-BRIDGE-001",
                        error_type="IPC Runtime Error",
                        severity=Severity.HIGH,
                        source="status_bridge.json",
                        line_number=None,
                        raw_message=str(last_err)[:180],
                        cause=cause,
                        handling_suggestion=sugg,
                        fix_code=fix,
                    )
                )
        except Exception:
            pass
        return errors

    def _diagnose_exception(self, err_type: str, context_snippet: str) -> Tuple[str, str, Optional[str]]:
        """Provides AI-grade diagnostic understanding and handling suggestion for common exceptions."""
        err_lower = err_type.lower()
        snippet_lower = context_snippet.lower()

        if "keyboardinterrupt" in err_lower:
            return (
                "Process received SIGINT (Ctrl+C) signal from user keyboard while waiting in I/O loop.",
                "Wrap long-running execution loops with try/except KeyboardInterrupt to release hardware cameras, threads, and sockets gracefully.",
                "try:\n    run_loop()\nexcept KeyboardInterrupt:\n    print('Exiting cleanly...')\n    cleanup_resources()"
            )

        elif "filenotfounderror" in err_lower:
            return (
                "Operating system file lookup failed because the specified path or asset does not exist on disk.",
                "Verify file path existence before opening, or use os.path.exists() and default fallback resources.",
                "if os.path.exists(target_path):\n    with open(target_path) as f: ...\nelse:\n    create_default_file(target_path)"
            )

        elif "modulenotfounderror" in err_lower or "importerror" in err_lower:
            match = re.search(r"No module named\s+['\"]?([a-zA-Z0-9_\-]+)['\"]?", context_snippet)
            pkg = match.group(1) if match else "missing_module"
            return (
                f"Python runtime attempted to import package '{pkg}' which is not installed in the active environment.",
                f"Install the required dependency into your virtual environment and add it to requirements.txt.",
                f"pip install {pkg}"
            )

        elif "connectionerror" in err_lower or "connectionrefusederror" in err_lower or "timeout" in err_lower:
            return (
                "Network socket connection failed, timed out, or was rejected by the remote host.",
                "Implement exponential backoff retry loops with timeout bounds and fallback responses when external services are unreachable.",
                "from urllib3.util import Retry\nfrom requests.adapters import HTTPAdapter\n# Configure session with 3 retries"
            )

        elif "permissionerror" in err_lower:
            return (
                "Operating system denied access to read, modify, or lock the target file or IPC bridge.",
                "Implement atomic file replacement using temporary files or retry loops with backoff to handle concurrent file locks.",
                "for attempt in range(5):\n    try:\n        os.replace(temp_file, target_file)\n        break\n    except PermissionError:\n        time.sleep(0.05)"
            )

        elif "zerodivisionerror" in err_lower:
            return (
                "Division or modulo by zero encountered in numeric calculation.",
                "Validate the denominator before performing mathematical divisions and guard against empty list counts.",
                "average = total / len(items) if items else 0.0"
            )

        elif "keyerror" in err_lower:
            return (
                "Dictionary key accessed with bracket notation was not present in the dictionary mapping.",
                "Use dict.get(key, default) instead of direct bracket access to provide safe fallbacks.",
                "value = data.get('desired_key', default_value)"
            )

        elif "indexerror" in err_lower:
            return (
                "Sequence index access out of bounds for the current list or tuple size.",
                "Check len(sequence) before indexing or use safe slicing/iteration.",
                "first_item = items[0] if items else None"
            )

        elif "syntaxerror" in err_lower:
            return (
                "Python parser failed to tokenize or parse code structure due to invalid syntax.",
                "Inspect the reported file and line number for missing colons, mismatched brackets, or improper indentation.",
                "# Ensure all open quotes and parentheses are matched correctly"
            )

        # Generic default diagnostic
        return (
            f"Encountered unexpected {err_type} during execution.",
            f"Review stack trace, add robust exception isolation with logging, and handle boundary conditions.",
            "try:\n    risky_operation()\nexcept Exception as e:\n    logger.error(f'Operation failed: {e}', exc_info=True)"
        )
