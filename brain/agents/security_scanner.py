"""
Neura Multi-Agent System - Project Vulnerability Scanner & Security Auditor.
Provides automated Static Application Security Testing (SAST), secrets detection,
dependency security audits, and configuration reviews for any software project.
"""

import os
import re
import ast
import json
import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict, field

from brain.agents.event_system import Finding, FindingCategory, Severity


@dataclass
class Vulnerability:
    """Represents a discrete security vulnerability identified in a project."""
    id: str
    title: str
    category: str
    severity: Severity
    cwe: str
    cvss_score: float
    file_path: str
    line_number: int
    code_snippet: str
    cause: str
    suggestion: str
    fix_snippet: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value if isinstance(self.severity, Severity) else str(self.severity)
        return d

    def to_finding(self) -> Finding:
        return Finding(
            category=FindingCategory.VULNERABILITY,
            severity=self.severity,
            title=f"[{self.cwe}] {self.title}",
            description=f"Cause: {self.cause}\nOffending code: {self.code_snippet}",
            file_path=self.file_path,
            line_number=self.line_number,
            suggestion=self.suggestion,
        )


class VulnerabilityScanner:
    """
    Automated security auditing engine that scans codebases for vulnerabilities,
    secrets, injection vectors, cryptographic flaws, and insecure dependencies.
    """

    def __init__(self, workspace: Optional[str] = None):
        self.workspace = workspace or os.getcwd()
        self.ignore_dirs = {
            ".git", ".agents", "venv", "env", "__pycache__", "node_modules",
            ".pytest_cache", "build", "dist", ".idea", ".vscode"
        }

    def scan_project(self, target_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes a comprehensive security vulnerability scan across the target project directory.
        """
        scan_root = target_dir or self.workspace
        if not os.path.exists(scan_root):
            return {
                "success": False,
                "error": f"Target directory '{scan_root}' does not exist.",
                "vulnerabilities": [],
            }

        print(f"\n🛡️  [VulnerabilityScanner] Commencing security scan on: {scan_root}")
        start_time = datetime.datetime.now()

        vulnerabilities: List[Vulnerability] = []
        files_scanned = 0

        # 1. Scan Source Files (Python, JS/TS, HTML, Shell, Configs)
        for dirpath, dirnames, filenames in os.walk(scan_root):
            dirnames[:] = [d for d in dirnames if d not in self.ignore_dirs]

            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(fpath, scan_root)
                ext = os.path.splitext(fname)[1].lower()

                # Process code and config files
                if ext in [".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".php", ".sh", ".json", ".env", ".yml", ".yaml"]:
                    files_scanned += 1
                    file_vulns = self._scan_file(fpath, rel_path, ext)
                    vulnerabilities.extend(file_vulns)

        # 2. Dependency Audit
        dep_vulns = self._audit_dependencies(scan_root)
        vulnerabilities.extend(dep_vulns)

        # 3. Environment & Git Ignore Security Audit
        env_vulns = self._audit_environment_configs(scan_root)
        vulnerabilities.extend(env_vulns)

        # Sort vulnerabilities by severity (CRITICAL first)
        severity_rank = {
            Severity.CRITICAL: 4,
            Severity.HIGH: 3,
            Severity.MEDIUM: 2,
            Severity.LOW: 1,
            Severity.INFO: 0
        }
        vulnerabilities.sort(key=lambda v: severity_rank.get(v.severity, 0), reverse=True)

        # Calculate metrics
        stats = {
            "critical": sum(1 for v in vulnerabilities if v.severity == Severity.CRITICAL),
            "high": sum(1 for v in vulnerabilities if v.severity == Severity.HIGH),
            "medium": sum(1 for v in vulnerabilities if v.severity == Severity.MEDIUM),
            "low": sum(1 for v in vulnerabilities if v.severity == Severity.LOW),
            "info": sum(1 for v in vulnerabilities if v.severity == Severity.INFO),
            "total": len(vulnerabilities),
        }

        # Calculate security health score (0-100)
        # Deductions: CRITICAL = -25, HIGH = -15, MEDIUM = -5, LOW = -1
        penalty = (stats["critical"] * 25) + (stats["high"] * 15) + (stats["medium"] * 5) + (stats["low"] * 1)
        security_score = max(0, 100 - penalty)

        elapsed = (datetime.datetime.now() - start_time).total_seconds()
        print(f"🛡️  [VulnerabilityScanner] Scan complete in {elapsed:.2f}s! Found {stats['total']} issues (Security Score: {security_score}/100)\n")

        return {
            "success": True,
            "project_name": os.path.basename(os.path.abspath(scan_root)),
            "scan_root": os.path.abspath(scan_root),
            "files_scanned": files_scanned,
            "elapsed_seconds": elapsed,
            "security_score": security_score,
            "stats": stats,
            "vulnerabilities": [v.to_dict() for v in vulnerabilities],
            "findings_objects": [v.to_finding() for v in vulnerabilities],
        }

    def _scan_file(self, full_path: str, rel_path: str, ext: str) -> List[Vulnerability]:
        """Scans a single file for known vulnerability patterns and anti-patterns."""
        vulns: List[Vulnerability] = []

        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception:
            return vulns

        # -------------------------------------------------------------
        # 1. HARDCODED SECRETS & CREDENTIALS (All file types)
        # -------------------------------------------------------------
        secret_patterns = [
            (
                r'(?i)(?:api_key|apikey|secret_key|private_key|auth_token|access_token|secret)\s*[:=]\s*["\']([a-zA-Z0-9_\-\.]{20,})["\']',
                "Hardcoded Secret / API Token Detected",
                "CWE-798: Use of Hard-coded Credentials (OWASP A07)",
                Severity.CRITICAL,
                8.9,
                "Embedding production tokens directly in source code allows anyone with read access to compromise associated services.",
                "Extract credentials into environment variables (.env) or use a secure secret manager (e.g. AWS Secrets Manager, HashiCorp Vault).",
                'api_key = os.getenv("API_KEY")'
            ),
            (
                r'AIza[0-9A-Za-z-_]{35}',
                "Exposed Google / Gemini API Key",
                "CWE-798: Exposed Cloud API Key",
                Severity.CRITICAL,
                9.1,
                "Google Gemini/Cloud API Key is hardcoded in source text. Exposed keys risk quota exhaustion, unauthorized LLM calls, and financial billing.",
                "Revoke and rotate this API key immediately in Google Cloud Console. Store new key in .env outside version control.",
                'GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")'
            ),
            (
                r'gsk_[a-zA-Z0-9]{40,}',
                "Exposed Groq API Key",
                "CWE-798: Exposed LLM API Key",
                Severity.CRITICAL,
                9.0,
                "Groq LLM key is hardcoded directly in file. Threat actors can use your inference allocation.",
                "Rotate the Groq API key in your console and access it exclusively via os.getenv('GROQ_API_KEY').",
                'groq_key = os.getenv("GROQ_API_KEY")'
            ),
            (
                r'AKIA[0-9A-Z]{16}',
                "Exposed AWS Access Key ID",
                "CWE-798: Exposed Cloud Credentials",
                Severity.CRITICAL,
                9.5,
                "Active AWS Access Key ID found. Compromised credentials can lead to complete infrastructure takeover.",
                "Invalidate this key immediately in AWS IAM and configure IAM roles or AWS CLI credentials.",
                'aws_key = os.environ.get("AWS_ACCESS_KEY_ID")'
            ),
            (
                r'-----BEGIN (?:RSA )?PRIVATE KEY-----',
                "Unencrypted Private Cryptographic Key in Source",
                "CWE-312: Cleartext Storage of Sensitive Information",
                Severity.CRITICAL,
                9.8,
                "Private RSA/SSH cryptographic key is stored in plain text within codebase repository.",
                "Remove private key from git history, rotate associated public certs, and load from secure filesystem paths with 0600 permissions.",
                'with open("/secure/keys/private.pem") as kf: ...'
            )
        ]

        # Scan each line for secrets (except in test files or .env files where keys are meant to be loaded)
        is_test_file = "test" in rel_path.lower()
        is_env_file = rel_path.endswith(".env") or "context_memory" in rel_path.lower()

        for idx, line in enumerate(lines, 1):
            line_str = line.strip()
            if not line_str or line_str.startswith("#") or line_str.startswith("//"):
                continue

            for pattern, title, cwe, sev, cvss, cause, sugg, fix in secret_patterns:
                # In .env files, only flag if .env is committed or public
                if is_env_file and "AIza" in pattern:
                    continue
                if is_test_file and sev == Severity.CRITICAL:
                    sev = Severity.HIGH

                if re.search(pattern, line):
                    vulns.append(
                        Vulnerability(
                            id=f"VULN-{len(vulns)+1:03d}",
                            title=title,
                            category="Sensitive Data Exposure",
                            severity=sev,
                            cwe=cwe,
                            cvss_score=cvss,
                            file_path=rel_path,
                            line_number=idx,
                            code_snippet=line_str[:120],
                            cause=cause,
                            suggestion=sugg,
                            fix_snippet=fix,
                        )
                    )

        # -------------------------------------------------------------
        # 2. PYTHON-SPECIFIC SAST (AST & Regex Analysis)
        # -------------------------------------------------------------
        if ext == ".py":
            # A. Command Injection Flaws
            for idx, line in enumerate(lines, 1):
                line_str = line.strip()

                # os.system(var)
                if re.search(r'\bos\.system\s*\(\s*(?!["\'][^"\']*["\']\s*\))', line):
                    vulns.append(
                        Vulnerability(
                            id=f"VULN-{len(vulns)+1:03d}",
                            title="Command Injection via os.system()",
                            category="Injection",
                            severity=Severity.HIGH,
                            cwe="CWE-78: OS Command Injection (OWASP A03)",
                            cvss_score=8.4,
                            file_path=rel_path,
                            line_number=idx,
                            code_snippet=line_str[:120],
                            cause="os.system() spawns a shell and executes arbitrary strings without sanitization. An attacker supplying input containing shell metacharacters (;, &, |) can run arbitrary system commands.",
                            suggestion="Replace os.system() with subprocess.run() using a parameterized argument list and shell=False.",
                            fix_snippet='subprocess.run(["command", arg1, arg2], check=True)'
                        )
                    )

                # subprocess with shell=True
                if "shell=True" in line and ("subprocess." in line or "Popen" in line):
                    vulns.append(
                        Vulnerability(
                            id=f"VULN-{len(vulns)+1:03d}",
                            title="Subprocess Invocation with shell=True",
                            category="Injection",
                            severity=Severity.HIGH,
                            cwe="CWE-78: Improper Neutralization of Special Elements used in an OS Command",
                            cvss_score=8.1,
                            file_path=rel_path,
                            line_number=idx,
                            code_snippet=line_str[:120],
                            cause="Using shell=True allows shell metacharacter expansion and variable substitution, facilitating command injection attacks if arguments contain untrusted inputs.",
                            suggestion="Avoid shell=True. Pass commands as a list of individual string tokens directly to the executable.",
                            fix_snippet='subprocess.run([binary_path, parameter], shell=False)'
                        )
                    )

                # eval() or exec() usage
                if re.search(r'\b(eval|exec)\s*\(', line) and not line_str.startswith("#"):
                    vulns.append(
                        Vulnerability(
                            id=f"VULN-{len(vulns)+1:03d}",
                            title="Dynamic Code Execution (eval/exec)",
                            category="Code Injection",
                            severity=Severity.CRITICAL,
                            cwe="CWE-94: Improper Control of Generation of Code ('Code Injection')",
                            cvss_score=9.6,
                            file_path=rel_path,
                            line_number=idx,
                            code_snippet=line_str[:120],
                            cause="Evaluating raw string inputs dynamically allows arbitrary Python code execution under the current process privileges.",
                            suggestion="Use ast.literal_eval() for parsing data literals, or implement a strict dispatch table/state machine.",
                            fix_snippet='import ast\nsafe_data = ast.literal_eval(untrusted_string)'
                        )
                    )

                # SQL Injection via formatted queries
                if re.search(r'(?i)(?:execute|raw|query)\s*\(\s*f["\'].*?(?:select|insert|update|delete|drop)\b', line) or \
                   re.search(r'(?i)(?:select|insert|update|delete)\s+.*?\s+%\s+[a-zA-Z_]', line):
                    vulns.append(
                        Vulnerability(
                            id=f"VULN-{len(vulns)+1:03d}",
                            title="SQL Injection via Formatted String Query",
                            category="Injection",
                            severity=Severity.CRITICAL,
                            cwe="CWE-89: SQL Injection (OWASP A03)",
                            cvss_score=9.3,
                            file_path=rel_path,
                            line_number=idx,
                            code_snippet=line_str[:120],
                            cause="Constructing SQL queries using f-strings or string concatenation bypasses database query parameterized escaping, enabling SQL injection attacks.",
                            suggestion="Utilize parameterized queries with query placeholders (?, %s, or named bind variables).",
                            fix_snippet='cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))'
                        )
                    )

                # Insecure Deserialization (pickle or unsafe yaml)
                if re.search(r'\bpickle\.(?:loads?|load)\s*\(', line):
                    vulns.append(
                        Vulnerability(
                            id=f"VULN-{len(vulns)+1:03d}",
                            title="Insecure Deserialization with Python pickle",
                            category="Deserialization",
                            severity=Severity.HIGH,
                            cwe="CWE-502: Deserialization of Untrusted Data (OWASP A08)",
                            cvss_score=8.8,
                            file_path=rel_path,
                            line_number=idx,
                            code_snippet=line_str[:120],
                            cause="The pickle module is not secure against erroneous or maliciously constructed data. Unpickling untrusted data can execute arbitrary arbitrary code via __reduce__.",
                            suggestion="Use secure serialization formats like JSON, Protocol Buffers, or MessagePack.",
                            fix_snippet='import json\ndata = json.loads(payload)'
                        )
                    )

                if "yaml.load(" in line and "Loader=yaml.SafeLoader" not in line and "SafeLoader" not in line:
                    vulns.append(
                        Vulnerability(
                            id=f"VULN-{len(vulns)+1:03d}",
                            title="Unsafe PyYAML Deserialization",
                            category="Deserialization",
                            severity=Severity.HIGH,
                            cwe="CWE-502: Unsafe YAML Loading",
                            cvss_score=8.5,
                            file_path=rel_path,
                            line_number=idx,
                            code_snippet=line_str[:120],
                            cause="yaml.load without specifying SafeLoader can instantiate arbitrary Python objects and execute malicious code.",
                            suggestion="Always use yaml.safe_load() or specify Loader=yaml.SafeLoader.",
                            fix_snippet='data = yaml.safe_load(yaml_content)'
                        )
                    )

                # Weak Hashing Algorithm (MD5 / SHA1 for security)
                if re.search(r'hashlib\.(?:md5|sha1)\s*\(', line):
                    vulns.append(
                        Vulnerability(
                            id=f"VULN-{len(vulns)+1:03d}",
                            title="Use of Cryptographically Broken Hash Algorithm (MD5/SHA1)",
                            category="Cryptography",
                            severity=Severity.MEDIUM,
                            cwe="CWE-328: Use of Weak Hash (OWASP A02)",
                            cvss_score=5.5,
                            file_path=rel_path,
                            line_number=idx,
                            code_snippet=line_str[:120],
                            cause="MD5 and SHA-1 suffer from well-documented collision vulnerabilities. If used for password hashing, integrity verification, or tokens, they can be broken.",
                            suggestion="Upgrade to SHA-256 / SHA-3 for digest integrity, or Argon2 / bcrypt for password storage.",
                            fix_snippet='import hashlib\ndigest = hashlib.sha256(data).hexdigest()'
                        )
                    )

                # Disabled SSL Verification
                if "verify=False" in line:
                    vulns.append(
                        Vulnerability(
                            id=f"VULN-{len(vulns)+1:03d}",
                            title="Disabled TLS/SSL Certificate Verification",
                            category="Network Security",
                            severity=Severity.HIGH,
                            cwe="CWE-295: Improper Certificate Validation",
                            cvss_score=7.4,
                            file_path=rel_path,
                            line_number=idx,
                            code_snippet=line_str[:120],
                            cause="Disabling SSL certificate verification (verify=False) exposes HTTP requests to Man-In-The-Middle (MITM) eavesdropping and traffic tampering.",
                            suggestion="Enable certificate validation (verify=True) or supply a custom trusted CA bundle.",
                            fix_snippet='response = requests.get(url, verify=True, timeout=10)'
                        )
                    )

                # Path Traversal vulnerability
                if re.search(r'os\.path\.join\s*\(.*,\s*[a-zA-Z_0-9]+(?:filename|name|path)\b', line) and "abspath" not in line:
                    # Check if line does sanitization
                    if not any(k in line for k in ["os.path.basename", "secure_filename"]):
                        vulns.append(
                            Vulnerability(
                                id=f"VULN-{len(vulns)+1:03d}",
                                title="Potential Path Traversal in File Resolution",
                                category="File Security",
                                severity=Severity.MEDIUM,
                                cwe="CWE-22: Improper Limitation of a Pathname to a Restricted Directory ('Path Traversal')",
                                cvss_score=6.8,
                                file_path=rel_path,
                                line_number=idx,
                                code_snippet=line_str[:120],
                                cause="Joining paths directly with unsanitized user filenames can allow '../' sequence directory traversal outside the intended directory.",
                                suggestion="Wrap filenames with os.path.basename() and verify the resolved path starts with the intended base directory.",
                                fix_snippet='safe_name = os.path.basename(filename)\nfull_path = os.path.abspath(os.path.join(base_dir, safe_name))'
                            )
                        )

        return vulns

    def _audit_dependencies(self, scan_root: str) -> List[Vulnerability]:
        """Audits project requirements.txt for unpinned dependencies or known vulnerable packages."""
        vulns: List[Vulnerability] = []
        req_path = os.path.join(scan_root, "requirements.txt")
        if not os.path.exists(req_path):
            return vulns

        try:
            with open(req_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            return vulns

        unpinned_count = 0
        for idx, line in enumerate(lines, 1):
            pkg_line = line.strip()
            if not pkg_line or pkg_line.startswith("#"):
                continue

            # Flag completely unpinned package lines
            if not any(op in pkg_line for op in ["==", ">=", "<=", "~="]):
                unpinned_count += 1
                vulns.append(
                    Vulnerability(
                        id=f"VULN-DEP-{len(vulns)+1:03d}",
                        title=f"Unpinned Dependency Version: '{pkg_line}'",
                        category="Supply Chain / Dependencies",
                        severity=Severity.LOW,
                        cwe="CWE-1104: Use of Unmaintained or Uncontrolled Third-Party Components",
                        cvss_score=3.7,
                        file_path="requirements.txt",
                        line_number=idx,
                        code_snippet=pkg_line,
                        cause="Unpinned dependencies install the latest available upstream version upon deployment, introducing risk of breaking changes or upstream malicious package takeovers.",
                        suggestion="Pin the package to an exact known verified version with '==' (e.g. package==1.2.3).",
                        fix_snippet=f"{pkg_line}==1.0.0"
                    )
                )

        return vulns

    def _audit_environment_configs(self, scan_root: str) -> List[Vulnerability]:
        """Audits repository configuration such as .gitignore, sensitive files, and exposure."""
        vulns: List[Vulnerability] = []

        # Check if .env exists but is not listed in .gitignore
        env_file = os.path.join(scan_root, ".env")
        gitignore_file = os.path.join(scan_root, ".gitignore")

        if os.path.exists(env_file):
            has_gitignore = os.path.exists(gitignore_file)
            ignored_env = False
            if has_gitignore:
                try:
                    with open(gitignore_file, "r", encoding="utf-8") as f:
                        content = f.read()
                        if ".env" in content:
                            ignored_env = True
                except Exception:
                    pass

            if not ignored_env:
                vulns.append(
                    Vulnerability(
                        id=f"VULN-CFG-{len(vulns)+1:03d}",
                        title="Environment Secret File (.env) Not Excluded in .gitignore",
                        category="Configuration & Credentials",
                        severity=Severity.HIGH,
                        cwe="CWE-552: Files or Directories Accessible to External Parties",
                        cvss_score=7.8,
                        file_path=".gitignore" if has_gitignore else ".env",
                        line_number=1,
                        code_snippet=".env exists in project root but is not excluded in .gitignore",
                        cause="Without adding .env to .gitignore, sensitive environment variables, private API keys, and database passwords can be inadvertently pushed to public or team version control.",
                        suggestion="Append '.env' and '*.env' to .gitignore immediately.",
                        fix_snippet=".env\n*.env\n.env.local"
                    )
                )

        return vulns
