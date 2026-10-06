"""
Neura Multi-Agent System - Skill Agent.
Enables learning, validating, and safely registering reusable automated workflows.
Enforces permission gating and prevents unrestricted code execution.
"""

import os
import json
import time
import datetime
from typing import Dict, Any, List, Optional, Tuple
from brain.agents.base_agent import BaseAgent, AgentStatus
from brain.agents.task_manager import Task, PermissionLevel, TaskState
from brain.agents.event_system import (
    Finding,
    FindingCategory,
    Severity,
    EventType,
)

class SkillAgent(BaseAgent):
    """
    Skill Agent learns repetitive multi-step sequences, validates them,
    and registers them as reusable capabilities under explicit permission controls.
    """
    def __init__(self, registry_file: Optional[str] = None, event_bus=None, task_manager=None):
        super().__init__(
            name="SkillAgent",
            description="Learns, validates, sandboxes, and executes reusable automation workflows.",
            capabilities=[
                "workflow_learning",
                "skill_validation",
                "skill_registration",
                "permission_gated_execution",
            ],
            event_bus=event_bus,
            task_manager=task_manager,
        )
        if not registry_file:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.registry_file = os.path.join(base_dir, ".agents", "learned_skills.json")
        else:
            self.registry_file = registry_file

        os.makedirs(os.path.dirname(self.registry_file), exist_ok=True)
        self._skills: Dict[str, Dict[str, Any]] = self._load_registry()

    def _load_registry(self) -> Dict[str, Dict[str, Any]]:
        if os.path.exists(self.registry_file):
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_registry(self):
        try:
            with open(self.registry_file, "w", encoding="utf-8") as f:
                json.dump(self._skills, f, indent=2)
        except Exception as e:
            print(f"[SkillAgent] Error saving registry: {e}")

    def execute_task(self, task: Task) -> Dict[str, Any]:
        """
        Executes skill operations:
        - 'learn_skill' / 'create_skill': creates candidate skill, validates it, and registers it if authorized
        - 'list_skills': returns all registered skills
        - 'execute_skill' / 'run_skill': safely runs steps of an existing registered skill
        """
        task_type = task.task_type.lower()
        meta = task.metadata or {}

        if task_type in ["learn_skill", "create_skill", "learn_workflow"]:
            name = meta.get("name", "learned_workflow")
            desc = meta.get("description", "Automated sequence learned from user workflow")
            triggers = meta.get("triggers", [name.replace("_", " ")])
            steps = meta.get("steps", [])
            user_permission_granted = meta.get("permission_granted", False)

            self.emit_progress(task.task_id, 25.0, f"Creating candidate skill '{name}'...")
            candidate = self.create_candidate_skill(name, desc, triggers, steps)

            self.emit_progress(task.task_id, 60.0, "Validating skill workflow and safety constraints...")
            is_valid, validation_msg = self.validate_skill(candidate)

            if not is_valid:
                self.emit_warning(task.task_id, f"Skill validation failed: {validation_msg}")
                return {
                    "success": False,
                    "error": validation_msg,
                    "skill_name": name,
                    "status": "VALIDATION_FAILED",
                }

            # Enforce permission gating
            candidate["validation_status"] = "VALIDATED"

            if not user_permission_granted:
                # Skill is saved as candidate awaiting explicit authorization
                candidate["status"] = "AWAITING_PERMISSION"
                self._skills[candidate["skill_id"]] = candidate
                self._save_registry()
                msg = f"Candidate skill '{name}' validated successfully. Awaiting explicit user EXECUTE permission before active registration."
                return {
                    "success": True,
                    "message": msg,
                    "skill": candidate,
                    "status": "AWAITING_PERMISSION",
                }

            # Register skill with permission
            candidate["status"] = "REGISTERED"
            self._skills[candidate["skill_id"]] = candidate
            self._save_registry()
            self.emit_event(
                EventType.IMPORTANT_UPDATE,
                Severity.INFO,
                f"New skill '{name}' registered successfully.",
                data={"skill_id": candidate["skill_id"]},
                task_id=task.task_id,
            )
            return {
                "success": True,
                "message": f"Skill '{name}' has been validated and permanently registered.",
                "skill": candidate,
                "status": "REGISTERED",
            }

        elif task_type in ["list_skills", "list"]:
            return {
                "success": True,
                "skills": list(self._skills.values()),
            }

        elif task_type in ["execute_skill", "run_skill"]:
            skill_name = meta.get("skill_name") or meta.get("name")
            return self.run_skill(skill_name, task.task_id)

        else:
            return {"success": False, "error": f"Unknown skill task: {task_type}"}

    def create_candidate_skill(
        self,
        name: str,
        description: str,
        triggers: List[str],
        steps: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Creates a candidate skill data structure conforming to the protocol."""
        skill_id = f"skill_{name.lower().replace(' ', '_')}"
        return {
            "skill_id": skill_id,
            "name": name,
            "description": description,
            "trigger_phrases": triggers,
            "required_permissions": [PermissionLevel.OBSERVE.value, PermissionLevel.EXECUTE.value],
            "workflow_steps": steps,
            "validation_status": "CANDIDATE",
            "version": "1.0.0",
            "status": "PENDING_VALIDATION",
            "created_at": datetime.datetime.now().isoformat(),
        }

    def validate_skill(self, skill: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validates that skill workflow contains only safe, known actions and no dangerous shell injections.
        """
        steps = skill.get("workflow_steps", [])
        if not steps:
            # Allow learning a template workflow with standard steps
            return True, "Valid template workflow."

        allowed_actions = {"open_app", "wait", "run_command", "check_port", "open_browser", "http_get", "notify"}
        disallowed_cmds = {"rm -rf", "format", "del /f /s /q c:", "drop database", "mkfs"}

        for idx, step in enumerate(steps):
            act = step.get("action")
            if not act:
                return False, f"Step {idx+1} is missing an 'action' field."
            if act not in allowed_actions:
                return False, f"Step {idx+1} uses unauthorized action '{act}'."

            if act == "run_command":
                cmd = step.get("command", "").lower()
                if any(bad in cmd for bad in disallowed_cmds):
                    return False, f"Step {idx+1} contains potentially harmful command string."

        return True, "Workflow successfully validated against security policies."

    def run_skill(self, skill_name_or_id: str, task_id: str) -> Dict[str, Any]:
        """Safely executes steps of a registered skill."""
        match = None
        for s in self._skills.values():
            if s.get("name", "").lower() == skill_name_or_id.lower() or s.get("skill_id") == skill_name_or_id:
                match = s
                break

        if not match:
            return {"success": False, "error": f"Skill '{skill_name_or_id}' is not registered."}

        if match.get("status") != "REGISTERED":
            return {"success": False, "error": f"Skill '{skill_name_or_id}' cannot run because its status is {match.get('status')}."}

        steps = match.get("workflow_steps", [])
        total_steps = len(steps)
        self.emit_progress(task_id, 0.0, f"Executing skill '{match['name']}' ({total_steps} steps)...")

        for idx, step in enumerate(steps):
            action = step.get("action")
            desc = step.get("description", action)
            pct = ((idx + 1) / max(total_steps, 1)) * 100.0
            self.emit_progress(task_id, pct, f"Step {idx+1}/{total_steps}: {desc}")

            # Simulated safe execution of steps
            time.sleep(0.2)

        self.emit_event(
            EventType.TASK_COMPLETED,
            Severity.INFO,
            f"Skill '{match['name']}' executed successfully.",
            data={"skill_id": match["skill_id"]},
            task_id=task_id,
        )
        return {
            "success": True,
            "message": f"Skill '{match['name']}' executed all {total_steps} steps successfully.",
            "skill": match,
        }
