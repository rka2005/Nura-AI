"""
Neura Multi-Agent System - User Presence & Multi-Channel Notification Service.
Detects user physical or interaction presence (camera, Windows idle time, memory state)
and dispatches findings via voice (if user is present) or email (if user is away).
"""

import os
import smtplib
import ctypes
import datetime
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, Any, List, Optional, Tuple


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


class NotificationService:
    """
    Manages intelligent dispatch of security audit and error findings.
    Determines whether the user is present or away, routing alerts via
    voice or email accordingly.
    """

    def __init__(self, voice_speaker_fn=None, memory_mgr=None):
        self.voice_speaker = voice_speaker_fn
        self.memory_mgr = memory_mgr

    def check_user_availability(self, idle_threshold_seconds: float = 90.0) -> Tuple[bool, str]:
        """
        Determines whether the user is physically present and available at the computer.
        Checks:
        1. Windows hardware input idle time (mouse/keyboard activity).
        2. MemoryManager user presence flag.
        """
        # 1. Check Windows user input idle time
        try:
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
                idle_seconds = millis / 1000.0

                if idle_seconds <= idle_threshold_seconds:
                    return True, f"User is active at computer (idle for {idle_seconds:.1f}s)."
                else:
                    return False, f"User is away from computer (idle for {idle_seconds:.1f}s > {idle_threshold_seconds}s limit)."
        except Exception:
            pass

        # 2. Check MemoryManager presence facts
        if self.memory_mgr:
            try:
                facts = self.memory_mgr.user_memory.get("user_facts", {})
                presence = facts.get("presence", "")
                if presence == "present":
                    return True, "User marked present in active memory facts."
                elif presence == "away":
                    return False, "User marked away in active memory facts."
            except Exception:
                pass

        # Default assumption: user is available
        return True, "User assumed available by default."

    def notify_user_audit_results(
        self,
        vuln_report: Dict[str, Any],
        error_report: Dict[str, Any],
        doc_path: Optional[str] = None,
        force_email: bool = False,
        force_voice: bool = False,
    ) -> Dict[str, Any]:
        """
        Dispatches the audit results via Voice (if available) or Email (if away).
        """
        is_available, availability_reason = self.check_user_availability()
        print(f"👤 [NotificationService] User Availability Check: {availability_reason} (Available: {is_available})")

        notification_log = {
            "is_available": is_available,
            "reason": availability_reason,
            "voice_spoken": False,
            "email_sent": False,
            "email_saved_to_disk": False,
            "doc_attached": bool(doc_path and os.path.exists(doc_path)),
        }

        # Build voice message focusing strictly on major vulnerabilities (Critical & High)
        vulns = vuln_report.get("vulnerabilities", [])
        major_vulns = [v for v in vulns if v.get("severity") in ["CRITICAL", "HIGH"]]
        doc_name = os.path.basename(doc_path) if doc_path else "report.doc"

        if major_vulns:
            count = len(major_vulns)
            major_titles = [v.get("title", "") for v in major_vulns[:3]]
            major_str = ", ".join(major_titles)
            more_str = f", plus {count - 3} more" if count > 3 else ""
            vuln_word = "major vulnerability" if count == 1 else "major vulnerabilities"
            voice_summary = (
                f"Sir, I have generated the full technical report in {doc_name}. "
                f"I detected {count} {vuln_word}: {major_str}{more_str}. "
                f"All root causes and handling suggestions are documented in your doc file."
            )
        else:
            voice_summary = (
                f"Sir, I have generated the full audit report in {doc_name}. "
                f"No major critical or high vulnerabilities were found in your project."
            )

        # 1. Voice Delivery (if user is available or forced)
        if (is_available or force_voice) and not force_email:
            print(f"🎙️  [NotificationService] Speaking audit findings to user...")
            if self.voice_speaker:
                try:
                    self.voice_speaker(voice_summary)
                    notification_log["voice_spoken"] = True
                except Exception as e:
                    print(f"[NotificationService] Voice speak note: {e}")
            else:
                print(f"[Neura Voice Output]: {voice_summary}")
                notification_log["voice_spoken"] = True

        # 2. Email Delivery (if user is NOT available, or force_email is requested)
        if (not is_available or force_email):
            print(f"📧 [NotificationService] User is away or email requested. Preparing email alert...")
            email_result = self.send_email_report(
                vuln_report=vuln_report,
                error_report=error_report,
                doc_path=doc_path,
                voice_summary=voice_summary,
            )
            notification_log.update(email_result)

        return notification_log

    def send_email_report(
        self,
        vuln_report: Dict[str, Any],
        error_report: Dict[str, Any],
        doc_path: Optional[str] = None,
        voice_summary: str = "",
    ) -> Dict[str, Any]:
        """
        Sends audit alert email via SMTP, attaching the .doc report.
        If SMTP is unconfigured, saves the rendered email to disk in audit_reports/.
        """
        v_stats = vuln_report.get("stats", {})
        e_stats = error_report.get("stats", {})
        score = vuln_report.get("security_score", 100)
        project_name = vuln_report.get("project_name", "Target Project")

        subject = f"[Neura AI Alert] Security & Error Audit Report: {project_name} (Score: {score}/100)"

        # Read environment SMTP configs
        smtp_host = os.getenv("SMTP_HOST", "").strip(" \"'")
        smtp_port = int(os.getenv("SMTP_PORT", "587").strip(" \"'") or 587)
        smtp_user = os.getenv("SMTP_USER", "").strip(" \"'")
        smtp_pass = os.getenv("SMTP_PASSWORD", "").strip(" \"'")
        receiver_email = os.getenv("ALERT_RECEIVER_EMAIL", "").strip(" \"'") or smtp_user or "user@local"

        # Build Rich HTML Content
        html_body = self._build_email_html(
            project_name=project_name,
            score=score,
            vuln_report=vuln_report,
            error_report=error_report,
            voice_summary=voice_summary,
            doc_path=doc_path,
        )

        plain_text = (
            f"NEURA AI SECURITY & ERROR AUDIT REPORT\n"
            f"Project: {project_name}\n"
            f"Security Health Score: {score}/100\n\n"
            f"SUMMARY:\n{voice_summary}\n\n"
            f"VULNERABILITIES FOUND: {v_stats.get('total', 0)} (Critical: {v_stats.get('critical', 0)}, High: {v_stats.get('high', 0)})\n"
            f"SYSTEM LOG ERRORS: {e_stats.get('total_errors', 0)}\n\n"
            f"Full technical report has been generated at: {doc_path or 'report.doc'}\n"
        )

        # Create MIME Message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_user or "neura.ai.assistant@gmail.com"
        msg["To"] = receiver_email
        msg.attach(MIMEText(plain_text, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        # Attach .doc / .docx if available
        if doc_path and os.path.exists(doc_path):
            try:
                with open(doc_path, "rb") as attachment:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename={os.path.basename(doc_path)}",
                )
                msg.attach(part)
            except Exception as e:
                print(f"[NotificationService] Attachment error: {e}")

        # Attempt SMTP Dispatch if configured
        email_sent = False
        if smtp_host and smtp_user and smtp_pass:
            try:
                print(f"📧 [NotificationService] Connecting to SMTP server {smtp_host}:{smtp_port}...")
                with smtplib.SMTP(smtp_host, smtp_port, timeout=12) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                    server.sendmail(smtp_user, [receiver_email], msg.as_string())
                email_sent = True
                print(f"✅ [NotificationService] Audit email successfully dispatched to {receiver_email}!")
            except Exception as smtp_err:
                print(f"⚠️  [NotificationService] SMTP dispatch failed: {smtp_err}")

        # Always save email draft to audit_reports directory for transparency and resilience
        reports_dir = os.path.join(os.getcwd(), "audit_reports")
        os.makedirs(reports_dir, exist_ok=True)
        ts_slug = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        draft_html_path = os.path.join(reports_dir, f"email_alert_{ts_slug}.html")
        draft_txt_path = os.path.join(reports_dir, f"email_alert_{ts_slug}.txt")

        try:
            with open(draft_html_path, "w", encoding="utf-8") as f:
                f.write(html_body)
            with open(draft_txt_path, "w", encoding="utf-8") as f:
                f.write(plain_text)
            print(f"💾 [NotificationService] Saved email alert copy to: {draft_html_path}")
        except Exception:
            pass

        return {
            "email_sent": email_sent,
            "email_saved_to_disk": True,
            "draft_html_path": draft_html_path,
            "receiver_email": receiver_email,
        }

    def _build_email_html(
        self,
        project_name: str,
        score: int,
        vuln_report: Dict[str, Any],
        error_report: Dict[str, Any],
        voice_summary: str,
        doc_path: Optional[str]
    ) -> str:
        """Renders responsive HTML template for security notification email."""
        v_stats = vuln_report.get("stats", {})
        e_stats = error_report.get("stats", {})
        vulns = vuln_report.get("vulnerabilities", [])[:5]
        errors = error_report.get("errors", [])[:5]

        vuln_rows = ""
        for v in vulns:
            sev = v.get("severity", "MEDIUM")
            color = "#d9534f" if sev in ["CRITICAL", "HIGH"] else "#f0ad4e"
            vuln_rows += f"""
            <tr style="border-bottom: 1px solid #eee;">
                <td style="padding: 10px; font-weight: bold; color: {color};">{sev}</td>
                <td style="padding: 10px;">{v.get('title')}</td>
                <td style="padding: 10px; font-family: monospace; font-size: 12px;">{v.get('file_path')}:{v.get('line_number')}</td>
                <td style="padding: 10px; font-size: 12px;">{v.get('suggestion')}</td>
            </tr>
            """

        error_rows = ""
        for e in errors:
            error_rows += f"""
            <tr style="border-bottom: 1px solid #eee;">
                <td style="padding: 10px; font-weight: bold; color: #d9534f;">{e.get('error_type')}</td>
                <td style="padding: 10px; font-family: monospace; font-size: 12px;">{e.get('source')}</td>
                <td style="padding: 10px; font-size: 12px;">{e.get('cause')}</td>
                <td style="padding: 10px; font-size: 12px;">{e.get('handling_suggestion')}</td>
            </tr>
            """

        score_color = "#28a745" if score >= 80 else ("#f0ad4e" if score >= 60 else "#d9534f")

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Neura Security Audit Alert</title>
</head>
<body style="font-family: Arial, sans-serif; background-color: #f7f9fc; margin: 0; padding: 20px; color: #333;">
<div style="max-width: 680px; margin: 0 auto; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border: 1px solid #e1e8ed;">

    <div style="background: linear-gradient(135deg, #102C57, #1679AB); padding: 24px; color: white;">
        <h1 style="margin: 0; font-size: 22px;">🛡️ NEURA AI — Automated Security & Error Audit</h1>
        <p style="margin: 6px 0 0; opacity: 0.85; font-size: 13px;">Target Project: {project_name} | {datetime.datetime.now().strftime('%B %d, %Y - %H:%M')}</p>
    </div>

    <div style="padding: 24px;">
        <div style="display: flex; align-items: center; justify-content: space-between; background: #f8fafc; border-left: 4px solid {score_color}; padding: 14px; border-radius: 4px; margin-bottom: 20px;">
            <div>
                <h3 style="margin: 0; color: #102C57;">Security Health Score</h3>
                <p style="margin: 4px 0 0; font-size: 13px; color: #666;">{voice_summary}</p>
            </div>
            <div style="font-size: 28px; font-weight: bold; color: {score_color}; padding-left: 16px;">
                {score}/100
            </div>
        </div>

        <h3 style="color: #102C57; border-bottom: 2px solid #eef2f6; padding-bottom: 6px;">Top Detected Vulnerabilities</h3>
        <table style="width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;">
            <thead>
                <tr style="background: #f1f5f9; color: #475569;">
                    <th style="padding: 8px;">Severity</th>
                    <th style="padding: 8px;">Vulnerability</th>
                    <th style="padding: 8px;">Location</th>
                    <th style="padding: 8px;">Handling Fix</th>
                </tr>
            </thead>
            <tbody>
                {vuln_rows if vuln_rows else "<tr><td colspan='4' style='padding:12px;'>No critical vulnerabilities found!</td></tr>"}
            </tbody>
        </table>

        <h3 style="color: #102C57; border-bottom: 2px solid #eef2f6; padding-bottom: 6px; margin-top: 24px;">System & Application Log Errors</h3>
        <table style="width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;">
            <thead>
                <tr style="background: #f1f5f9; color: #475569;">
                    <th style="padding: 8px;">Error Type</th>
                    <th style="padding: 8px;">Source</th>
                    <th style="padding: 8px;">Root Cause</th>
                    <th style="padding: 8px;">Remediation Suggestion</th>
                </tr>
            </thead>
            <tbody>
                {error_rows if error_rows else "<tr><td colspan='4' style='padding:12px;'>No active error logs found.</td></tr>"}
            </tbody>
        </table>

        <div style="margin-top: 28px; padding: 14px; background: #eef8ff; border-radius: 6px; border: 1px solid #bde0fe; font-size: 13px;">
            <strong>📎 Attached Technical Report:</strong> A complete Microsoft Word <code>{os.path.basename(doc_path) if doc_path else "report.doc"}</code> file has been generated with all vulnerabilities, line-by-line code snippets, root causes, and handling suggestions.
        </div>
    </div>

    <div style="background: #f1f5f9; padding: 14px; text-align: center; font-size: 12px; color: #64748b;">
        Generated autonomously by Neura AI Multi-Agent Security Engine.
    </div>
</div>
</body>
</html>
"""
