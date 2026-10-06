"""
Neura Multi-Agent System - Task Lifecycle & Permission Manager.
Defines Task model, TaskState transitions, PermissionLevel gates, and TaskManager.
"""

import time
import datetime
import threading
import uuid
from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from brain.agents.event_system import Finding, Event, EventType, Severity, EventBus

class TaskState(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    STARTED = "STARTED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    MONITORING = "MONITORING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class PermissionLevel(str, Enum):
    OBSERVE = "OBSERVE"   # Non-destructive reading: screen, files, processes, logs
    SUGGEST = "SUGGEST"   # Proposing recommendations, refactorings, or architecture changes
    EXECUTE = "EXECUTE"   # Modifying files, installing packages, running processes, registering skills

# Permission hierarchy: EXECUTE implies SUGGEST and OBSERVE
PERMISSION_ORDER = {
    PermissionLevel.OBSERVE: 1,
    PermissionLevel.SUGGEST: 2,
    PermissionLevel.EXECUTE: 3,
}

@dataclass
class Task:
    task_id: str
    task_type: str
    description: str
    assigned_agents: List[str] = field(default_factory=list)
    required_permission: PermissionLevel = PermissionLevel.OBSERVE
    state: TaskState = TaskState.CREATED
    progress: float = 0.0  # 0.0 to 100.0
    findings: List[Finding] = field(default_factory=list)
    error: Optional[str] = None
    result: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    completed_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value if isinstance(self.state, TaskState) else str(self.state)
        d["required_permission"] = self.required_permission.value if isinstance(self.required_permission, PermissionLevel) else str(self.required_permission)
        d["findings"] = [f.to_dict() if isinstance(f, Finding) else f for f in self.findings]
        return d

class TaskManager:
    """
    Central, thread-safe store and lifecycle controller for all tasks across
    Neura's multi-agent system.
    """
    def __init__(self, event_bus: Optional[EventBus] = None):
        self._lock = threading.RLock()
        self._tasks: Dict[str, Task] = {}
        self.event_bus = event_bus or EventBus()

    def create_task(
        self,
        task_type: str,
        description: str,
        assigned_agents: Optional[List[str]] = None,
        required_permission: PermissionLevel = PermissionLevel.OBSERVE,
        metadata: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None
    ) -> Task:
        """Instantiates and registers a new task with state CREATED."""
        with self._lock:
            tid = task_id or f"task_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"
            task = Task(
                task_id=tid,
                task_type=task_type,
                description=description,
                assigned_agents=assigned_agents or [],
                required_permission=required_permission,
                state=TaskState.CREATED,
                metadata=metadata or {}
            )
            self._tasks[tid] = task

        self.event_bus.publish(
            Event(
                event_type=EventType.TASK_CREATED,
                task_id=task.task_id,
                agent_name="TaskManager",
                severity=Severity.INFO,
                message=f"Task '{task.description}' created.",
                data={"task_type": task_type, "assigned_agents": task.assigned_agents}
            )
        )
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)

    def update_task_state(
        self,
        task_id: str,
        state: TaskState,
        progress: Optional[float] = None,
        message: Optional[str] = None
    ):
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task.state = state
            task.updated_at = datetime.datetime.now().isoformat()
            if progress is not None:
                task.progress = min(max(progress, 0.0), 100.0)

        ev_type = {
            TaskState.QUEUED: EventType.TASK_WAITING,
            TaskState.STARTED: EventType.TASK_STARTED,
            TaskState.RUNNING: EventType.TASK_PROGRESS,
            TaskState.MONITORING: EventType.MONITORING_STARTED,
            TaskState.COMPLETED: EventType.TASK_COMPLETED,
            TaskState.FAILED: EventType.TASK_FAILED,
            TaskState.CANCELLED: EventType.TASK_CANCELLED,
        }.get(state, EventType.TASK_PROGRESS)

        self.event_bus.publish(
            Event(
                event_type=ev_type,
                task_id=task.task_id,
                agent_name="TaskManager",
                severity=Severity.INFO,
                message=message or f"Task '{task.description}' changed state to {state.value}.",
                data={"state": state.value, "progress": task.progress}
            )
        )

    def add_finding(self, task_id: str, finding: Finding, agent_name: str = "Agent"):
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task.findings.append(finding)
            task.updated_at = datetime.datetime.now().isoformat()

        self.event_bus.publish(
            Event(
                event_type=EventType.FINDING_DETECTED,
                task_id=task_id,
                agent_name=agent_name,
                severity=finding.severity,
                message=f"[{finding.category.value}] {finding.title}: {finding.description}",
                data=finding.to_dict()
            )
        )

    def complete_task(self, task_id: str, result: Dict[str, Any], message: Optional[str] = None):
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task.state = TaskState.COMPLETED
            task.progress = 100.0
            task.result = result
            task.completed_at = datetime.datetime.now().isoformat()
            task.updated_at = task.completed_at

        self.event_bus.publish(
            Event(
                event_type=EventType.TASK_COMPLETED,
                task_id=task_id,
                agent_name="TaskManager",
                severity=Severity.INFO,
                message=message or f"Task '{task.description}' completed successfully.",
                data={"result": result}
            )
        )

    def fail_task(self, task_id: str, error: str, message: Optional[str] = None):
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task.state = TaskState.FAILED
            task.error = error
            task.completed_at = datetime.datetime.now().isoformat()
            task.updated_at = task.completed_at

        self.event_bus.publish(
            Event(
                event_type=EventType.TASK_FAILED,
                task_id=task_id,
                agent_name="TaskManager",
                severity=Severity.HIGH,
                message=message or f"Task '{task.description}' failed: {error}",
                data={"error": error}
            )
        )

    def cancel_task(self, task_id: str, reason: str = "User cancelled"):
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            task.state = TaskState.CANCELLED
            task.completed_at = datetime.datetime.now().isoformat()
            task.updated_at = task.completed_at

        self.event_bus.publish(
            Event(
                event_type=EventType.TASK_CANCELLED,
                task_id=task_id,
                agent_name="TaskManager",
                severity=Severity.INFO,
                message=f"Task '{task.description}' was cancelled. Reason: {reason}",
                data={"reason": reason}
            )
        )
        return True

    def list_active_tasks(self) -> List[Task]:
        """Returns all currently active (RUNNING, STARTED, MONITORING, QUEUED, WAITING) tasks."""
        active_states = {
            TaskState.CREATED,
            TaskState.QUEUED,
            TaskState.STARTED,
            TaskState.RUNNING,
            TaskState.WAITING,
            TaskState.MONITORING,
        }
        with self._lock:
            return [t for t in self._tasks.values() if t.state in active_states]

    def list_all_tasks(self) -> List[Task]:
        with self._lock:
            return list(self._tasks.values())
