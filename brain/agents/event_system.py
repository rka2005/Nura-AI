"""
Neura Multi-Agent System - Event System & Severity Framework.
Defines standard events, severities, finding categories, and thread-safe EventBus.
"""

import time
import datetime
import threading
from enum import Enum
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict

class EventType(str, Enum):
    TASK_CREATED = "TASK_CREATED"
    TASK_STARTED = "TASK_STARTED"
    TASK_PROGRESS = "TASK_PROGRESS"
    TASK_WAITING = "TASK_WAITING"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_CANCELLED = "TASK_CANCELLED"
    ERROR_DETECTED = "ERROR_DETECTED"
    WARNING_DETECTED = "WARNING_DETECTED"
    FINDING_DETECTED = "FINDING_DETECTED"
    MONITORING_STARTED = "MONITORING_STARTED"
    MONITORING_STOPPED = "MONITORING_STOPPED"
    IMPORTANT_UPDATE = "IMPORTANT_UPDATE"

class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

class FindingCategory(str, Enum):
    BUG = "BUG"
    WARNING = "WARNING"
    ARCHITECTURE_CONCERN = "ARCHITECTURE_CONCERN"
    IMPROVEMENT_SUGGESTION = "IMPROVEMENT_SUGGESTION"
    OPTIONAL_REFACTOR = "OPTIONAL_REFACTOR"
    VULNERABILITY = "VULNERABILITY"
    ERROR_LOG = "ERROR_LOG"

# Severity numeric rank for comparisons (higher = more severe)
SEVERITY_ORDER = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}

@dataclass
class Finding:
    category: FindingCategory
    severity: Severity
    title: str
    description: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    suggestion: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value if isinstance(self.category, FindingCategory) else str(self.category)
        d["severity"] = self.severity.value if isinstance(self.severity, Severity) else str(self.severity)
        return d

@dataclass
class Event:
    event_type: EventType
    task_id: str
    agent_name: str
    severity: Severity
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value if isinstance(self.event_type, EventType) else str(self.event_type)
        d["severity"] = self.severity.value if isinstance(self.severity, Severity) else str(self.severity)
        return d

class EventBus:
    """
    Thread-safe EventBus providing publish/subscribe, structured event logging,
    and a proactive notification filtering queue for Neura orchestrator.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self._events: List[Event] = []
        self._subscribers: Dict[str, List[Callable[[Event], None]]] = {}
        self._proactive_queue: List[Event] = []
        self._proactive_consumed: set = set()

    def subscribe(self, event_type: Optional[EventType], callback: Callable[[Event], None]):
        """Subscribes a callback to a specific event type or ALL events if event_type is None."""
        with self._lock:
            key = event_type.value if event_type else "*"
            if key not in self._subscribers:
                self._subscribers[key] = []
            self._subscribers[key].append(callback)

    def publish(self, event: Event):
        """Publishes an event to listeners and enqueues high-severity events for proactive notification."""
        with self._lock:
            self._events.append(event)

            # Determine if this event qualifies for proactive notification:
            # - CRITICAL or HIGH severity
            # - Process crash / abnormal termination
            # - Long-running background task completion or failure
            is_proactive = (
                event.severity in [Severity.CRITICAL, Severity.HIGH] or
                event.event_type in [EventType.TASK_COMPLETED, EventType.TASK_FAILED, EventType.IMPORTANT_UPDATE]
            )

            # Avoid spamming tiny progress events or info
            if is_proactive:
                event_uid = f"{event.task_id}_{event.event_type.value}_{event.timestamp}"
                if event_uid not in self._proactive_consumed:
                    self._proactive_queue.append(event)

            # Dispatch to subscribers
            handlers = list(self._subscribers.get(event.event_type.value, []))
            handlers.extend(self._subscribers.get("*", []))

        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                print(f"[EventBus Handler Error] {e}")

    def get_events(self, task_id: Optional[str] = None, min_severity: Optional[Severity] = None) -> List[Event]:
        """Retrieves history of recorded events with optional filtering."""
        with self._lock:
            events = list(self._events)

        if task_id:
            events = [e for e in events if e.task_id == task_id]

        if min_severity:
            min_rank = SEVERITY_ORDER.get(min_severity, 0)
            events = [e for e in events if SEVERITY_ORDER.get(e.severity, 0) >= min_rank]

        return events

    def pop_proactive_notifications(self) -> List[Event]:
        """Retrieves and clears unconsumed proactive events."""
        with self._lock:
            unhandled = list(self._proactive_queue)
            for ev in unhandled:
                uid = f"{ev.task_id}_{ev.event_type.value}_{ev.timestamp}"
                self._proactive_consumed.add(uid)
            self._proactive_queue.clear()
            return unhandled

    def clear(self):
        """Clears all logged events and subscriber state."""
        with self._lock:
            self._events.clear()
            self._proactive_queue.clear()
            self._proactive_consumed.clear()
