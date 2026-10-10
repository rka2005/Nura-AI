"""
Neura Multi-Agent System - Central Orchestrator.
Coordinates specialized agents (Project, Screen, Monitor, Skill),
dispatches single and multi-agent workflows, synthesizes unified intelligence,
and manages proactive notifications and task lifecycle tracking.
"""

import os
import time
import json
import threading
from typing import Dict, Any, List, Optional, Tuple
from brain.agents.event_system import EventBus, Event, EventType, Severity, Finding
from brain.agents.task_manager import TaskManager, Task, TaskState, PermissionLevel
from brain.agents.base_agent import AgentStatus
from brain.agents.project_agent import ProjectAgent
from brain.agents.screen_agent import ScreenAgent
from brain.agents.monitor_agent import MonitorAgent
from brain.agents.skill_agent import SkillAgent
from brain.agents.context_memory_agent import ContextMemoryAgent
from brain.agents.computer_use_agent import ComputerUseAgent
from brain.agents.security_scanner import VulnerabilityScanner
from brain.agents.error_auditor import ErrorAuditor
from brain.notification_service import NotificationService
from brain.report_doc_generator import ReportDocGenerator

class AgentOrchestrator:
    """
    Master coordinator for Neura's multi-agent architecture.
    Receives high-level user goals from neura.py, divides or routes them to specialized
    agents, and interprets multi-agent findings into unified responses.
    """
    def __init__(self, workspace: Optional[str] = None):
        self.workspace = workspace or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        self.event_bus = EventBus()
        self.task_manager = TaskManager(self.event_bus)

        # Specialized agents
        self.project_agent = ProjectAgent(
            event_bus=self.event_bus,
            task_manager=self.task_manager,
            default_workspace=self.workspace,
        )
        self.screen_agent = ScreenAgent(
            event_bus=self.event_bus,
            task_manager=self.task_manager,
        )
        self.monitor_agent = MonitorAgent(
            event_bus=self.event_bus,
            task_manager=self.task_manager,
        )
        self.skill_agent = SkillAgent(
            event_bus=self.event_bus,
            task_manager=self.task_manager,
        )
        self.memory_agent = ContextMemoryAgent(
            context_memory_dir=os.path.join(self.workspace, ".agents", "context_memory"),
            event_bus=self.event_bus,
            task_manager=self.task_manager,
        )

        # New Computer Use, Security Auditing, Error Logging & Report Generation Subsystems
        self.computer_use_agent = ComputerUseAgent(
            desktop_ctrl=self.screen_agent.desktop_ctrl,
            event_bus=self.event_bus,
            task_manager=self.task_manager,
        )
        self.security_scanner = VulnerabilityScanner(workspace=self.workspace)
        self.error_auditor = ErrorAuditor(workspace=self.workspace)
        self.notification_service = NotificationService(memory_mgr=None)
        self.report_generator = ReportDocGenerator(workspace=self.workspace)

        self._lock = threading.RLock()
        self._proactive_listener_active = True
        self.status_bridge_file = os.path.join(self.workspace, "status_bridge.json")
        self._custom_assigned_tasks: Dict[str, str] = {}
        self._release_timer: Optional[threading.Timer] = None
        self.active_test_session: Optional[Dict[str, Any]] = None
        self._test_worker_thread: Optional[threading.Thread] = None

        # Auto-subscribe to EventBus to sync live status on every event
        self.event_bus.subscribe(None, self._on_event_bus_update)

    # -------------------------------------------------------------
    # 1. Project Testing & Inspection Workflow
    # -------------------------------------------------------------
    def test_project(
        self,
        workspace: Optional[str] = None,
        target_file: Optional[str] = None,
        terminal_allowed: bool = False,
        target_name: Optional[str] = None,
        from_screen: bool = False,
        prefer_dedicated_gpu: bool = True,
    ) -> str:
        """
        Coordinates full project or specific file testing:
        - Identifies structure & tech stack
        - Audits dependencies & static AST syntax
        - Executes available test suites / scripts in terminal if terminal_allowed=True
        - Performs automated debugging for runtime errors
        - Categorizes findings by severity
        """
        target_ws = workspace or self.workspace
        target_desc = os.path.basename(target_file) if target_file else os.path.basename(target_ws)
        self.assign_agents_for_intent("AGENT_PROJECT_TEST", query=f"test {target_desc}")
        perm_level = PermissionLevel.EXECUTE if terminal_allowed else PermissionLevel.OBSERVE

        task = self.task_manager.create_task(
            task_type="file_test" if target_file else "project_test",
            description=f"Inspect and test '{target_desc}' (Terminal: {'ALLOWED' if terminal_allowed else 'OFF'})",
            assigned_agents=["ProjectAgent"],
            required_permission=perm_level,
            metadata={
                "workspace": target_ws,
                "target_file": target_file,
                "terminal_allowed": terminal_allowed,
                "target_name": target_name or target_desc,
                "from_screen": from_screen,
                "prefer_dedicated_gpu": prefer_dedicated_gpu,
            },
        )

        try:
            result = self.project_agent.run_safe(task)
            self.last_test_result = result
            summary = result.get("summary")
            if summary:
                return summary
            elif result.get("error"):
                return f"Project testing encountered an error: {result['error']}. Neura remains running."
            else:
                return "Project testing completed."
        finally:
            self.release_agents(grace_period=3.5)

    def start_background_test(
        self,
        workspace: Optional[str] = None,
        target_file: Optional[str] = None,
        terminal_allowed: bool = False,
        target_name: Optional[str] = None,
        from_screen: bool = False,
        prefer_dedicated_gpu: bool = True,
        on_complete_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Launches ProjectAgent test execution in a non-blocking background worker thread.
        Neura's main conversational brain remains completely unblocked and responsive
        to user speech, questions, and other operations.
        """
        with self._lock:
            if self.active_test_session and self.active_test_session.get("active"):
                return {
                    "already_running": True,
                    "target": self.active_test_session.get("target"),
                    "status": "RUNNING",
                    "started_at": self.active_test_session.get("started_at"),
                }

            target_ws = workspace or self.workspace
            target_desc = os.path.basename(target_file) if target_file else os.path.basename(target_ws)
            if target_name:
                target_desc = target_name

            session = {
                "active": True,
                "target": target_desc,
                "workspace": target_ws,
                "target_file": target_file,
                "terminal_allowed": terminal_allowed,
                "started_at": time.time(),
                "status": "RUNNING",
                "summary": None,
                "error": None,
                "result": None,
            }
            self.active_test_session = session

        def _worker():
            try:
                res_summary = self.test_project(
                    workspace=target_ws,
                    target_file=target_file,
                    terminal_allowed=terminal_allowed,
                    target_name=target_desc,
                    from_screen=from_screen,
                    prefer_dedicated_gpu=prefer_dedicated_gpu,
                )
                with self._lock:
                    if self.active_test_session:
                        self.active_test_session["active"] = False
                        self.active_test_session["status"] = "PASSED" if not "failed" in res_summary.lower() else "FAILED"
                        self.active_test_session["summary"] = res_summary
                        self.active_test_session["result"] = getattr(self, "last_test_result", None)

                if on_complete_callback and callable(on_complete_callback):
                    try:
                        on_complete_callback({
                            "summary": res_summary,
                            "last_test_result": getattr(self, "last_test_result", None),
                            "full_report": getattr(self, "last_test_result", {}).get("full_report") if getattr(self, "last_test_result", None) else None,
                        })
                    except Exception as cb_err:
                        logger.error(f"Error in background test callback: {cb_err}")

            except Exception as e:
                with self._lock:
                    if self.active_test_session:
                        self.active_test_session["active"] = False
                        self.active_test_session["status"] = "ERROR"
                        self.active_test_session["error"] = str(e)
            finally:
                with self._lock:
                    if self.active_test_session:
                        self.active_test_session["active"] = False

        thread = threading.Thread(target=_worker, daemon=True, name=f"Neura-TestAgent-{target_desc}")
        self._test_worker_thread = thread
        thread.start()

        return {
            "already_running": False,
            "target": target_desc,
            "status": "STARTED",
            "session": session,
        }

    def get_background_test_status(self) -> Dict[str, Any]:
        """Returns the current status of background test execution."""
        with self._lock:
            if not self.active_test_session:
                return {"active": False, "status": "IDLE"}

            session_copy = dict(self.active_test_session)
            # Read latest live_terminal data from status_bridge.json if available
            try:
                if os.path.exists(self.status_bridge_file):
                    with open(self.status_bridge_file, "r", encoding="utf-8") as f:
                        bridge_data = json.load(f)
                    if "live_terminal" in bridge_data:
                        session_copy["live_terminal"] = bridge_data["live_terminal"]
            except Exception:
                pass

            return session_copy

    def test_file(self, file_path: str, terminal_allowed: bool = False) -> str:
        """Convenience method to test a specific single file."""
        return self.test_project(target_file=file_path, terminal_allowed=terminal_allowed)

    # -------------------------------------------------------------
    # 2. Background Task Monitoring Workflow
    # -------------------------------------------------------------
    def start_monitoring(
        self,
        command: Optional[str] = None,
        pid: Optional[int] = None,
        log_file: Optional[str] = None,
        name: str = "Active Task",
    ) -> str:
        """
        Starts a non-blocking background monitoring session for a task or process.
        """
        task = self.task_manager.create_task(
            task_type="start_monitor",
            description=f"Monitor '{name}'",
            assigned_agents=["MonitorAgent"],
            required_permission=PermissionLevel.OBSERVE,
            metadata={"command": command, "pid": pid, "log_file": log_file, "name": name},
        )

        result = self.monitor_agent.run_safe(task)
        return result.get("message", f"Started monitoring for {name}.")

    def stop_monitoring(self, session_id: Optional[str] = None) -> str:
        """Stops active background monitoring."""
        stopped = self.monitor_agent.stop_session(session_id)
        if stopped:
            return "Background monitoring has been stopped."
        return "No active monitoring session found to stop."

    # -------------------------------------------------------------
    # 3. Multi-Agent Failure & Diagnostic Investigation
    # -------------------------------------------------------------
    def investigate_project_failure(self, workspace: Optional[str] = None) -> str:
        """
        Multi-agent collaboration:
        1. Project Agent inspects code, dependencies, and test suite.
        2. Screen Agent inspects screen and terminal for visible errors.
        3. Monitor Agent inspects active background processes and logs.
        Synthesizes a unified diagnostic report.
        """
        target_ws = workspace or self.workspace
        task = self.task_manager.create_task(
            task_type="multi_agent_investigation",
            description=f"Investigate project failure in {os.path.basename(target_ws)}",
            assigned_agents=["ProjectAgent", "ScreenAgent", "MonitorAgent"],
            required_permission=PermissionLevel.OBSERVE,
            metadata={"workspace": target_ws},
        )

        self.task_manager.update_task_state(task.task_id, TaskState.RUNNING, 10.0, "Multi-agent diagnostic started.")

        # 1. Project Agent Inspection
        p_task = Task(
            task_id=f"{task.task_id}_proj",
            task_type="project_test",
            description="Project code analysis",
            metadata={"workspace": target_ws},
        )
        p_res = self.project_agent.run_safe(p_task)
        p_findings = p_res.get("findings", [])

        # 2. Screen Agent Visual & Terminal Error Scan
        s_task = Task(
            task_id=f"{task.task_id}_scrn",
            task_type="detect_errors",
            description="Visible screen error scan",
        )
        s_res = self.screen_agent.run_safe(s_task)
        s_findings = s_res.get("findings", [])

        # 3. Monitor Agent Background Surveillance
        m_status = self.monitor_agent.get_all_sessions_status()

        # Combine all findings
        all_findings = []
        for f in p_findings + s_findings:
            all_findings.append(f)

        self.task_manager.complete_task(task.task_id, {
            "project_findings": p_findings,
            "screen_findings": s_findings,
            "monitor_sessions": m_status,
        })

        # Synthesize unified response
        sections = ["I investigated why the project is failing with my specialized agents."]

        # High/Critical errors
        crit_high = [f for f in all_findings if f.get("severity") in ["CRITICAL", "HIGH"]]
        if crit_high:
            sections.append("Primary Issues Discovered:")
            for item in crit_high[:3]:
                title = item.get("title", "Issue")
                desc = item.get("description", "")
                sections.append(f"• [{item.get('severity')}] {title}: {desc}")
        else:
            sections.append("I found no immediate CRITICAL or HIGH fatal errors in the codebase or screen.")

        # Screen observations
        if s_res.get("active_window"):
            sections.append(f"Visual Context: Active foreground window is '{s_res['active_window']}'.")

        # Medium / Architecture observations
        med_issues = [f for f in all_findings if f.get("severity") == "MEDIUM"]
        if med_issues:
            sections.append(f"Secondary Observations: Found {len(med_issues)} medium-priority issue(s) (e.g., {med_issues[0].get('title')}).")

        # Recommendation
        if crit_high:
            sections.append("Recommendation: Address the critical and high errors identified above first.")
        else:
            sections.append("All background agents are standing by.")

        return "\n\n".join(sections)

    # -------------------------------------------------------------
    # 4. Skill Learning Workflow
    # -------------------------------------------------------------
    def learn_workflow(
        self,
        name: str,
        steps: Optional[List[Dict[str, Any]]] = None,
        permission_granted: bool = False,
    ) -> str:
        """
        Creates, validates, and registers a reusable skill.
        """
        task = self.task_manager.create_task(
            task_type="learn_skill",
            description=f"Learn reusable skill '{name}'",
            assigned_agents=["SkillAgent"],
            required_permission=PermissionLevel.EXECUTE if permission_granted else PermissionLevel.SUGGEST,
            metadata={"name": name, "steps": steps or [], "permission_granted": permission_granted},
        )

        res = self.skill_agent.run_safe(task)
        return res.get("message", f"Processed skill '{name}'.")

    # -------------------------------------------------------------
    # 5. Task Status & "What are you doing?" Query
    # -------------------------------------------------------------
    def get_status_overview(self) -> str:
        """
        Produces a natural-language report of active tasks and agents.
        """
        active_tasks = self.task_manager.list_active_tasks()
        active_monitors = [s for s in self.monitor_agent.get_all_sessions_status() if s.get("active")]

        if not active_tasks and not active_monitors:
            return "I currently have no long-running background tasks. All specialized agents are idle and ready."

        parts = [f"I currently have {len(active_tasks) + len(active_monitors)} active operations:"]
        for t in active_tasks:
            agents_str = ", ".join(t.assigned_agents) if t.assigned_agents else "System"
            parts.append(f"• Task '{t.description}' is {t.state.value} (Progress: {t.progress:.0f}%, handled by {agents_str}).")

        for m in active_monitors:
            parts.append(f"• Monitor Agent is watching '{m['name']}' ({m['status']}).")

        return "\n".join(parts)

    def _on_event_bus_update(self, event: Event):
        """Callback triggered on any EventBus activity to immediately sync status_bridge.json."""
        try:
            self.publish_agents_bridge()
        except Exception:
            pass

    def publish_agents_bridge(self):
        """Thread-safe update of live agent states to status_bridge.json."""
        with self._lock:
            try:
                agents_dict = self.get_agents_status_dict()
                data = {}
                if os.path.exists(self.status_bridge_file):
                    try:
                        with open(self.status_bridge_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except Exception:
                        data = {}
                data["agents"] = agents_dict
                data["timestamp"] = time.time()

                # Determine active status
                busy_agents = [aid for aid, info in agents_dict.items() if info.get("status") in ["BUSY", "WORKING", "TESTING"]]
                if busy_agents:
                    data["status"] = "BUSY"
                    first_task = next((info.get("task") for info in agents_dict.values() if info.get("task")), "")
                    if first_task:
                        data["active_task"] = first_task
                else:
                    if data.get("status") == "BUSY":
                        data["status"] = "READY"
                        data["active_task"] = ""

                temp_bridge = f"{self.status_bridge_file}.tmp"
                with open(temp_bridge, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_bridge, self.status_bridge_file)
            except Exception:
                pass

    def get_agents_status_dict(self) -> Dict[str, Any]:
        """Returns structured dictionary of all agents' live statuses and current tasks."""
        # Monitor agent status
        monitor_busy = (
            self.monitor_agent.status == AgentStatus.BUSY
            or any(s.get("active") for s in self.monitor_agent.get_all_sessions_status())
            or "system_monitor" in self._custom_assigned_tasks
            or "MonitorAgent" in self._custom_assigned_tasks
        )

        # Project agent status
        proj_busy = (
            self.project_agent.status == AgentStatus.BUSY
            or "project_tester" in self._custom_assigned_tasks
            or "ProjectAgent" in self._custom_assigned_tasks
        )
        proj_task = self._custom_assigned_tasks.get("project_tester") or self._custom_assigned_tasks.get("ProjectAgent")
        if not proj_task and self.project_agent._active_task_ids:
            t = self.task_manager.get_task(self.project_agent._active_task_ids[-1])
            if t:
                proj_task = t.description

        # Screen agent status
        screen_busy = (
            self.screen_agent.status == AgentStatus.BUSY
            or "screen_vision" in self._custom_assigned_tasks
            or "ScreenAgent" in self._custom_assigned_tasks
        )
        screen_task = self._custom_assigned_tasks.get("screen_vision") or self._custom_assigned_tasks.get("ScreenAgent")
        if not screen_task and self.screen_agent._active_task_ids:
            t = self.task_manager.get_task(self.screen_agent._active_task_ids[-1])
            if t:
                screen_task = t.description

        # System monitor task
        sys_task = self._custom_assigned_tasks.get("system_monitor") or self._custom_assigned_tasks.get("MonitorAgent")
        if not sys_task:
            active_m = [s for s in self.monitor_agent.get_all_sessions_status() if s.get("active")]
            if active_m:
                sys_task = f"Monitoring: {active_m[0].get('name', 'Process')}"
            elif self.monitor_agent._active_task_ids:
                t = self.task_manager.get_task(self.monitor_agent._active_task_ids[-1])
                if t:
                    sys_task = t.description

        # Skill agent status
        skill_busy = (
            self.skill_agent.status == AgentStatus.BUSY
            or self.computer_use_agent.status == AgentStatus.BUSY
            or "skill_runner" in self._custom_assigned_tasks
            or "SkillAgent" in self._custom_assigned_tasks
        )
        skill_task = self._custom_assigned_tasks.get("skill_runner") or self._custom_assigned_tasks.get("SkillAgent")
        if not skill_task:
            if self.computer_use_agent._active_task_ids:
                t = self.task_manager.get_task(self.computer_use_agent._active_task_ids[-1])
                if t:
                    skill_task = t.description
            elif self.skill_agent._active_task_ids:
                t = self.task_manager.get_task(self.skill_agent._active_task_ids[-1])
                if t:
                    skill_task = t.description

        # Memory agent status
        mem_busy = (
            self.memory_agent.status == AgentStatus.BUSY
            or "memory_agent" in self._custom_assigned_tasks
            or "MemoryAgent" in self._custom_assigned_tasks
        )
        mem_task = self._custom_assigned_tasks.get("memory_agent") or self._custom_assigned_tasks.get("MemoryAgent")
        if not mem_task and self.memory_agent._active_task_ids:
            t = self.task_manager.get_task(self.memory_agent._active_task_ids[-1])
            if t:
                mem_task = t.description

        res = {
            # Lowercase keys for office_view.py
            "project_tester": {
                "name": "Project Tester",
                "role": "Code & Architecture",
                "status": "BUSY" if proj_busy else "IDLE",
                "task": proj_task or ("Running project test suite" if proj_busy else "")
            },
            "screen_vision": {
                "name": "Screen Vision",
                "role": "Vision & Screen Control",
                "status": "BUSY" if screen_busy else "IDLE",
                "task": screen_task or ("Inspecting active screen" if screen_busy else "")
            },
            "system_monitor": {
                "name": "System Monitor",
                "role": "System & Process Monitoring",
                "status": "BUSY" if monitor_busy else "IDLE",
                "task": sys_task or ("Monitoring system health" if monitor_busy else "")
            },
            "skill_runner": {
                "name": "Skill Runner",
                "role": "Domain Skills & Tools",
                "status": "BUSY" if skill_busy else "IDLE",
                "task": skill_task or ("Executing tool workflow" if skill_busy else "")
            },
            "memory_agent": {
                "name": "Memory Archivist",
                "role": "Dual-Tier Context & Knowledge",
                "status": "BUSY" if mem_busy else "IDLE",
                "task": mem_task or ("Updating memory archive" if mem_busy else "")
            },
            # PascalCase keys for backwards compatibility
            "ProjectAgent": {
                "name": "ProjectAgent",
                "role": "Code & Architecture",
                "status": "BUSY" if proj_busy else "IDLE",
                "task": proj_task or ""
            },
            "ScreenAgent": {
                "name": "ScreenAgent",
                "role": "Vision & Screen Control",
                "status": "BUSY" if screen_busy else "IDLE",
                "task": screen_task or ""
            },
            "MonitorAgent": {
                "name": "MonitorAgent",
                "role": "System & Process Monitoring",
                "status": "BUSY" if monitor_busy else "IDLE",
                "task": sys_task or ""
            },
            "SkillAgent": {
                "name": "SkillAgent",
                "role": "Domain Skills & Tools",
                "status": "BUSY" if skill_busy else "IDLE",
                "task": skill_task or ""
            },
            "MemoryAgent": {
                "name": "MemoryAgent",
                "role": "Dual-Tier Context & Knowledge",
                "status": "BUSY" if mem_busy else "IDLE",
                "task": mem_task or ""
            },
            "ComputerUseAgent": {
                "name": "ComputerUseAgent",
                "role": "Full Screen Autonomous Control",
                "status": "BUSY" if self.computer_use_agent.status == AgentStatus.BUSY else "IDLE",
                "task": skill_task or ""
            }
        }
        return res

    def assign_agents_for_intent(self, intent: str, metadata: Optional[Dict[str, Any]] = None, query: str = ""):
        """
        Dynamically assigns the appropriate agent(s) according to incoming intent/task,
        sets them to BUSY with descriptive task notes, and broadcasts immediately to status_bridge.json.
        """
        metadata = metadata or {}
        q = (query or "").strip().lower()
        with self._lock:
            # Cancel any pending release timer
            if self._release_timer:
                self._release_timer.cancel()
                self._release_timer = None

            # Reset custom assignments
            self._custom_assigned_tasks.clear()

            # 1. Project Testing & Inspection
            if intent in ["AGENT_PROJECT_TEST", "IntentType.AGENT_PROJECT_TEST"] or any(k in q for k in ["test", "testing", "run test"]):
                self.project_agent.status = AgentStatus.BUSY
                self._custom_assigned_tasks["project_tester"] = "Executing project test suite & AST syntax validation"
                self._custom_assigned_tasks["ProjectAgent"] = "Executing project test suite & AST syntax validation"

            # 2. Multi-Agent Diagnostics
            elif intent in ["AGENT_PROJECT_DIAGNOSTIC", "IntentType.AGENT_PROJECT_DIAGNOSTIC"] or "diagnos" in q:
                self.project_agent.status = AgentStatus.BUSY
                self.screen_agent.status = AgentStatus.BUSY
                self.monitor_agent.status = AgentStatus.BUSY
                self._custom_assigned_tasks["project_tester"] = "Investigating codebase architecture & syntax"
                self._custom_assigned_tasks["screen_vision"] = "Scanning screen and terminal for visible tracebacks"
                self._custom_assigned_tasks["system_monitor"] = "Inspecting system processes and runtime logs"

            # 3. Vulnerability Scan
            elif intent in ["AGENT_VULNERABILITY_SCAN", "IntentType.AGENT_VULNERABILITY_SCAN"] or "vulnerabilit" in q:
                self.project_agent.status = AgentStatus.BUSY
                self.monitor_agent.status = AgentStatus.BUSY
                self._custom_assigned_tasks["project_tester"] = "Scanning codebase for SAST security vulnerabilities"
                self._custom_assigned_tasks["system_monitor"] = "Auditing runtime error logs and exceptions"

            # 4. Error Audit
            elif intent in ["AGENT_ERROR_AUDIT", "IntentType.AGENT_ERROR_AUDIT"] or "error audit" in q:
                self.monitor_agent.status = AgentStatus.BUSY
                self._custom_assigned_tasks["system_monitor"] = "Auditing system error logs & tracebacks"

            # 5. Full Audit Report
            elif intent in ["AGENT_FULL_AUDIT_REPORT", "IntentType.AGENT_FULL_AUDIT_REPORT"]:
                self.project_agent.status = AgentStatus.BUSY
                self.monitor_agent.status = AgentStatus.BUSY
                self.skill_agent.status = AgentStatus.BUSY
                self._custom_assigned_tasks["project_tester"] = "Vulnerability security analysis"
                self._custom_assigned_tasks["system_monitor"] = "Diagnostic error audit"
                self._custom_assigned_tasks["skill_runner"] = "Generating comprehensive Word audit report"

            # 6. Autonomous Computer Use
            elif intent in ["AGENT_COMPUTER_USE", "IntentType.AGENT_COMPUTER_USE"] or "computer use" in q:
                self.computer_use_agent.status = AgentStatus.BUSY
                self.skill_agent.status = AgentStatus.BUSY
                self.screen_agent.status = AgentStatus.BUSY
                goal = metadata.get("goal") or query or "Automating on-screen actions"
                self._custom_assigned_tasks["skill_runner"] = f"Computer Use: {goal[:35]}"
                self._custom_assigned_tasks["screen_vision"] = "Perceiving active screen state"

            # 7. Screen Vision / Inspection
            elif intent in [
                "AGENT_SCREEN_INSPECT", "SCREEN_DESCRIBE", "SCREEN_CLICK", "SCREEN_OPEN",
                "SCREEN_PLAY", "SCREEN_SCROLL", "SCREEN_TYPE", "SCREEN_SEARCH",
                "SCREEN_INTERACT", "VISION_FACE_RECOGNIZE"
            ] or any(k in q for k in ["screen", "look at screen", "see on screen"]):
                self.screen_agent.status = AgentStatus.BUSY
                self._custom_assigned_tasks["screen_vision"] = f"Vision analysis: {query[:35] or 'Inspecting active screen'}"

            # 8. Background Monitoring
            elif intent in ["AGENT_MONITOR_START", "IntentType.AGENT_MONITOR_START"] or "monitor" in q:
                self.monitor_agent.status = AgentStatus.BUSY
                tname = metadata.get("name", "Active Background Task")
                self._custom_assigned_tasks["system_monitor"] = f"Monitoring: {tname}"

            # 9. Skills, Tools, Desktop Actions, Apps, Files
            elif intent in [
                "AGENT_SKILL_LEARN", "AGENT_SKILL_RUN", "SYSTEM_APP_OPEN", "SYSTEM_APP_CLOSE",
                "SYSTEM_FOLDER_OPEN", "SYSTEM_FILE_OPEN", "FILE_CREATE", "FILE_READ",
                "FILE_UPDATE", "FILE_DELETE", "FILE_LIST", "DESKTOP_SEARCH_IN_TAB",
                "DESKTOP_TYPE", "DESKTOP_HOTKEY", "DESKTOP_FIRST_LINK", "DESKTOP_SCREENSHOT"
            ]:
                self.skill_agent.status = AgentStatus.BUSY
                self._custom_assigned_tasks["skill_runner"] = f"Executing tool: {query[:35] or intent}"

            # 10. Memory & Alerts
            elif intent in [
                "SYSTEM_ALERT_SET", "SYSTEM_ALERT_LIST", "SYSTEM_ALERT_CANCEL",
                "SYSTEM_ALERT_STOP", "MEMORY_CLEAR", "MEMORY_INSPECT", "MEMORY_REMEMBER",
                "MEMORY_CONTEXT_QUERY"
            ] or any(k in q for k in ["alert", "alarm", "timer", "remember"]):
                self.memory_agent.status = AgentStatus.BUSY
                self._custom_assigned_tasks["memory_agent"] = f"Memory Vault: {query[:35] or intent}"

            # 11. Conversational Queries & Default
            else:
                self.memory_agent.status = AgentStatus.BUSY
                self._custom_assigned_tasks["memory_agent"] = "Searching dual-tier context & memories"

            self.publish_agents_bridge()

    def release_agents(self, grace_period: float = 3.0):
        """
        Gracefully returns busy agents back to IDLE after grace_period seconds,
        allowing the 3D office animations to cleanly complete their visible working cycle.
        """
        def _do_release():
            with self._lock:
                self._custom_assigned_tasks.clear()
                self.project_agent.status = AgentStatus.IDLE
                self.screen_agent.status = AgentStatus.IDLE
                self.skill_agent.status = AgentStatus.IDLE
                self.computer_use_agent.status = AgentStatus.IDLE
                # Keep monitor active only if active monitor sessions exist
                if not any(s.get("active") for s in self.monitor_agent.get_all_sessions_status()):
                    self.monitor_agent.status = AgentStatus.IDLE
                self.memory_agent.status = AgentStatus.IDLE
                self.publish_agents_bridge()

        if grace_period <= 0:
            _do_release()
        else:
            if self._release_timer:
                self._release_timer.cancel()
            self._release_timer = threading.Timer(grace_period, _do_release)
            self._release_timer.daemon = True
            self._release_timer.start()

    # -------------------------------------------------------------
    # 7. Autonomous Full-Screen Computer Use Workflow
    # -------------------------------------------------------------
    def execute_computer_use(self, goal: str, max_steps: int = 8) -> str:
        """
        Coordinates full-screen autonomous computer use like Gemini / Claude:
        Perceives screen, plans next actions, operates mouse/keyboard, and verifies state.
        """
        task = self.task_manager.create_task(
            task_type="computer_use",
            description=f"Autonomous Computer Use: {goal}",
            assigned_agents=["ComputerUseAgent", "ScreenAgent"],
            required_permission=PermissionLevel.EXECUTE,
            metadata={"goal": goal, "max_steps": max_steps},
        )
        res = self.computer_use_agent.run_safe(task)
        msg = res.get("message") or f"Executed computer use task '{goal}'."
        return msg

    # -------------------------------------------------------------
    # 8. Automated Project Vulnerability Scanning Workflow
    # -------------------------------------------------------------
    def scan_project_vulnerabilities(self, target_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Runs SAST security scanning for secrets, SQLi, command injection,
        broken crypto, deserialization, and dependency flaws.
        """
        scan_path = target_dir or self.workspace
        task = self.task_manager.create_task(
            task_type="vulnerability_scan",
            description=f"Security audit for {os.path.basename(scan_path)}",
            assigned_agents=["ProjectAgent"],
            required_permission=PermissionLevel.OBSERVE,
            metadata={"target_dir": scan_path},
        )
        report = self.security_scanner.scan_project(scan_path)
        for f in report.get("findings_objects", []):
            self.event_bus.publish(
                Event(
                    event_type=EventType.FINDING_DETECTED,
                    task_id=task.task_id,
                    agent_name="SecurityScanner",
                    severity=f.severity,
                    message=f"{f.title}: {f.description[:100]}",
                    data=f.to_dict(),
                )
            )
        self.task_manager.complete_task(task.task_id, report)
        return report

    # -------------------------------------------------------------
    # 9. System Logging & Error Auditing Workflow
    # -------------------------------------------------------------
    def audit_system_errors(self, target_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Audits application logs, runtime dumps, and tracebacks to understand
        error causes and produce handling suggestions.
        """
        scan_path = target_dir or self.workspace
        task = self.task_manager.create_task(
            task_type="error_audit",
            description=f"Error log audit for {os.path.basename(scan_path)}",
            assigned_agents=["MonitorAgent"],
            required_permission=PermissionLevel.OBSERVE,
            metadata={"target_dir": scan_path},
        )
        report = self.error_auditor.audit_all_logs(scan_path)
        for f in report.get("findings_objects", []):
            self.event_bus.publish(
                Event(
                    event_type=EventType.ERROR_DETECTED,
                    task_id=task.task_id,
                    agent_name="ErrorAuditor",
                    severity=f.severity,
                    message=f"{f.title}: {f.description[:100]}",
                    data=f.to_dict(),
                )
            )
        self.task_manager.complete_task(task.task_id, report)
        return report

    # -------------------------------------------------------------
    # 10. End-to-End Audit, Report Generation (.doc) & Notification
    # -------------------------------------------------------------
    def audit_and_generate_report(
        self,
        target_dir: Optional[str] = None,
        voice_speaker_fn=None,
        force_email: bool = False,
        output_doc_path: str = "report.doc",
    ) -> Dict[str, Any]:
        """
        End-to-end integration:
        1. Checks project vulnerabilities (SAST & dependencies).
        2. Audits system error logs & tracebacks with causes and handling suggestions.
        3. Creates professional Microsoft Word .doc (and .docx) report.
        4. Detects user availability: speaks voice summary if present, or dispatches email if away.
        """
        scan_path = target_dir or self.workspace
        print(f"\n🚀 [AgentOrchestrator] Running Complete Security & Error Audit on '{scan_path}'...")

        # 1. Vulnerability Scan
        vuln_report = self.scan_project_vulnerabilities(scan_path)

        # 2. Error Log Audit
        error_report = self.audit_system_errors(scan_path)

        # 3. Generate Word Document (.doc and .docx)
        doc_res = self.report_generator.generate_audit_report(
            vuln_report=vuln_report,
            error_report=error_report,
            computer_use_history=self.computer_use_agent.action_history,
            output_filename=output_doc_path,
        )
        doc_path = doc_res.get("doc_path") or os.path.abspath(output_doc_path)

        # 4. Notify User via Voice (if present) or Email (if away)
        if voice_speaker_fn:
            self.notification_service.voice_speaker = voice_speaker_fn

        notif_res = self.notification_service.notify_user_audit_results(
            vuln_report=vuln_report,
            error_report=error_report,
            doc_path=doc_path,
            force_email=force_email,
        )

        v_stats = vuln_report.get("stats", {})
        e_stats = error_report.get("stats", {})
        score = vuln_report.get("security_score", 100)

        vulns = vuln_report.get("vulnerabilities", [])
        major_vulns = [v for v in vulns if v.get("severity") in ["CRITICAL", "HIGH"]]

        if major_vulns:
            count = len(major_vulns)
            major_titles = [v.get("title", "") for v in major_vulns[:3]]
            major_str = ", ".join(major_titles)
            more_str = f", plus {count - 3} more" if count > 3 else ""
            vuln_word = "major vulnerability" if count == 1 else "major vulnerabilities"
            summary_msg = (
                f"Security audit complete. Detected {count} {vuln_word}: {major_str}{more_str}. "
                f"The complete technical report with all vulnerabilities, errors, and handling suggestions has been generated in '{os.path.basename(doc_path)}'."
            )
        else:
            summary_msg = (
                f"Security audit complete with no major critical or high vulnerabilities. "
                f"The full technical report has been generated in '{os.path.basename(doc_path)}'."
            )

        return {
            "success": True,
            "summary": summary_msg,
            "security_score": score,
            "vuln_report": vuln_report,
            "error_report": error_report,
            "doc_path": doc_path,
            "docx_path": doc_res.get("docx_path"),
            "notification": notif_res,
        }

    # -------------------------------------------------------------
    # 6. Proactive Communication Queue
    # -------------------------------------------------------------
    def get_proactive_announcements(self) -> List[str]:
        """
        Retrieves unannounced proactive events and converts them into
        natural, non-intrusive messages for Neura to speak or display.
        """
        events = self.event_bus.pop_proactive_notifications()
        announcements = []

        for ev in events:
            if ev.severity == Severity.CRITICAL:
                announcements.append(f"Attention Sir: {ev.message}")
            elif ev.event_type == EventType.TASK_COMPLETED:
                announcements.append(f"Update: {ev.message}")
            elif ev.event_type == EventType.TASK_FAILED:
                announcements.append(f"Alert: {ev.message}")
            elif ev.severity == Severity.HIGH:
                announcements.append(f"Notice: {ev.message}")

        return announcements


# Global singleton instance
_GLOBAL_ORCHESTRATOR: Optional[AgentOrchestrator] = None

def get_orchestrator(workspace: Optional[str] = None) -> AgentOrchestrator:
    global _GLOBAL_ORCHESTRATOR
    if _GLOBAL_ORCHESTRATOR is None:
        _GLOBAL_ORCHESTRATOR = AgentOrchestrator(workspace)
    return _GLOBAL_ORCHESTRATOR
