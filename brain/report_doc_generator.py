"""
Neura Multi-Agent System - Professional .doc & .docx Report Generator.
Generates comprehensive Microsoft Word documents containing project vulnerability audits,
system log error investigations, root causes, and actionable handling suggestions.
Converts to native binary .doc via Microsoft Word COM automation with fallback to .docx.
"""

import os
import sys
import datetime
from typing import Dict, Any, List, Optional
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def _set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Sets internal padding on a table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)


def _set_cell_shading(cell, color_hex):
    """Sets background fill color on a table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), color_hex)
    tcPr.append(shd)


class ReportDocGenerator:
    """
    Builds structured Microsoft Word documents for security vulnerabilities,
    system error audits, root causes, and handling suggestions.
    """

    def __init__(self, workspace: Optional[str] = None):
        self.workspace = workspace or os.getcwd()

    def generate_audit_report(
        self,
        vuln_report: Dict[str, Any],
        error_report: Dict[str, Any],
        computer_use_history: Optional[List[Dict[str, Any]]] = None,
        output_filename: str = "project_diagnosis_report.doc",
    ) -> Dict[str, Any]:
        """
        Creates a complete professional Word report (.doc and .docx).
        """
        print(f"\n📄 [ReportDocGenerator] Assembling comprehensive Word report...")

        doc = docx.Document()

        # Configure page margins
        for section in doc.sections:
            section.top_margin = Inches(1.0)
            section.bottom_margin = Inches(1.0)
            section.left_margin = Inches(1.0)
            section.right_margin = Inches(1.0)

        # Document Title
        title_p = doc.add_paragraph()
        title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title_run = title_p.add_run("NEURA AI — Vulnerability Assessment & Error Audit Report")
        title_run.font.name = "Calibri"
        title_run.font.size = Pt(22)
        title_run.font.bold = True
        title_run.font.color.rgb = RGBColor(16, 44, 87)  # Deep Navy

        # Subtitle / Metadata
        project_name = vuln_report.get("project_name", "Target Project")
        sub_p = doc.add_paragraph()
        sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sub_run = sub_p.add_run(
            f"Automated SAST Security Inspection, Runtime Log Auditing, Root Cause Analysis, and Remediation Blueprint\n"
            f"Project: {project_name} | Generated: {datetime.datetime.now().strftime('%B %d, %Y at %H:%M:%S')} | Auditor: Neura Multi-Agent System"
        )
        sub_run.font.size = Pt(10)
        sub_run.font.italic = True
        sub_run.font.color.rgb = RGBColor(90, 90, 90)

        doc.add_paragraph("―" * 55).alignment = WD_ALIGN_PARAGRAPH.CENTER

        def add_sec_heading(title, number=None):
            h = doc.add_paragraph()
            h.paragraph_format.space_before = Pt(16)
            h.paragraph_format.space_after = Pt(6)
            txt = f"{number}. {title}" if number is not None else title
            r = h.add_run(txt)
            r.font.name = "Calibri"
            r.font.size = Pt(15)
            r.font.bold = True
            r.font.color.rgb = RGBColor(26, 54, 110)
            return h

        def add_p(text, bold_prefix=None, space_after=4):
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(space_after)
            p.paragraph_format.line_spacing = 1.15
            if bold_prefix:
                br = p.add_run(bold_prefix)
                br.font.bold = True
                br.font.color.rgb = RGBColor(30, 30, 30)
            r = p.add_run(text)
            r.font.name = "Calibri"
            r.font.size = Pt(10.5)
            r.font.color.rgb = RGBColor(40, 40, 40)
            return p

        def add_code_block(code_text):
            tbl = doc.add_table(rows=1, cols=1)
            tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
            cell = tbl.cell(0, 0)
            _set_cell_shading(cell, "F1F5F9")
            _set_cell_margins(cell, top=80, bottom=80, left=140, right=140)
            cp = cell.paragraphs[0]
            cp.paragraph_format.space_before = Pt(2)
            cp.paragraph_format.space_after = Pt(2)
            crun = cp.add_run(code_text.strip())
            crun.font.name = "Consolas"
            crun.font.size = Pt(9.5)
            crun.font.color.rgb = RGBColor(30, 41, 59)
            doc.add_paragraph()  # Spacing

        # ==========================================
        # 1. Executive Summary & Audit Scorecard
        # ==========================================
        add_sec_heading("Executive Summary & Audit Scorecard", 1)
        v_stats = vuln_report.get("stats", {})
        e_stats = error_report.get("stats", {})
        score = vuln_report.get("security_score", 100)

        add_p(
            f"This audit report was generated autonomously by the Neura AI multi-agent architecture. "
            f"The assessment performed comprehensive Static Application Security Testing (SAST) across all project files, "
            f"screen perception and action loops, and ingested active application and runtime error logs."
        )

        # Scorecard Table
        tbl = doc.add_table(rows=2, cols=6)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        headers = ["Security Score", "Critical Vulns", "High Vulns", "Medium Vulns", "Low Vulns", "Log Errors"]
        vals = [
            f"{score}/100",
            str(v_stats.get("critical", 0)),
            str(v_stats.get("high", 0)),
            str(v_stats.get("medium", 0)),
            str(v_stats.get("low", 0)),
            str(e_stats.get("total_errors", 0)),
        ]

        for i, h in enumerate(headers):
            cell = tbl.cell(0, i)
            _set_cell_shading(cell, "102C57")
            p = cell.paragraphs[0]
            r = p.add_run(h)
            r.font.bold = True
            r.font.size = Pt(9.5)
            r.font.color.rgb = RGBColor(255, 255, 255)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        for i, val in enumerate(vals):
            cell = tbl.cell(1, i)
            _set_cell_shading(cell, "F8FAFC")
            p = cell.paragraphs[0]
            r = p.add_run(val)
            r.font.bold = True
            r.font.size = Pt(13)
            if i == 0:
                r.font.color.rgb = RGBColor(40, 167, 69) if score >= 80 else RGBColor(220, 53, 69)
            elif i in [1, 2] and int(val) > 0:
                r.font.color.rgb = RGBColor(220, 53, 69)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        doc.add_paragraph()

        # ==========================================
        # 2. Project Vulnerabilities Assessment
        # ==========================================
        add_sec_heading("Project Security Vulnerabilities (SAST)", 2)
        vulns = vuln_report.get("vulnerabilities", [])

        if not vulns:
            add_p("No security vulnerabilities were detected in the target workspace. All scanned files adhere to basic static security hygiene.")
        else:
            add_p(f"A total of {len(vulns)} security vulnerabilities were discovered across scanned project source files and configuration items:")

            # Summary Table
            v_tbl = doc.add_table(rows=len(vulns) + 1, cols=5)
            v_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
            v_headers = ["ID", "Severity", "Vulnerability Title", "CWE / Standard", "Location"]
            for i, h in enumerate(v_headers):
                cell = v_tbl.cell(0, i)
                _set_cell_shading(cell, "1E3E62")
                p = cell.paragraphs[0]
                r = p.add_run(h)
                r.font.bold = True
                r.font.size = Pt(9.5)
                r.font.color.rgb = RGBColor(255, 255, 255)

            for row_idx, v in enumerate(vulns, 1):
                sev = v.get("severity", "MEDIUM")
                row_cells = [
                    v.get("id", f"VULN-{row_idx}"),
                    sev,
                    v.get("title", "Untitled"),
                    v.get("cwe", "CWE-Unknown"),
                    f"{v.get('file_path')}:{v.get('line_number')}",
                ]
                bg_color = "FDF2F2" if sev in ["CRITICAL", "HIGH"] else "F8FAFC"
                for col_idx, cell_text in enumerate(row_cells):
                    cell = v_tbl.cell(row_idx, col_idx)
                    _set_cell_shading(cell, bg_color)
                    _set_cell_margins(cell, top=60, bottom=60, left=80, right=80)
                    p = cell.paragraphs[0]
                    r = p.add_run(cell_text)
                    r.font.size = Pt(9)
                    if col_idx == 1 and sev in ["CRITICAL", "HIGH"]:
                        r.font.bold = True
                        r.font.color.rgb = RGBColor(200, 35, 51)

            doc.add_paragraph()

            # Detailed Vulnerability Breakdown
            add_sec_heading("Detailed Vulnerability Analysis & Handling Suggestions", 3)
            for idx, v in enumerate(vulns, 1):
                sub_h = doc.add_paragraph()
                sub_h.paragraph_format.space_before = Pt(12)
                sub_h.paragraph_format.space_after = Pt(4)
                r = sub_h.add_run(f"2.{idx} [{v.get('severity')}] {v.get('title')} ({v.get('id')})")
                r.font.bold = True
                r.font.size = Pt(12)
                r.font.color.rgb = RGBColor(180, 40, 40) if v.get('severity') in ["CRITICAL", "HIGH"] else RGBColor(40, 80, 160)

                add_p(f"Location: {v.get('file_path')}, Line {v.get('line_number')} | Classification: {v.get('cwe')}")
                add_p(v.get("cause"), bold_prefix="Root Cause & Threat Vector: ")

                if v.get("code_snippet"):
                    add_p("Vulnerable Code Snippet:")
                    add_code_block(v.get("code_snippet"))

                add_p(v.get("suggestion"), bold_prefix="Handling Suggestion: ")

                if v.get("fix_snippet"):
                    add_p("Recommended Secure Replacement:")
                    add_code_block(v.get("fix_snippet"))

        # ==========================================
        # 3. System Logging & Runtime Error Audit
        # ==========================================
        add_sec_heading("System Logging, Auditing & Exception Analysis", 4)
        errors = error_report.get("errors", [])

        if not errors:
            add_p("No active fatal exceptions or anomalous runtime error dumps were found in inspected log files.")
        else:
            add_p(f"The automated audit identified {len(errors)} runtime error log entries across system logs and runtime bridges:")

            # Errors Table
            e_tbl = doc.add_table(rows=len(errors) + 1, cols=4)
            e_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
            e_headers = ["ID", "Error Type", "Source File", "Severity"]
            for i, h in enumerate(e_headers):
                cell = e_tbl.cell(0, i)
                _set_cell_shading(cell, "1E3E62")
                p = cell.paragraphs[0]
                r = p.add_run(h)
                r.font.bold = True
                r.font.size = Pt(9.5)
                r.font.color.rgb = RGBColor(255, 255, 255)

            for row_idx, e in enumerate(errors, 1):
                row_cells = [
                    e.get("id", f"ERR-{row_idx}"),
                    e.get("error_type", "Unknown Exception"),
                    e.get("source", "System"),
                    e.get("severity", "HIGH"),
                ]
                for col_idx, cell_text in enumerate(row_cells):
                    cell = e_tbl.cell(row_idx, col_idx)
                    _set_cell_shading(cell, "F8FAFC")
                    _set_cell_margins(cell, top=60, bottom=60, left=80, right=80)
                    p = cell.paragraphs[0]
                    r = p.add_run(cell_text)
                    r.font.size = Pt(9)

            doc.add_paragraph()

            # Detailed Error Explanations
            add_sec_heading("Error Diagnostics, Root Causes & Prevention Suggestions", 5)
            for idx, e in enumerate(errors, 1):
                eh = doc.add_paragraph()
                eh.paragraph_format.space_before = Pt(12)
                eh.paragraph_format.space_after = Pt(4)
                r = eh.add_run(f"4.{idx} [{e.get('severity')}] {e.get('error_type')} ({e.get('id')})")
                r.font.bold = True
                r.font.size = Pt(12)
                r.font.color.rgb = RGBColor(16, 44, 87)

                add_p(f"Log Origin: {e.get('source')}" + (f", Line {e.get('line_number')}" if e.get("line_number") else ""))
                if e.get("raw_message"):
                    add_p(e.get("raw_message"), bold_prefix="Raw Log Message: ")

                add_p(e.get("cause"), bold_prefix="Why this Error Occurs: ")
                add_p(e.get("handling_suggestion"), bold_prefix="Handling & Prevention Suggestion: ")

                if e.get("fix_code"):
                    add_p("Recommended Handling Code:")
                    add_code_block(e.get("fix_code"))

        # ==========================================
        # 4. Full Screen Automation Audit Trail
        # ==========================================
        add_sec_heading("Full-Screen Computer-Use Automation Audit", 6)
        if computer_use_history:
            add_p(f"Neura's ComputerUseAgent logged {len(computer_use_history)} autonomous screen interaction actions:")
            for h in computer_use_history:
                step_num = h.get("step", 1)
                action_name = h.get("action", "")
                status = h.get("status", "success")
                detail = h.get("result") or h.get("details") or str(h.get("params", {}))
                add_p(f"• Step {step_num} [{status.upper()}]: Action '{action_name}' — {detail}")
        else:
            add_p("ComputerUseAgent is standing by with full screen access permissions active. No autonomous action sequences were executed in this session.")

        # ==========================================
        # 5. Security Hardening Roadmap
        # ==========================================
        add_sec_heading("Security Hardening & Remediation Roadmap", 7)
        add_p("1. Immediate Actions (24 Hours):", bold_prefix="Priority 1: ")
        add_p("   • Rotate and revoke any hardcoded API keys detected in repository source files.")
        add_p("   • Append '.env' and '*.env' to .gitignore to prevent accidental remote git pushes.")
        add_p("   • Replace all raw os.system() and shell=True calls with parameterized subprocess executions.")

        add_p("2. Short-Term Safeguards (7 Days):", bold_prefix="Priority 2: ")
        add_p("   • Pin all package versions in requirements.txt with '==' to prevent dependency supply-chain risks.")
        add_p("   • Replace pickle.loads with json or safe_load serializers.")
        add_p("   • Implement try/except KeyboardInterrupt handlers around all camera and microphone acquisition loops.")

        add_p("3. Long-Term Architecture:", bold_prefix="Priority 3: ")
        add_p("   • Integrate automated pre-commit hooks to run Neura's VulnerabilityScanner before git commits.")
        add_p("   • Enforce TLS certificate verification (verify=True) across all external HTTP client sessions.")

        # Save DOCX
        docx_target = os.path.abspath(output_filename.replace(".doc", ".docx"))
        doc.save(docx_target)
        print(f"✅ [ReportDocGenerator] Saved DOCX: {docx_target}")

        # Native binary .doc conversion via Word COM automation
        doc_target = os.path.abspath(output_filename if output_filename.endswith(".doc") else f"{output_filename}.doc")
        doc_generated = False
        try:
            import win32com.client
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            wdoc = word.Documents.Open(docx_target)
            # Format 0 corresponds to wdFormatDocument (.doc binary)
            wdoc.SaveAs(doc_target, FileFormat=0)
            wdoc.Close()
            word.Quit()
            doc_generated = True
            print(f"✅ [ReportDocGenerator] Converted native Word .doc: {doc_target} (Size: {os.path.getsize(doc_target)} bytes)")
        except Exception as e:
            print(f"⚠️  [ReportDocGenerator] Word COM conversion notice: {e}. Fallback to direct .doc file.")
            # Binary copy as fallback so both .doc and .docx exist on disk
            try:
                import shutil
                shutil.copyfile(docx_target, doc_target)
                doc_generated = True
            except Exception:
                pass

        return {
            "success": True,
            "docx_path": docx_target,
            "doc_path": doc_target,
            "doc_generated": doc_generated,
        }
