"""
Neura Multi-Agent System - Base Agent Interface.
Provides common contract, state management, event emission, and error isolation.
"""

import traceback
from enum import Enum
from typing import Dict, Any, List, Optional
from brain.agents.event_system import (
    Event,
    EventType,
    Severity,
    Finding,
    FindingCategory,
    EventBus,
)
from brain.agents.task_manager import (
    Task,
    TaskState,
    PermissionLevel,
    TaskManager,
)

class AgentStatus(str, Enum):
    IDLE = "IDLE"
    BUSY = "BUSY"
    ERROR = "ERROR"
    STOPPED = "STOPPED"

class BaseAgent:
    """
    Abstract base agent ensuring unified lifecycle, resilient error handling,
    and standardized event emission.
    """
    def __init__(
        self,
        name: str,
        description: str,
        capabilities: Optional[List[str]] = None,
        event_bus: Optional[EventBus] = None,
        task_manager: Optional[TaskManager] = None,
    ):
        self.name = name
        self.description = description
        self.capabilities = capabilities or []
        self.status = AgentStatus.IDLE
        self.event_bus = event_bus or EventBus()
        self.task_manager = task_manager or TaskManager(self.event_bus)
        self._active_task_ids: List[str] = []

    def execute_task(self, task: Task) -> Dict[str, Any]:
        """Subclasses override this method to perform actual logic."""
        raise NotImplementedError(f"{self.name} must implement execute_task.")

    def run_safe(self, task: Task) -> Dict[str, Any]:
        """
        Executes a task wrapped with comprehensive error isolation.
        Guarantees that an uncaught error in an agent NEVER crashes Neura.
        """
        self.status = AgentStatus.BUSY
        self._active_task_ids.append(task.task_id)
        self.task_manager.update_task_state(task.task_id, TaskState.STARTED, 0.0, f"{self.name} started task.")

        try:
            self.emit_event(
                EventType.TASK_STARTED,
                Severity.INFO,
                f"{self.name} is executing: {task.description}",
                task_id=task.task_id,
            )
            result = self.execute_task(task)
            self.task_manager.complete_task(task.task_id, result)
            self.status = AgentStatus.IDLE
            return result
        except Exception as e:
            err_trace = traceback.format_exc()
            err_msg = f"{type(e).__name__}: {str(e)}"
            print(f"❌ [{self.name} Exception caught]: {err_msg}\n{err_trace}")
            
            self.status = AgentStatus.ERROR
            self.emit_event(
                EventType.ERROR_DETECTED,
                Severity.HIGH,
                f"Agent {self.name} encountered an error: {err_msg}",
                data={"error": err_msg, "traceback": err_trace},
                task_id=task.task_id,
            )
            self.task_manager.fail_task(task.task_id, err_msg)
            # Revert to IDLE after safe failure reporting
            self.status = AgentStatus.IDLE
            return {
                "success": False,
                "error": err_msg,
                "agent": self.name,
                "findings": [f.to_dict() for f in task.findings],
            }
        finally:
            if task.task_id in self._active_task_ids:
                self._active_task_ids.remove(task.task_id)

    def cancel_task(self, task_id: str, reason: str = "Cancelled by user") -> bool:
        """Attempts to cancel an active task execution."""
        if task_id in self._active_task_ids:
            self._active_task_ids.remove(task_id)
            self.task_manager.cancel_task(task_id, reason)
            self.status = AgentStatus.IDLE
            self.emit_event(
                EventType.TASK_CANCELLED,
                Severity.INFO,
                f"{self.name} cancelled task {task_id}: {reason}",
                task_id=task_id,
            )
            return True
        return False

    def emit_event(
        self,
        event_type: EventType,
        severity: Severity,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        task_id: str = "system"
    ):
        """Emits a structured event onto the EventBus."""
        event = Event(
            event_type=event_type,
            task_id=task_id,
            agent_name=self.name,
            severity=severity,
            message=message,
            data=data or {},
        )
        self.event_bus.publish(event)

    def emit_progress(self, task_id: str, percent: float, message: str):
        """Emits progress update."""
        self.task_manager.update_task_state(task_id, TaskState.RUNNING, percent, message)
        self.emit_event(
            EventType.TASK_PROGRESS,
            Severity.INFO,
            message,
            data={"progress": percent},
            task_id=task_id,
        )

    def emit_finding(self, task_id: str, finding: Finding):
        """Records a structured finding."""
        self.task_manager.add_finding(task_id, finding, agent_name=self.name)

    def emit_warning(self, task_id: str, message: str, data: Optional[Dict[str, Any]] = None):
        """Emits a warning event."""
        self.emit_event(
            EventType.WARNING_DETECTED,
            Severity.MEDIUM,
            message,
            data=data or {},
            task_id=task_id,
        )

    def emit_error(self, task_id: str, message: str, data: Optional[Dict[str, Any]] = None):
        """Emits an error event."""
        self.emit_event(
            EventType.ERROR_DETECTED,
            Severity.HIGH,
            message,
            data=data or {},
            task_id=task_id,
        )
