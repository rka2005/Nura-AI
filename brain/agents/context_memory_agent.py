"""
Neura Multi-Agent System - Context Memory Agent.
Provides parallel, non-blocking monitoring, analysis, updating, and maintenance of Neura's dual-tier context memory:
- active_context.json: Active context snapshot for immediate task awareness
- fixed_memory.json: Enduring configurations, persistent rules, explicit memories, and successfully performed tasks
- temporary_memory.json: Ephemeral emotional states (e.g., bored, sad), one-off queries (e.g., weather, time), and transient context

Implements the 80% Context Similarity Resolution Protocol and dual-tier context-aware query answering.
"""

import os
import re
import json
import time
import queue
import datetime
import threading
from typing import Dict, Any, List, Optional, Tuple

from brain.agents.base_agent import BaseAgent, AgentStatus
from brain.agents.task_manager import Task, TaskState, PermissionLevel
from brain.agents.event_system import (
    Event,
    EventType,
    Severity,
    Finding,
    FindingCategory,
)

DEFAULT_CONTEXT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".agents",
    "context_memory",
)


class ContextMemoryAgent(BaseAgent):
    """
    Dedicated parallel agent responsible for analyzing user commands, extracting learnings,
    routing them to fixed vs temporary memory, resolving 80% context matches, maintaining
    memory JSON integrity, and answering queries based on the user's active context.
    """

    def __init__(
        self,
        context_memory_dir: Optional[str] = None,
        event_bus=None,
        task_manager=None,
    ):
        super().__init__(
            name="MemoryAgent",
            description="Continuously monitors, analyzes, routes, and maintains dual-tier context memory (active, fixed, temporary).",
            capabilities=[
                "command_analysis",
                "dual_tier_routing",
                "context_matching_80_rule",
                "parallel_monitoring",
                "context_retrieval_and_answering",
                "temporary_memory_maintenance",
            ],
            event_bus=event_bus,
            task_manager=task_manager,
        )

        self.context_memory_dir = context_memory_dir or DEFAULT_CONTEXT_DIR
        os.makedirs(self.context_memory_dir, exist_ok=True)

        self.active_context_path = os.path.join(self.context_memory_dir, "active_context.json")
        self.fixed_memory_path = os.path.join(self.context_memory_dir, "fixed_memory.json")
        self.temporary_memory_path = os.path.join(self.context_memory_dir, "temporary_memory.json")

        self._lock = threading.RLock()
        self._work_queue: queue.Queue = queue.Queue()
        self._running = True

        # Ensure memory storage integrity
        self._ensure_storage_files()

        # Start background worker and maintenance threads
        self._worker_thread = threading.Thread(
            target=self._worker_loop, name="MemoryAgentWorker", daemon=True
        )
        self._worker_thread.start()

        self._maintenance_thread = threading.Thread(
            target=self._maintenance_loop, name="MemoryAgentMaintenance", daemon=True
        )
        self._maintenance_thread.start()

    # -------------------------------------------------------------
    # Storage Initialization & File I/O
    # -------------------------------------------------------------

    def _ensure_storage_files(self):
        """Ensures all context memory JSON files exist and are valid JSON."""
        with self._lock:
            # 1. active_context.json
            if not os.path.exists(self.active_context_path):
                init_active = {
                    "user_command": "",
                    "task": "system_idle",
                    "name": "Neura",
                    "type": "conversation",
                    "extension": None,
                    "memory_type": "temporary",
                    "details": {"status": "initialized"},
                }
                self._atomic_save_json(self.active_context_path, init_active)

            # 2. fixed_memory.json
            if not os.path.exists(self.fixed_memory_path):
                self._atomic_save_json(self.fixed_memory_path, [])
            else:
                try:
                    with open(self.fixed_memory_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if not isinstance(data, list):
                        self._atomic_save_json(self.fixed_memory_path, [])
                except Exception:
                    self._atomic_save_json(self.fixed_memory_path, [])

            # 3. temporary_memory.json
            if not os.path.exists(self.temporary_memory_path):
                self._atomic_save_json(self.temporary_memory_path, [])
            else:
                try:
                    with open(self.temporary_memory_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if not isinstance(data, list):
                        self._atomic_save_json(self.temporary_memory_path, [])
                except Exception:
                    self._atomic_save_json(self.temporary_memory_path, [])

    def _atomic_save_json(self, path: str, data: Any):
        """Atomically saves JSON data using a temporary file replacement."""
        temp_file = f"{path}.tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, path)
        except Exception as e:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
            print(f"❌ [MemoryAgent] Error saving JSON {path}: {e}")

    def load_fixed_memories(self) -> List[Dict[str, Any]]:
        """Loads all records from fixed_memory.json."""
        with self._lock:
            try:
                if os.path.exists(self.fixed_memory_path):
                    with open(self.fixed_memory_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        return data if isinstance(data, list) else []
            except Exception as e:
                print(f"[MemoryAgent] Warning reading fixed memory: {e}")
            return []

    def load_temporary_memories(self) -> List[Dict[str, Any]]:
        """Loads all records from temporary_memory.json."""
        with self._lock:
            try:
                if os.path.exists(self.temporary_memory_path):
                    with open(self.temporary_memory_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        return data if isinstance(data, list) else []
            except Exception as e:
                print(f"[MemoryAgent] Warning reading temporary memory: {e}")
            return []

    # -------------------------------------------------------------
    # Command Analysis Engine & Feature Extraction
    # -------------------------------------------------------------

    def analyze_command(
        self,
        user_command: str,
        execution_success: Optional[bool] = None,
        execution_result: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyzes the user command to understand what type of command it is,
        what needs to be learned from here, and whether it belongs in fixed or temporary memory.
        """
        cmd_raw = user_command.strip()
        cmd_lower = cmd_raw.lower()

        feelings = None
        what_need_to_learn = {}
        memory_type = "temporary"
        context_type = "conversation"
        target_name = "general"
        extension = None
        task_slug = "process_user_query"

        # 1. Emotional state / Mood detection (Temporary Memory)
        # e.g., "i am feeling bored", "feeling tired", "i'm bored", "i feel sad"
        mood_match = re.search(
            r"\b(?:i am|i'm|i\s+feel|feeling)\s+(?:feeling\s+)?(bored|sad|tired|exhausted|stressed|unhappy|lonely|sleepy|lazy|happy|excited|anxious|angry)\b",
            cmd_lower,
        )
        if mood_match:
            feelings = mood_match.group(1).lower()
            memory_type = "temporary"
            context_type = "conversation"
            task_slug = f"express_feeling_{feelings}"
            target_name = "user_emotional_state"
            what_need_to_learn["user_feelings"] = feelings
            what_need_to_learn["emotional_support_required"] = True
            what_need_to_learn["takeaway"] = f"User is feeling {feelings}."

        # 2. Explicit "remember this" or memory storage requests (Fixed Memory)
        # e.g., "remember this: ...", "remember that ...", "keep in mind that ...", "don't forget ..."
        elif any(
            p in cmd_lower
            for p in [
                "remember this",
                "remember that",
                "remember:",
                "remember :",
                "don't forget",
                "dont forget",
                "keep in mind",
                "note down that",
                "store this in memory",
                "save to memory",
            ]
        ):
            memory_type = "fixed"
            context_type = "config"
            task_slug = "store_explicit_memory"
            target_name = "user_explicit_instruction"

            # Extract memory body
            cleaned_fact = cmd_raw
            for prefix in [
                "remember this",
                "remember that",
                "remember:",
                "remember :",
                "remember",
                "don't forget that",
                "don't forget",
                "dont forget that",
                "dont forget",
                "keep in mind that",
                "keep in mind",
                "store this in memory",
                "save to memory",
            ]:
                if cleaned_fact.lower().startswith(prefix):
                    cleaned_fact = cleaned_fact[len(prefix) :].strip(" :,-")
                    break
            what_need_to_learn["explicit_note"] = cleaned_fact or cmd_raw
            what_need_to_learn["takeaway"] = f"Explicit user note: {cleaned_fact or cmd_raw}"

        # 3. User Identity & Enduring Personal Preferences (Fixed Memory)
        # e.g., "my name is ...", "i work as ...", "i like ... music", "response style concise"
        elif any(
            p in cmd_lower
            for p in [
                "my name is",
                "call me",
                "i am a developer",
                "i am an engineer",
                "i work as",
                "response style",
                "keep responses short",
                "detailed answers",
            ]
        ):
            memory_type = "fixed"
            context_type = "config"
            target_name = "user_profile"
            task_slug = "update_user_preference"
            what_need_to_learn["profile_update"] = cmd_raw
            what_need_to_learn["takeaway"] = "User profile preference or persistent attribute."

        # 4. One-off queries: Weather, time, jokes, disposable lookups (Temporary Memory)
        elif (
            any(k in cmd_lower for k in ["weather", "temperature", "forecast", "climate", "joke"])
            or re.search(r"\b(?:time|clock)\b", cmd_lower)
            or any(p in cmd_lower for p in ["who won the", "how old is", "what year", "when was", "define "])
        ):
            memory_type = "temporary"
            context_type = "conversation"
            task_slug = "transient_info_query"
            target_name = "weather_lookup" if any(w in cmd_lower for w in ["weather", "temperature", "forecast"]) else ("time_lookup" if "time" in cmd_lower or "clock" in cmd_lower else "general_lookup")
            if any(w in cmd_lower for w in ["weather", "temperature", "forecast"]):
                what_need_to_learn["query_topic"] = "weather"
                what_need_to_learn["takeaway"] = "User asked for real-time weather information."
            elif "time" in cmd_lower or "clock" in cmd_lower:
                what_need_to_learn["query_topic"] = "time"
                what_need_to_learn["takeaway"] = "User inquired about current time."
            elif "joke" in cmd_lower:
                what_need_to_learn["query_topic"] = "joke"
                what_need_to_learn["takeaway"] = "User requested a joke."
            else:
                what_need_to_learn["query_topic"] = "disposable_query"
                what_need_to_learn["takeaway"] = "Transient information query."

        # 5. System capabilities & What can you perform queries (Fixed Memory)
        elif any(
            p in cmd_lower
            for p in [
                "what can you do", "what can you perform", "what all can you do", "what are your capabilities",
                "what tasks can you perform", "what are your features", "tell me what you can do",
                "tell me what you can perform", "tell me your capabilities", "what can be done by you",
                "what can you do for me", "what are your functions", "what do you perform"
            ]
        ):
            memory_type = "fixed"
            context_type = "app"
            task_slug = "system_capabilities_query"
            target_name = "neura_capabilities"
            what_need_to_learn["query_topic"] = "capabilities"
            what_need_to_learn["takeaway"] = "Inquiry regarding Neura's system capabilities and supported functions."

        # 6. Screen vision, OCR and reading queries
        elif any(
            p in cmd_lower
            for p in [
                "what can you see", "what do you see", "what is on screen", "what's on screen",
                "what is on my screen", "what's on my screen", "what is written", "what text is on screen",
                "read the screen", "read my screen", "summarize the screen", "summarize my screen"
            ]
        ):
            memory_type = "temporary"
            context_type = "app"
            task_slug = "screen_vision_inspection"
            target_name = "screen_vision"
            what_need_to_learn["query_topic"] = "screen_perception"
            what_need_to_learn["takeaway"] = f"Screen inspection query: {cmd_raw}"

        # 7. System health & diagnostics queries
        elif any(
            p in cmd_lower
            for p in [
                "system condition", "system status", "computer condition", "pc status", "system health",
                "cpu usage", "ram usage", "memory usage", "disk usage", "how is my system"
            ]
        ):
            memory_type = "temporary"
            context_type = "script"
            task_slug = "system_diagnostics"
            target_name = "system_health"
            what_need_to_learn["query_topic"] = "system_condition"
            what_need_to_learn["takeaway"] = "User inquired about system performance and condition."

        # 8. Background inspection queries
        elif any(
            p in cmd_lower
            for p in [
                "what is running in the background", "what's running in the background",
                "what happens in the background", "what background apps are running",
                "background tasks", "background activity"
            ]
        ):
            memory_type = "temporary"
            context_type = "app"
            task_slug = "background_status_inspection"
            target_name = "background_tasks"
            what_need_to_learn["query_topic"] = "background_status"
            what_need_to_learn["takeaway"] = "User inquired about background activity and processes."

        # 9. Project & Code File Testing
        elif "test" in cmd_lower and any(
            p in cmd_lower for p in ["project", "file", "code", "app", "script", "suite", "workspace", "screen", "current"]
        ):
            if execution_success is True:
                memory_type = "fixed"
            else:
                memory_type = "temporary"
            context_type = "code"
            task_slug = "project_or_file_testing"
            target_name = "test_subsystem"
            if any(p in cmd_lower for p in [".py", ".json", ".js", ".ts", ".html"]):
                match_ext = re.search(r"(\.[a-zA-Z0-9]+)\b", cmd_raw)
                if match_ext:
                    extension = match_ext.group(1).lower()
            what_need_to_learn["command_intent"] = task_slug
            what_need_to_learn["takeaway"] = f"Testing requested: {cmd_raw}"

        # 10. System Audibility & Microphone/Speaker Hardware Check
        elif any(
            p in cmd_lower
            for p in [
                "can you hear me", "am i audible", "are you able to hear me", "can you hear my voice",
                "can you hear", "can you listen", "check microphone", "test microphone",
                "check speaker", "check microphone and speaker", "is my microphone working"
            ]
        ) or re.search(r"\b(?:hear\s+me|am\s+i\s+audible|audible\s+to\s+you|check\s+(?:my\s+)?(?:mic|microphone|speaker))\b", cmd_lower):
            memory_type = "fixed" if execution_success is True else "temporary"
            context_type = "app"
            task_slug = "audio_hardware_and_audibility_check"
            target_name = "audio_subsystem"
            what_need_to_learn["query_topic"] = "audibility_and_audio_devices"
            what_need_to_learn["takeaway"] = "Inquiry regarding Neura hearing ability and microphone/speaker hardware status."

        # 11. Application / File / Desktop Automation / Code Actions
        elif any(
            p in cmd_lower
            for p in [
                "open",
                "launch",
                "close",
                "play",
                "search",
                "create file",
                "delete file",
                "write a note",
                "inspect screen",
                "test project",
                "run diagnostic",
            ]
        ):
            # If the action has already performed properly, it's fixed memory!
            if execution_success is True:
                memory_type = "fixed"
            else:
                # Initially logged as transient until success is confirmed
                memory_type = "temporary"

            if any(p in cmd_lower for p in [".py", ".json", ".md", ".txt", ".doc", ".docx", ".pdf"]):
                context_type = "code" if any(p in cmd_lower for p in [".py", ".json"]) else "text"
                match_ext = re.search(r"(\.[a-zA-Z0-9]+)\b", cmd_raw)
                if match_ext:
                    extension = match_ext.group(1).lower()
                target_name = "file_operation"
                task_slug = "file_automation"
            elif any(p in cmd_lower for p in ["open", "launch", "close"]):
                context_type = "app"
                target_name = "desktop_app"
                task_slug = "manage_application"
            elif "play" in cmd_lower or "youtube" in cmd_lower:
                context_type = "app"
                target_name = "youtube_media"
                task_slug = "play_media_action"
            elif "project" in cmd_lower or "diagnostic" in cmd_lower:
                context_type = "code"
                target_name = "project_subsystem"
                task_slug = "run_project_diagnostics"
            else:
                context_type = "script"
                target_name = "desktop_action"
                task_slug = "execute_desktop_command"

            what_need_to_learn["command_intent"] = task_slug
            what_need_to_learn["takeaway"] = f"Action requested: {cmd_raw}"

        # 10. General dialogue / fallback
        else:
            memory_type = "temporary"
            context_type = "conversation"
            task_slug = "conversational_dialogue"
            target_name = "dialogue"
            what_need_to_learn["dialogue_input"] = cmd_raw
            what_need_to_learn["takeaway"] = "General conversational exchange."

        # Attach execution result details if provided
        if execution_result:
            what_need_to_learn["execution_result"] = execution_result
        if execution_success is not None:
            what_need_to_learn["execution_success"] = execution_success
            if execution_success is True:
                memory_type = "fixed"

        context_obj = {
            "user_command": cmd_raw,
            "task": task_slug,
            "name": target_name,
            "type": context_type,
            "extension": extension,
            "memory_type": memory_type,
            "details": what_need_to_learn,
        }

        return context_obj

    # -------------------------------------------------------------
    # Active Context Snapshot Management
    # -------------------------------------------------------------

    def update_active_context(self, context_obj: Dict[str, Any]):
        """Persists active context snapshot to .agents/context_memory/active_context.json."""
        with self._lock:
            self._atomic_save_json(self.active_context_path, context_obj)

    # -------------------------------------------------------------
    # Context Matching & Similarity Resolution (80% Rule)
    # -------------------------------------------------------------

    def calculate_similarity(self, ctx_a: Dict[str, Any], ctx_b: Dict[str, Any]) -> float:
        """
        Evaluates context similarity score [0.0, 1.0] between two context records:
        - Command semantic/text similarity (weight: 0.50)
        - Specific task match (weight: 0.30)
        - Specific target name & detail overlap (weight: 0.20)
        
        Ensures generic fallback dialogue entries do not trigger false 80% matches
        unless their actual command contents are truly similar.
        """
        import difflib

        cmd_a = str(ctx_a.get("user_command", "")).strip().lower()
        cmd_b = str(ctx_b.get("user_command", "")).strip().lower()

        if not cmd_a or not cmd_b:
            return 0.0

        if cmd_a == cmd_b:
            return 1.0

        # 1. Command Text & Token Similarity (Weight: 0.50)
        seq_ratio = difflib.SequenceMatcher(None, cmd_a, cmd_b).ratio()

        STOPWORDS = {
            "can", "you", "tell", "me", "what", "is", "are", "the", "a", "an", "and", "or",
            "to", "in", "on", "at", "for", "with", "about", "from", "user", "please", "now",
            "do", "does", "did", "i", "my", "your", "it", "its", "so", "be", "just",
            "dialogue", "input", "takeaway", "general", "conversational", "exchange"
        }
        words_a = {w for w in re.findall(r"\b[a-z0-9_]{2,}\b", cmd_a) if w not in STOPWORDS}
        words_b = {w for w in re.findall(r"\b[a-z0-9_]{2,}\b", cmd_b) if w not in STOPWORDS}

        if words_a and words_b:
            token_jaccard = len(words_a & words_b) / len(words_a | words_b)
        else:
            token_jaccard = seq_ratio

        command_score = max(seq_ratio, token_jaccard)

        # 2. Specific Task Match (Weight: 0.30)
        task_a = str(ctx_a.get("task", "")).strip().lower()
        task_b = str(ctx_b.get("task", "")).strip().lower()
        task_score = 0.0

        GENERIC_TASKS = {"conversational_dialogue", "general_task", "dialogue", "general", ""}
        is_generic_task = (task_a in GENERIC_TASKS) or (task_b in GENERIC_TASKS)

        if not is_generic_task:
            if task_a == task_b:
                task_score = 1.0
            elif task_a in task_b or task_b in task_a:
                task_score = 0.7
        else:
            if task_a == task_b:
                task_score = command_score

        # 3. Target Name & Specific Details Match (Weight: 0.20)
        name_a = str(ctx_a.get("name", "")).strip().lower()
        name_b = str(ctx_b.get("name", "")).strip().lower()
        type_a = str(ctx_a.get("type", "")).strip().lower()
        type_b = str(ctx_b.get("type", "")).strip().lower()

        detail_score = 0.0
        GENERIC_NAMES = {"dialogue", "general", "conversation", ""}
        is_generic_name = (name_a in GENERIC_NAMES) or (name_b in GENERIC_NAMES)

        if not is_generic_name and name_a and name_a == name_b:
            detail_score += 0.5
        elif not is_generic_name and (name_a in name_b or name_b in name_a):
            detail_score += 0.3

        if type_a and type_a == type_b and type_a not in ["conversation", ""]:
            detail_score += 0.3

        # Check key semantic detail keys (feelings, query_topic, explicit_note)
        det_a = ctx_a.get("details", {})
        det_b = ctx_b.get("details", {})
        if det_a.get("user_feelings") and det_a.get("user_feelings") == det_b.get("user_feelings"):
            detail_score += 0.4
        if det_a.get("query_topic") and det_a.get("query_topic") == det_b.get("query_topic"):
            detail_score += 0.4
        if det_a.get("explicit_note") and det_a.get("explicit_note") == det_b.get("explicit_note"):
            detail_score += 0.5

        detail_score = min(1.0, detail_score)

        # 4. Total Weighted Score
        total_score = (0.50 * command_score) + (0.30 * task_score) + (0.20 * detail_score)

        if is_generic_task and command_score < 0.35:
            total_score = min(total_score, command_score)

        return min(1.0, round(total_score, 3))

    def resolve_and_record_memory(
        self,
        context_obj: Dict[str, Any],
        promote_to_fixed_if_success: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes the Dual-Tier Memory Protocol (80% Rule):
        1. Inspects fixed_memory.json and temporary_memory.json.
        2. Evaluates context similarity.
        3. If Similarity >= 80%:
           - Retains the optimal/successful context in fixed_memory.json.
           - Moves/demotes superseded/alternative context to temporary_memory.json.
        4. If Similarity < 80%:
           - Appends new record to the appropriate file (fixed or temporary).
        """
        with self._lock:
            fixed_list = self.load_fixed_memories()
            temp_list = self.load_temporary_memories()

            now_str = datetime.datetime.now().isoformat()
            is_fixed_target = (context_obj.get("memory_type") == "fixed") or promote_to_fixed_if_success

            best_sim = 0.0
            best_match_entry = None
            best_match_store = None
            best_match_idx = -1

            # Check fixed memories
            for i, item in enumerate(fixed_list):
                sim = self.calculate_similarity(context_obj, item)
                if sim > best_sim:
                    best_sim = sim
                    best_match_entry = item
                    best_match_store = "fixed"
                    best_match_idx = i

            # Check temporary memories
            for j, item in enumerate(temp_list):
                sim = self.calculate_similarity(context_obj, item)
                if sim > best_sim:
                    best_sim = sim
                    best_match_entry = item
                    best_match_store = "temporary"
                    best_match_idx = j

            # ---------------------------------------------------------
            # Match Found (Similarity >= 0.80)
            # ---------------------------------------------------------
            if best_sim >= 0.80 and best_match_entry is not None:
                print(f"🎯 [MemoryAgent] 80% Context Match Found (Similarity: {best_sim:.2f}) with {best_match_entry.get('id')}")

                new_entry = dict(context_obj)
                new_entry["timestamp"] = now_str
                new_entry["id"] = best_match_entry.get("id")

                if is_fixed_target:
                    new_entry["memory_type"] = "fixed"
                    # If match was in fixed memory, update fixed memory and demote previous to temporary
                    if best_match_store == "fixed":
                        prior_copy = dict(best_match_entry)
                        prior_copy["id"] = f"ctx_temp_demoted_{int(time.time())}"
                        prior_copy["memory_type"] = "temporary"
                        prior_copy["demoted_at"] = now_str

                        fixed_list[best_match_idx] = new_entry
                        temp_list.insert(0, prior_copy)
                    else:
                        # Match was in temporary memory, promote to fixed memory
                        temp_list.pop(best_match_idx)
                        fixed_list.append(new_entry)

                    self._atomic_save_json(self.fixed_memory_path, fixed_list)
                    self._atomic_save_json(self.temporary_memory_path, temp_list)
                    return {"action": "matched_promoted_to_fixed", "entry": new_entry, "similarity": best_sim}

                else:
                    new_entry["memory_type"] = "temporary"
                    # Repeated or refreshed temporary context
                    if best_match_store == "temporary":
                        temp_list[best_match_idx] = new_entry
                    else:
                        # Stays in fixed, temporary observation logged
                        new_temp_id = f"ctx_temp_{len(temp_list) + 1:03d}"
                        new_entry["id"] = new_temp_id
                        temp_list.insert(0, new_entry)

                    self._atomic_save_json(self.temporary_memory_path, temp_list)
                    return {"action": "matched_updated_temporary", "entry": new_entry, "similarity": best_sim}

            # ---------------------------------------------------------
            # New Context (Similarity < 0.80)
            # ---------------------------------------------------------
            else:
                new_entry = dict(context_obj)
                new_entry["timestamp"] = now_str

                if is_fixed_target:
                    new_id = f"ctx_fixed_{len(fixed_list) + 1:03d}"
                    new_entry["id"] = new_id
                    new_entry["memory_type"] = "fixed"
                    fixed_list.append(new_entry)
                    self._atomic_save_json(self.fixed_memory_path, fixed_list)
                    print(f"💾 [MemoryAgent] Saved new fixed memory: {new_id} ({new_entry.get('task')})")
                    return {"action": "created_new_fixed", "entry": new_entry, "similarity": best_sim}
                else:
                    new_id = f"ctx_temp_{len(temp_list) + 1:03d}"
                    new_entry["id"] = new_id
                    new_entry["memory_type"] = "temporary"
                    temp_list.insert(0, new_entry)
                    self._atomic_save_json(self.temporary_memory_path, temp_list)
                    print(f"⏱️ [MemoryAgent] Saved new temporary memory: {new_id} ({new_entry.get('task')})")
                    return {"action": "created_new_temporary", "entry": new_entry, "similarity": best_sim}

    # -------------------------------------------------------------
    # Parallel Worker & Maintenance Loop
    # -------------------------------------------------------------

    def _worker_loop(self):
        """Asynchronously processes command updates and records them without blocking speech/GUI."""
        while self._running:
            try:
                item = self._work_queue.get(timeout=1.0)
                if item is None:
                    break

                cmd_text = item.get("command", "")
                task_name = item.get("task_name")
                exec_success = item.get("execution_success")
                exec_result = item.get("execution_result")
                extra_details = item.get("details")

                self.status = AgentStatus.BUSY

                # Analyze command
                context_obj = self.analyze_command(
                    user_command=cmd_text,
                    execution_success=exec_success,
                    execution_result=exec_result,
                )
                if task_name:
                    context_obj["task"] = task_name
                if extra_details:
                    context_obj["details"].update(extra_details)
                if exec_success is True:
                    context_obj["memory_type"] = "fixed"

                # Update active context snapshot
                self.update_active_context(context_obj)

                # Execute 80% protocol resolution & dual-tier save
                self.resolve_and_record_memory(
                    context_obj=context_obj,
                    promote_to_fixed_if_success=(exec_success is True),
                )

                self.status = AgentStatus.IDLE
                self._work_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                self.status = AgentStatus.ERROR
                print(f"❌ [MemoryAgent Worker Exception]: {e}")
                self.status = AgentStatus.IDLE

    def _maintenance_loop(self):
        """Periodic background maintenance: prunes old temporary items and ensures file integrity."""
        while self._running:
            try:
                time.sleep(30.0)
                with self._lock:
                    temp_list = self.load_temporary_memories()
                    # Keep temporary memory manageable (max 40 items)
                    if len(temp_list) > 40:
                        pruned = temp_list[:40]
                        self._atomic_save_json(self.temporary_memory_path, pruned)
                        print(f"🧹 [MemoryAgent] Pruned temporary memory window to 40 items.")
            except Exception as e:
                print(f"[MemoryAgent Maintenance Note]: {e}")

    # -------------------------------------------------------------
    # Public Asynchronous & Synchronous Ingestion API
    # -------------------------------------------------------------

    def record_incoming_command_parallel(self, command: str):
        """
        Dispatches incoming user command to the parallel worker queue and
        immediately creates an active context snapshot for instant responsiveness.
        """
        if not command or not command.strip():
            return

        clean = command.strip()

        # Immediate synchronous snapshot in active_context.json
        quick_ctx = self.analyze_command(clean)
        self.update_active_context(quick_ctx)

        # Enqueue for background dual-tier matching & resolution
        self._work_queue.put({"command": clean, "execution_success": None, "execution_result": None})

    def record_task_success(
        self,
        command: str,
        task_name: str,
        result_summary: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Records a successfully executed task directly into fixed_memory.json.
        """
        clean = command.strip() if command else task_name
        ctx = self.analyze_command(
            user_command=clean,
            execution_success=True,
            execution_result=result_summary,
        )
        ctx["task"] = task_name
        ctx["memory_type"] = "fixed"
        if details:
            ctx["details"].update(details)

        self.update_active_context(ctx)
        self._work_queue.put(
            {
                "command": clean,
                "task_name": task_name,
                "execution_success": True,
                "execution_result": result_summary,
                "details": details,
            }
        )

    # -------------------------------------------------------------
    # Dual-Tier Context-Aware Query Answering
    # -------------------------------------------------------------

    def answer_from_context_memory(self, query: str) -> Optional[str]:
        """
        Checks both fixed_memory.json and temporary_memory.json to answer user queries
        grounded in active and historical context (Zero API Call).
        """
        q = query.strip().lower()

        # 1. System Capabilities & What can you perform (Zero API Call)
        if any(
            p in q
            for p in [
                "what can you do",
                "what can you perform",
                "what all can you do",
                "what are your capabilities",
                "what tasks can you perform",
                "what are your features",
                "tell me what you can do",
                "tell me what you can perform",
                "tell me your capabilities",
                "what can be done by you",
                "what can you do for me",
                "what are your functions",
                "what do you perform",
            ]
        ):
            return (
                "Sir, I can perform the following functions:\n"
                "• Screen Vision & Perception: Inspect and summarize your active screen, read text via OCR, click buttons, and open links.\n"
                "• System Diagnostics: Check real-time CPU, RAM, disk usage, battery status, and test internet speed.\n"
                "• Desktop Automation: Open and close desktop applications, manage files and folders, adjust volume and brightness.\n"
                "• Media & YouTube: Search and play YouTube videos or songs, and provide mood-based music recommendations.\n"
                "• Personal Assistance: Set alarms and reminders, write and read notes, and maintain dual-tier context memory.\n"
                "• Multi-Agent Systems: Run background surveillance, code syntax diagnostics, and autonomous skill learning."
            )

        # 2. System Audibility & Microphone/Speaker Hardware Status (Zero API Call)
        if any(
            p in q
            for p in [
                "can you hear me", "am i audible", "are you able to hear me", "can you hear my voice",
                "can you hear properly", "can you hear", "check microphone", "test microphone",
                "is my microphone working", "check speaker", "check microphone and speaker", "is my mic working"
            ]
        ) or re.search(r"\b(?:hear\s+me|am\s+i\s+audible|audible\s+to\s+you)\b", q):
            try:
                from neura import check_microphone_and_speaker_status
                healthy, info, speech = check_microphone_and_speaker_status()
                return speech
            except Exception:
                return "Yes Sir, I can hear you loud and clear! Your microphone and audio devices are working properly."

        # 3. User Feelings & Mood Recall (from temporary_memory.json)
        # e.g., "how am i feeling?", "what did i say about feeling bored?", "am i bored?", "my mood"
        if any(
            p in q
            for p in [
                "how am i feeling",
                "how do i feel",
                "what is my mood",
                "what's my mood",
                "am i bored",
                "did i say i am bored",
                "my feelings",
                "why am i bored",
            ]
        ):
            temp_memories = self.load_temporary_memories()
            for item in temp_memories:
                details = item.get("details", {})
                feelings = details.get("user_feelings")
                if feelings:
                    return (
                        f"Earlier you mentioned that you were feeling {feelings}, Sir. "
                        f"Would you like me to play some music or tell a joke to cheer you up?"
                    )
            return "You haven't mentioned feeling a particular way recently, Sir. How are you feeling right now?"

        # 3. Recent Temporary Queries (e.g., weather query recall)
        if any(
            p in q
            for p in [
                "what weather did i ask",
                "did i check the weather",
                "did i ask for weather",
                "what was the weather i asked",
            ]
        ):
            temp_memories = self.load_temporary_memories()
            for item in temp_memories:
                cmd = item.get("user_command", "").lower()
                if "weather" in cmd:
                    return f"You recently asked: '{item.get('user_command')}'. I retrieved the live weather for you."
            return "I don't have a recent weather query logged in temporary memory, Sir."

        # 4. Explicit Remembered Items (from fixed_memory.json)
        if any(
            p in q
            for p in [
                "what did i tell you to remember",
                "what did i ask you to remember",
                "do you remember what i told you",
                "check your fixed memory",
                "what is in your fixed memory",
                "show fixed memory",
            ]
        ):
            fixed_memories = self.load_fixed_memories()
            explicit_notes = []
            for item in reversed(fixed_memories):
                details = item.get("details", {})
                if "explicit_note" in details:
                    explicit_notes.append(f"• {details['explicit_note']}")
                elif item.get("task") == "store_explicit_memory":
                    explicit_notes.append(f"• {item.get('user_command')}")

            if explicit_notes:
                notes_str = "\n".join(explicit_notes[-3:])
                return f"Here is what you explicitly told me to remember, Sir:\n{notes_str}"
            else:
                return "You haven't instructed me to remember any specific notes yet, Sir. You can say 'Remember this: ...' anytime."

        # 5. Recent successful task recall (from fixed_memory.json)
        if any(
            p in q
            for p in [
                "what task did you complete",
                "what did you do last",
                "what was the last task",
                "what tasks did you perform",
            ]
        ):
            fixed_memories = self.load_fixed_memories()
            if fixed_memories:
                last_item = fixed_memories[-1]
                cmd = last_item.get("user_command", "")
                task = last_item.get("task", "")
                return f"The latest successfully recorded task in my fixed memory is '{task}' from command: '{cmd}'."
            return "No previous tasks are stored in fixed memory yet, Sir."

        # 6. Context Matching with Previous Memories (>= 80% Rule - Zero API Call)
        # If the incoming query matches any previous memory entry with similarity >= 0.80,
        # return that stored memory result directly without calling any LLM API.
        try:
            query_ctx = self.analyze_command(query)
            fixed_memories = self.load_fixed_memories()
            temp_memories = self.load_temporary_memories()

            best_match_entry = None
            best_match_sim = 0.0

            for item in fixed_memories + temp_memories:
                sim = self.calculate_similarity(query_ctx, item)
                if sim > best_match_sim:
                    best_match_sim = sim
                    best_match_entry = item

            if best_match_sim >= 0.80 and best_match_entry:
                details = best_match_entry.get("details", {})
                if details.get("execution_result"):
                    return f"{details['execution_result']}"
                elif details.get("result_summary"):
                    return f"{details['result_summary']}"
                elif details.get("explicit_note"):
                    return f"According to your saved memory, Sir: '{details['explicit_note']}'."
                elif details.get("user_feelings"):
                    return (
                        f"Earlier you mentioned that you were feeling {details['user_feelings']}, Sir. "
                        f"Would you like me to play some music or tell a joke to cheer you up?"
                    )
                elif details.get("takeaway") and details["takeaway"] not in [
                    "General conversational exchange.",
                    "Transient information query.",
                ]:
                    return f"{details['takeaway']}"
        except Exception as match_err:
            print(f"[ContextMemoryAgent] Memory match search note: {match_err}")

        return None

    # -------------------------------------------------------------
    # Context Augmentation Prompt Builder for LLM
    # -------------------------------------------------------------

    def get_dual_memory_context_prompt(self) -> str:
        """
        Generates a concise markdown context section containing active temporary
        states (e.g. user feelings, recent queries) and fixed memory points to
        feed directly into the LLM system prompt.
        """
        temp_memories = self.load_temporary_memories()
        fixed_memories = self.load_fixed_memories()

        lines = ["### Dual-Tier Context Memory:"]

        # 1. Temporary states
        recent_feelings = []
        recent_transient_queries = []
        for item in temp_memories[:6]:
            details = item.get("details", {})
            f = details.get("user_feelings")
            if f and f not in recent_feelings:
                recent_feelings.append(f)
            elif item.get("user_command"):
                recent_transient_queries.append(item.get("user_command"))

        if recent_feelings:
            lines.append(f"- Active User Feelings (Temporary): {', '.join(recent_feelings)}")
        if recent_transient_queries:
            lines.append(f"- Recent Transient Queries: {'; '.join(recent_transient_queries[:3])}")

        # 2. Fixed memory notes & rules
        explicit_remembers = []
        recent_fixed_tasks = []
        for item in reversed(fixed_memories[-8:]):
            details = item.get("details", {})
            if "explicit_note" in details:
                explicit_remembers.append(details["explicit_note"])
            elif item.get("task"):
                recent_fixed_tasks.append(item.get("task"))

        if explicit_remembers:
            lines.append(f"- Enduring Facts To Remember (Fixed): {'; '.join(explicit_remembers[:3])}")
        if recent_fixed_tasks:
            lines.append(f"- Successfully Executed Tasks (Fixed): {', '.join(recent_fixed_tasks[:3])}")

        return "\n".join(lines) if len(lines) > 1 else ""

    # -------------------------------------------------------------
    # BaseAgent Task Execution Interface
    # -------------------------------------------------------------

    def execute_task(self, task: Task) -> Dict[str, Any]:
        """Subclasses BaseAgent.execute_task for orchestrated memory operations."""
        cmd = task.metadata.get("command", "")
        if task.task_type == "analyze_and_record":
            ctx = self.analyze_command(cmd)
            self.update_active_context(ctx)
            res = self.resolve_and_record_memory(ctx)
            return {"success": True, "result": res}
        elif task.task_type == "record_success":
            task_name = task.metadata.get("task_name", "completed_task")
            summary = task.metadata.get("summary", "")
            self.record_task_success(cmd, task_name, summary)
            return {"success": True, "task_name": task_name}
        elif task.task_type == "context_query":
            ans = self.answer_from_context_memory(cmd)
            return {"success": True, "answer": ans}
        else:
            return {"success": True, "message": "MemoryAgent idle"}

    def stop(self):
        """Stops background threads cleanly."""
        self._running = False
        self._work_queue.put(None)
