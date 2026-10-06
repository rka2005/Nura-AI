"""
Neura Multi-Agent System - Monitor Agent.
Provides background, non-blocking surveillance of system processes, training jobs,
subprocess execution, resource usage (CPU/RAM/GPU), and log files.
"""

import os
import re
import time
import psutil
import threading
import subprocess
from typing import Dict, Any, List, Optional, Callable
from brain.agents.base_agent import BaseAgent, AgentStatus
from brain.agents.task_manager import Task, TaskState, PermissionLevel
from brain.agents.event_system import (
    Event,
    EventType,
    Severity,
    Finding,
    FindingCategory,
)

class MonitoredSession:
    """Represents an active monitoring session running in a background thread."""
    def __init__(self, session_id: str, name: str, target_type: str, target: Any):
        self.session_id = session_id
        self.name = name
        self.target_type = target_type  # 'pid', 'process', 'command', 'logfile'
        self.target = target
        self.is_active = True
        self.thread: Optional[threading.Thread] = None
        self.start_time = time.time()
        self.last_cpu = 0.0
        self.last_ram = 0.0
        self.progress = 0.0
        self.logs: List[str] = []
        self.status_message = "Monitoring active"
        self.exit_code: Optional[int] = None
        self.error: Optional[str] = None

class MonitorAgent(BaseAgent):
    """
    Monitor Agent tracks running processes, commands, and logs in background threads,
    emitting real-time events for progress, resource spikes, errors, and completions.
    """
    def __init__(self, event_bus=None, task_manager=None):
        super().__init__(
            name="MonitorAgent",
            description="Performs non-blocking background surveillance of processes, logs, resource usage, and background jobs.",
            capabilities=[
                "process_monitoring",
                "subprocess_surveillance",
                "resource_tracking",
                "log_file_watching",
                "crash_detection",
                "milestone_progress_tracking",
            ],
            event_bus=event_bus,
            task_manager=task_manager,
        )
        self._sessions: Dict[str, MonitoredSession] = {}
        self._lock = threading.RLock()

    def execute_task(self, task: Task) -> Dict[str, Any]:
        """
        Executes a monitoring task:
        - 'start_monitor': kicks off background thread for a command or pid
        - 'stop_monitor': stops an existing session
        - 'status': reports current status of sessions
        """
        task_type = task.task_type.lower()
        metadata = task.metadata or {}

        if task_type in ["start_monitor", "monitor_task", "monitor_process", "monitor_training"]:
            session_id = f"mon_{task.task_id}"
            target_cmd = metadata.get("command")
            target_pid = metadata.get("pid")
            log_path = metadata.get("log_file")
            name = metadata.get("name") or task.description

            if target_cmd:
                session = self._start_command_monitor(session_id, name, target_cmd, task.task_id)
            elif target_pid:
                session = self._start_pid_monitor(session_id, name, int(target_pid), task.task_id)
            elif log_path:
                session = self._start_logfile_monitor(session_id, name, log_path, task.task_id)
            else:
                # Default: monitor overall system and background active workloads
                session = self._start_system_monitor(session_id, name, task.task_id)

            with self._lock:
                self._sessions[session_id] = session

            self.task_manager.update_task_state(task.task_id, TaskState.MONITORING, 0.0, f"Monitoring started for {name}.")
            return {
                "success": True,
                "session_id": session_id,
                "message": f"Background monitoring started for '{name}'. You may continue working freely.",
            }

        elif task_type in ["stop_monitor", "cancel_monitor"]:
            session_id = metadata.get("session_id")
            stopped = self.stop_session(session_id)
            return {"success": stopped, "session_id": session_id}

        elif task_type in ["get_status", "status"]:
            status_data = self.get_all_sessions_status()
            return {"success": True, "sessions": status_data}

        else:
            return {"success": False, "error": f"Unknown monitor task type: {task_type}"}

    def _start_command_monitor(self, session_id: str, name: str, cmd: str, task_id: str) -> MonitoredSession:
        """Launches a shell command and tracks its output, progress, errors, and exit."""
        session = MonitoredSession(session_id, name, "command", cmd)

        def _worker():
            self.emit_event(
                EventType.MONITORING_STARTED,
                Severity.INFO,
                f"Started background process for: '{name}'",
                data={"command": cmd, "session_id": session_id},
                task_id=task_id,
            )
            try:
                proc = subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                )

                milestones_hit = set()

                while session.is_active and proc.poll() is None:
                    line = proc.stdout.readline()
                    if line:
                        clean_line = line.strip()
                        session.logs.append(clean_line)

                        # Detect progress numbers or percentage
                        pct_match = re.search(r"(\d{1,3})%", clean_line)
                        if pct_match:
                            val = float(pct_match.group(1))
                            session.progress = val
                            # Proactively announce major milestones (25%, 50%, 75%, 100%)
                            for m in [25, 50, 75]:
                                if val >= m and m not in milestones_hit:
                                    milestones_hit.add(m)
                                    self.emit_event(
                                        EventType.TASK_PROGRESS,
                                        Severity.INFO,
                                        f"Task '{name}' progress: {m}%",
                                        data={"progress": m, "session_id": session_id},
                                        task_id=task_id,
                                    )

                        # Detect warnings in stdout
                        if any(w in clean_line.lower() for w in ["warning:", "gpu memory spike", "high memory"]):
                            self.emit_event(
                                EventType.WARNING_DETECTED,
                                Severity.MEDIUM,
                                f"Warning in '{name}': {clean_line[:120]}",
                                data={"line": clean_line},
                                task_id=task_id,
                            )

                    time.sleep(0.1)

                proc.wait()
                session.exit_code = proc.returncode

                if session.exit_code == 0:
                    session.progress = 100.0
                    session.status_message = "Completed successfully"
                    self.emit_event(
                        EventType.TASK_COMPLETED,
                        Severity.INFO,
                        f"Background task '{name}' completed successfully.",
                        data={"exit_code": 0, "session_id": session_id},
                        task_id=task_id,
                    )
                    self.task_manager.complete_task(task_id, {"exit_code": 0, "logs": session.logs[-5:]})
                else:
                    stderr_out = proc.stderr.read()
                    session.error = stderr_out or f"Process exited with code {session.exit_code}"
                    session.status_message = "Failed / Crashed"
                    self.emit_event(
                        EventType.ERROR_DETECTED,
                        Severity.CRITICAL,
                        f"Background task '{name}' crashed or exited with error code {session.exit_code}!",
                        data={"exit_code": session.exit_code, "error": session.error},
                        task_id=task_id,
                    )
                    self.task_manager.fail_task(task_id, session.error)

            except Exception as e:
                session.error = str(e)
                self.emit_event(
                    EventType.ERROR_DETECTED,
                    Severity.CRITICAL,
                    f"Monitoring error in '{name}': {e}",
                    data={"error": str(e)},
                    task_id=task_id,
                )
                self.task_manager.fail_task(task_id, str(e))
            finally:
                session.is_active = False

        t = threading.Thread(target=_worker, daemon=True)
        session.thread = t
        t.start()
        return session

    def _start_pid_monitor(self, session_id: str, name: str, pid: int, task_id: str) -> MonitoredSession:
        """Watches an existing OS process by PID."""
        session = MonitoredSession(session_id, name, "pid", pid)

        def _worker():
            self.emit_event(
                EventType.MONITORING_STARTED,
                Severity.INFO,
                f"Monitoring started for process PID {pid} ('{name}').",
                data={"pid": pid, "session_id": session_id},
                task_id=task_id,
            )
            try:
                proc = psutil.Process(pid)
                warned_high_ram = False

                while session.is_active and proc.is_running():
                    try:
                        session.last_cpu = proc.cpu_percent(interval=0.5)
                        mem_info = proc.memory_info()
                        session.last_ram = mem_info.rss / (1024 * 1024)  # MB

                        if session.last_ram > 2048 and not warned_high_ram:
                            warned_high_ram = True
                            self.emit_event(
                                EventType.WARNING_DETECTED,
                                Severity.HIGH,
                                f"High memory usage warning: Process '{name}' (PID {pid}) exceeded 2GB RAM ({session.last_ram:.1f} MB).",
                                data={"ram_mb": session.last_ram},
                                task_id=task_id,
                            )
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        break

                    time.sleep(1.0)

                # Process ended
                session.status_message = "Process exited"
                self.emit_event(
                    EventType.TASK_COMPLETED,
                    Severity.INFO,
                    f"Monitored process '{name}' (PID {pid}) has terminated.",
                    data={"pid": pid, "session_id": session_id},
                    task_id=task_id,
                )
                self.task_manager.complete_task(task_id, {"pid": pid, "status": "terminated"})

            except psutil.NoSuchProcess:
                err_msg = f"Process PID {pid} not found."
                session.error = err_msg
                self.emit_event(
                    EventType.ERROR_DETECTED,
                    Severity.HIGH,
                    err_msg,
                    task_id=task_id,
                )
                self.task_manager.fail_task(task_id, err_msg)
            finally:
                session.is_active = False

        t = threading.Thread(target=_worker, daemon=True)
        session.thread = t
        t.start()
        return session

    def _start_logfile_monitor(self, session_id: str, name: str, filepath: str, task_id: str) -> MonitoredSession:
        """Tails a log file for runtime errors or warnings."""
        session = MonitoredSession(session_id, name, "logfile", filepath)

        def _worker():
            self.emit_event(
                EventType.MONITORING_STARTED,
                Severity.INFO,
                f"Watching log file '{os.path.basename(filepath)}' for errors.",
                data={"file": filepath},
                task_id=task_id,
            )
            try:
                if not os.path.exists(filepath):
                    time.sleep(1.0)

                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    # Move to end
                    f.seek(0, os.SEEK_END)
                    while session.is_active:
                        line = f.readline()
                        if line:
                            clean = line.strip()
                            if "error" in clean.lower() or "exception" in clean.lower():
                                self.emit_event(
                                    EventType.ERROR_DETECTED,
                                    Severity.HIGH,
                                    f"Error detected in log '{name}': {clean[:140]}",
                                    data={"log_line": clean},
                                    task_id=task_id,
                                )
                        else:
                            time.sleep(0.5)
            except Exception as e:
                session.error = str(e)
            finally:
                session.is_active = False

        t = threading.Thread(target=_worker, daemon=True)
        session.thread = t
        t.start()
        return session

    def _start_system_monitor(self, session_id: str, name: str, task_id: str) -> MonitoredSession:
        """Watches overall system background health and reports anomalies."""
        session = MonitoredSession(session_id, name, "system", None)

        def _worker():
            self.emit_event(
                EventType.MONITORING_STARTED,
                Severity.INFO,
                f"General system background monitoring is active for '{name}'.",
                task_id=task_id,
            )
            ticks = 0
            while session.is_active and ticks < 60:  # Watch for up to 60 intervals
                cpu = psutil.cpu_percent(interval=1.0)
                ram = psutil.virtual_memory().percent
                session.last_cpu = cpu
                session.last_ram = ram

                if cpu > 92.0:
                    self.emit_event(
                        EventType.WARNING_DETECTED,
                        Severity.MEDIUM,
                        f"System alert: High CPU utilization detected ({cpu:.1f}%).",
                        data={"cpu": cpu},
                        task_id=task_id,
                    )

                ticks += 1
                time.sleep(1.0)

            session.is_active = False
            self.emit_event(
                EventType.TASK_COMPLETED,
                Severity.INFO,
                f"Background monitoring session for '{name}' finished cleanly.",
                task_id=task_id,
            )
            self.task_manager.complete_task(task_id, {"status": "completed"})

        t = threading.Thread(target=_worker, daemon=True)
        session.thread = t
        t.start()
        return session

    def stop_session(self, session_id: Optional[str] = None) -> bool:
        """Stops a specific monitoring session, or all sessions if None."""
        with self._lock:
            if session_id:
                sess = self._sessions.get(session_id)
                if sess:
                    sess.is_active = False
                    sess.status_message = "Stopped by user"
                    return True
                return False
            else:
                for s in self._sessions.values():
                    s.is_active = False
                    s.status_message = "Stopped by user"
                return True

    def get_all_sessions_status(self) -> List[Dict[str, Any]]:
        with self._lock:
            res = []
            for sid, s in self._sessions.items():
                res.append({
                    "session_id": sid,
                    "name": s.name,
                    "type": s.target_type,
                    "active": s.is_active,
                    "progress": s.progress,
                    "status": s.status_message,
                    "last_cpu": s.last_cpu,
                    "last_ram": s.last_ram,
                })
            return res
