"""
Neura Multi-Agent System - Central Orchestrator.
Coordinates specialized agents (Project, Screen, Monitor, Skill),
dispatches single and multi-agent workflows, synthesizes unified intelligence,
and manages proactive notifications and task lifecycle tracking.
"""

import os
import threading
from typing import Dict, Any, List, Optional, Tuple
from brain.agents.event_system import EventBus, Event, EventType, Severity, Finding
from brain.agents.task_manager import TaskManager, Task, TaskState, PermissionLevel
from brain.agents.project_agent import ProjectAgent
from brain.agents.screen_agent import ScreenAgent
from brain.agents.monitor_agent import MonitorAgent
from brain.agents.skill_agent import SkillAgent

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

        self._lock = threading.RLock()
        self._proactive_listener_active = True

    # -------------------------------------------------------------
    # 1. Project Testing & Inspection Workflow
    # -------------------------------------------------------------
    def test_project(self, workspace: Optional[str] = None) -> str:
        """
        Coordinates full project testing:
        - Identifies structure & tech stack
        - Audits dependencies
        - Validates syntax
        - Executes available test suites
        - Categorizes findings by severity
        """
        target_ws = workspace or self.workspace
        task = self.task_manager.create_task(
            task_type="project_test",
            description=f"Inspect and test project '{os.path.basename(target_ws)}'",
            assigned_agents=["ProjectAgent"],
            required_permission=PermissionLevel.OBSERVE,
            metadata={"workspace": target_ws},
        )

        result = self.project_agent.run_safe(task)
        summary = result.get("summary")
        if summary:
            return summary
        elif result.get("error"):
            return f"Project testing encountered an error: {result['error']}. Neura remains running."
        else:
            return "Project testing completed."

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

    def get_agents_status_dict(self) -> Dict[str, Any]:
        """Returns structured dictionary of all agents' live statuses and current tasks."""
        agents_map = {
            "ProjectAgent": (self.project_agent, "Code & Architecture"),
            "ScreenAgent": (self.screen_agent, "Vision & Screen Control"),
            "MonitorAgent": (self.monitor_agent, "System & Process Monitoring"),
            "SkillAgent": (self.skill_agent, "Domain Skills & Tools"),
        }
        res = {}
        for key, (agent, role) in agents_map.items():
            curr_task = ""
            if agent._active_task_ids:
                t_id = agent._active_task_ids[-1]
                t_obj = self.task_manager.get_task(t_id)
                if t_obj:
                    curr_task = t_obj.description
            res[key] = {
                "name": agent.name,
                "role": role,
                "status": agent.status.value,
                "task": curr_task,
            }
        return res

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
