import os
import json
import re
import datetime
from typing import Dict, Any, List, Optional, Callable

DEFAULT_USER_MEMORY_PATH = os.path.join(os.path.dirname(__file__), "user_memory.json")
DEFAULT_CONV_MEMORY_PATH = os.path.join(os.path.dirname(__file__), "conversation_memory.json")
LEGACY_MEMORY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "neura_memory.json")

MAX_RECENT_MESSAGES = 8

class MemoryManager:
    """
    Manages Neura's 3-Tier Memory Architecture:
    - User Memory (Dynamic, persistent facts & preferences)
    - Conversation Memory (Temporary, sliding window with rolling summary)
    - Automatic learning from user interactions
    """
    def __init__(self, 
                 user_memory_path: str = DEFAULT_USER_MEMORY_PATH, 
                 conv_memory_path: str = DEFAULT_CONV_MEMORY_PATH,
                 legacy_memory_path: str = LEGACY_MEMORY_PATH):
        self.user_memory_path = user_memory_path
        self.conv_memory_path = conv_memory_path
        self.legacy_memory_path = legacy_memory_path

        self.user_memory: Dict[str, Any] = {
            "preferences": {
                "response_style": "concise",
                "weather_city": "",
                "song_preferences": []
            },
            "user_facts": {
                "name": "",
                "projects": [],
                "likes": [],
                "dislikes": []
            },
            "activity_log": []
        }

        self.conv_memory: Dict[str, Any] = {
            "summary": "",
            "recent_messages": []
        }

        self.load_all()

    def load_all(self):
        """Loads both user memory and conversation memory, migrating legacy data if present."""
        # 1. User Memory
        if os.path.exists(self.user_memory_path):
            try:
                with open(self.user_memory_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.user_memory["preferences"].update(data.get("preferences", {}))
                    self.user_memory["user_facts"].update(data.get("user_facts", {}))
                    self.user_memory["activity_log"] = data.get("activity_log", [])
            except Exception as e:
                print(f"[MemoryManager] Warning loading user memory: {e}")
        elif os.path.exists(self.legacy_memory_path):
            self._migrate_legacy_memory()
        else:
            self.save_user_memory()

        # 2. Conversation Memory
        if os.path.exists(self.conv_memory_path):
            try:
                with open(self.conv_memory_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.conv_memory["summary"] = data.get("summary", "")
                    self.conv_memory["recent_messages"] = data.get("recent_messages", [])
            except Exception as e:
                print(f"[MemoryManager] Warning loading conversation memory: {e}")
        else:
            self.save_conv_memory()

    def _migrate_legacy_memory(self):
        """Migrate legacy neura_memory.json to the new structure."""
        try:
            with open(self.legacy_memory_path, "r", encoding="utf-8") as f:
                old = json.load(f)
            old_prefs = old.get("preferences", {})
            self.user_memory["preferences"].update(old_prefs)
            self.user_memory["activity_log"] = old.get("activity_log", [])[-50:]
            self.save_user_memory()
            print("[MemoryManager] Successfully migrated legacy memory to user_memory.json.")
        except Exception as e:
            print(f"[MemoryManager] Legacy migration note: {e}")

    def save_user_memory(self):
        """Persist user memory to user_memory.json."""
        try:
            os.makedirs(os.path.dirname(self.user_memory_path), exist_ok=True)
            with open(self.user_memory_path, "w", encoding="utf-8") as f:
                json.dump(self.user_memory, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[MemoryManager] Error saving user memory: {e}")

    def save_conv_memory(self):
        """Persist conversation memory to conversation_memory.json."""
        try:
            os.makedirs(os.path.dirname(self.conv_memory_path), exist_ok=True)
            with open(self.conv_memory_path, "w", encoding="utf-8") as f:
                json.dump(self.conv_memory, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[MemoryManager] Error saving conversation memory: {e}")

    # ------------------ USER MEMORY OPERATIONS ------------------

    def get_preference(self, key: str, default: Any = None) -> Any:
        return self.user_memory["preferences"].get(key, default)

    def set_preference(self, key: str, value: Any):
        prev = self.user_memory["preferences"].get(key)
        if prev != value:
            self.user_memory["preferences"][key] = value
            self.save_user_memory()
            print(f"\nPreference detected:\n{key} = {value}\n")

    def add_fact(self, category: str, value: str):
        if category not in self.user_memory["user_facts"]:
            self.user_memory["user_facts"][category] = []
        target = self.user_memory["user_facts"][category]
        if isinstance(target, list):
            if value not in target:
                target.append(value)
                self.save_user_memory()
                print(f"\nFact learned:\n{category} += {value}\n")
        else:
            self.user_memory["user_facts"][category] = value
            self.save_user_memory()
            print(f"\nFact learned:\n{category} = {value}\n")

    def log_activity(self, action: str):
        self.user_memory["activity_log"].append({
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action
        })
        # Keep log size reasonable
        if len(self.user_memory["activity_log"]) > 100:
            self.user_memory["activity_log"] = self.user_memory["activity_log"][-100:]
        self.save_user_memory()

    def get_user_profile_prompt(self) -> str:
        """Formats the active user memory into a prompt section for LLM context."""
        prefs = self.user_memory.get("preferences", {})
        facts = self.user_memory.get("user_facts", {})
        
        lines = ["### User Memory & Preferences:"]
        
        # Style preferences
        style = prefs.get("response_style", "concise")
        lines.append(f"- Preferred Response Style: {style}")
        
        if prefs.get("weather_city"):
            lines.append(f"- Preferred Weather City: {prefs['weather_city']}")
        
        songs = prefs.get("song_preferences", [])
        if songs:
            lines.append(f"- Music/Song Preferences: {', '.join(songs) if isinstance(songs, list) else songs}")
            
        for k, v in prefs.items():
            if k not in ["response_style", "weather_city", "song_preferences"]:
                lines.append(f"- {k}: {v}")

        # Personal facts
        for cat, val in facts.items():
            if val:
                if isinstance(val, list):
                    lines.append(f"- Known {cat.replace('_', ' ').capitalize()}: {', '.join(str(x) for x in val)}")
                else:
                    lines.append(f"- Known {cat.replace('_', ' ').capitalize()}: {val}")

        return "\n".join(lines)

    def answer_from_memory(self, query: str) -> Optional[str]:
        """
        Attempts to answer user questions directly from stored memory facts
        and preferences without needing an external LLM API call.
        """
        q = query.strip().lower()
        facts = self.user_memory.get("user_facts", {})
        prefs = self.user_memory.get("preferences", {})
        user_name = facts.get("name") or "Sir"

        # 1. User name questions
        if any(p in q for p in ["what is my name", "who am i", "do you know my name", "tell me my name", "what's my name"]):
            if facts.get("name"):
                return f"Your name is {facts['name']}."
            return "I don't have your name recorded yet, Sir. You can say 'My name is ...' to let me know."

        # 2. Profession / Job questions
        if any(p in q for p in ["what is my profession", "what do i do", "what is my job", "my profession", "what is my work"]):
            if facts.get("profession"):
                return f"You are a {facts['profession']}, {user_name}."
            return "I don't have your profession recorded yet, Sir."

        # 3. Last song questions
        if any(p in q for p in ["last song", "last played song", "what song did i play", "what was the last song", "what did i listen to"]):
            last_song = prefs.get("last_played_song")
            if last_song:
                return f"The last song you played was '{last_song}'."
            return "You haven't played any songs recently, Sir."

        # 4. Music preferences
        if any(p in q for p in ["my music", "what music do i like", "my song preference", "favorite song", "favorite music", "what songs do i like"]):
            songs = prefs.get("song_preferences", [])
            if songs:
                song_list = ", ".join(songs) if isinstance(songs, list) else songs
                return f"Your stored music preferences are: {song_list}."
            last_song = prefs.get("last_played_song")
            if last_song:
                return f"You recently listened to '{last_song}'."
            return "I don't have specific music preferences saved for you yet, Sir."

        # 5. Project questions
        if any(p in q for p in ["what is my project", "what project am i working on", "my projects", "my project"]):
            projects = facts.get("projects", [])
            if projects:
                proj_list = ", ".join(projects) if isinstance(projects, list) else projects
                return f"You are working on: {proj_list}."
            return "I don't have any projects recorded for you yet, Sir."

        # 6. Response style / directives
        if any(p in q for p in ["what is your response style", "my response style", "how do you respond"]):
            style = prefs.get("response_style", "concise")
            return f"My active response style is set to {style}."

        # 7. Preferred weather city
        if any(p in q for p in ["what is my city", "where do i live", "my weather city", "my location"]):
            city = prefs.get("weather_city")
            if city:
                return f"Your preferred city is {city}."
            return "I don't have your default city saved yet, Sir."

        # 8. Full memory / profile overview
        if any(p in q for p in ["what do you know about me", "show my memory", "what are my preferences", "tell me what you remember"]):
            summary = []
            if facts.get("name"):
                summary.append(f"Name: {facts['name']}")
            if facts.get("profession"):
                summary.append(f"Profession: {facts['profession']}")
            if facts.get("projects"):
                summary.append(f"Projects: {', '.join(facts['projects'])}")
            if prefs.get("response_style"):
                summary.append(f"Response style: {prefs['response_style']}")
            if prefs.get("song_preferences"):
                summary.append(f"Music preferences: {', '.join(prefs['song_preferences'])}")
            if prefs.get("last_played_song"):
                summary.append(f"Last played song: {prefs['last_played_song']}")
            
            if summary:
                return "Here is what I remember about you, Sir: " + "; ".join(summary) + "."
            return "I don't have much personal information stored yet, Sir."

        return None

    # -------------- CONVERSATION MEMORY OPERATIONS --------------

    def append_turn(self, user_text: str, assistant_reply: str, summarizer: Optional[Callable[[str], str]] = None):
        """
        Appends user and assistant messages to temporary conversation memory.
        Trims older messages when exceeding MAX_RECENT_MESSAGES and rolls them into summary.
        """
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.conv_memory["recent_messages"].append({"role": "user", "content": user_text, "timestamp": now})
        self.conv_memory["recent_messages"].append({"role": "assistant", "content": assistant_reply, "timestamp": now})

        # Check sliding window
        if len(self.conv_memory["recent_messages"]) > MAX_RECENT_MESSAGES:
            overflow_count = len(self.conv_memory["recent_messages"]) - MAX_RECENT_MESSAGES
            overflow_messages = self.conv_memory["recent_messages"][:overflow_count]
            self.conv_memory["recent_messages"] = self.conv_memory["recent_messages"][overflow_count:]
            
            # Summarize overflow messages
            self._update_rolling_summary(overflow_messages, summarizer)

        self.save_conv_memory()

    def _update_rolling_summary(self, overflow_messages: List[Dict[str, str]], summarizer: Optional[Callable[[str], str]]):
        """Rolls evicted messages into the ongoing conversation summary."""
        chunk_lines = [f"{m['role'].capitalize()}: {m['content']}" for m in overflow_messages]
        chunk_text = "\n".join(chunk_lines)

        if summarizer:
            try:
                existing_summary = self.conv_memory.get("summary", "")
                prompt = (
                    f"Existing summary of previous conversation:\n{existing_summary}\n\n"
                    f"New conversation segment to incorporate:\n{chunk_text}\n\n"
                    "Provide a very concise, 2-3 sentence updated summary of what has been discussed."
                )
                new_summary = summarizer(prompt)
                if new_summary and not "error" in new_summary.lower():
                    self.conv_memory["summary"] = new_summary.strip()
                    return
            except Exception as e:
                print(f"[MemoryManager] Summary generation error: {e}")

        # Fallback manual summary compression
        prev_summary = self.conv_memory.get("summary", "")
        new_points = "; ".join([f"{m['role']}: {m['content'][:40]}..." for m in overflow_messages if len(m['content']) > 5])
        if prev_summary:
            combined = f"{prev_summary} | Recent points: {new_points}"
        else:
            combined = f"Prior topics: {new_points}"
        # Keep summary under 500 chars
        self.conv_memory["summary"] = combined[-500:]

    def get_conversation_context(self) -> str:
        """Returns the temporary conversation context (summary + sliding window)."""
        summary = self.conv_memory.get("summary", "").strip()
        recent = self.conv_memory.get("recent_messages", [])

        parts = []
        if summary:
            parts.append(f"### Context from Earlier in this Session (Summary):\n{summary}")

        if recent:
            parts.append("### Recent Conversation Window:")
            for msg in recent:
                role = "User" if msg["role"] == "user" else "Neura"
                parts.append(f"{role}: {msg['content']}")

        return "\n".join(parts)

    def get_recent_history_pairs(self) -> List[tuple]:
        """Returns list of (role, content) for compatibility with chat models."""
        pairs = []
        for msg in self.conv_memory.get("recent_messages", []):
            role = "user" if msg.get("role") == "user" else "bot"
            pairs.append((role, msg.get("content", "")))
        return pairs

    def clear_all(self):
        """Clears both user preferences and conversation memory."""
        self.user_memory = {
            "preferences": {
                "response_style": "concise",
                "weather_city": "",
                "song_preferences": []
            },
            "user_facts": {
                "name": "",
                "projects": [],
                "likes": [],
                "dislikes": []
            },
            "activity_log": []
        }
        self.conv_memory = {
            "summary": "",
            "recent_messages": []
        }
        self.save_user_memory()
        self.save_conv_memory()

    def clear_conversation_only(self):
        """Clears only temporary conversation memory, leaving user profile intact."""
        self.conv_memory = {
            "summary": "",
            "recent_messages": []
        }
        self.save_conv_memory()

    # ---------------- AUTOMATIC LEARNING ENGINE ----------------

    def auto_learn(self, user_text: str, llm_detector: Optional[Callable[[str], Optional[dict]]] = None) -> Optional[dict]:
        """
        Analyzes user input for preference signals and personal facts.
        Saves detected preferences and returns what was learned.
        """
        text_lower = user_text.strip().lower()
        learned = {}

        # 1. Response style detection (concise vs detailed)
        if any(p in text_lower for p in [
            "keep your responses short", "keep responses short", "short answers", 
            "short responses", "be concise", "concise answers", "don't give long answers", 
            "dont give long answers", "no long answers", "i don't like long answers", 
            "i dont like long answers", "brief answers", "be brief"
        ]):
            self.set_preference("response_style", "concise")
            learned["response_style"] = "concise"

        elif any(p in text_lower for p in [
            "give detailed answers", "detailed explanations", "explain in detail", 
            "long answers", "elaborate more", "be detailed"
        ]):
            self.set_preference("response_style", "detailed")
            learned["response_style"] = "detailed"

        # 2. Song / Music preferences
        music_match = re.search(r"i (?:like|love|prefer) (?:listening to )?([a-zA-Z0-9\s]+?) (?:music|songs|song)", user_text, re.IGNORECASE)
        if music_match:
            genre_or_song = music_match.group(1).strip()
            existing_songs = self.user_memory["preferences"].get("song_preferences", [])
            if not isinstance(existing_songs, list):
                existing_songs = [existing_songs] if existing_songs else []
            if genre_or_song not in existing_songs:
                existing_songs.append(genre_or_song)
                self.set_preference("song_preferences", existing_songs)
                learned["song_preferences"] = genre_or_song

        # Mood / Emotional state detection
        mood_match = re.search(r"\b(?:i am|i'm|feel|feeling)\s+(?:feeling\s+)?(bored|sad|tired|exhausted|stressed|unhappy|lonely|sleepy|lazy)\b", text_lower)
        if mood_match:
            detected_mood = mood_match.group(1)
            self.add_fact("current_mood", detected_mood)
            learned["mood"] = detected_mood

        # 3. Name detection
        non_name_words = {
            "neura", "fine", "good", "busy", "here", "ready", "happy", "sad",
            "feeling", "feel", "feels", "bored", "boring", "tired", "exhausted",
            "sick", "hungry", "angry", "stressed", "annoyed", "confused", "back",
            "done", "okay", "ok", "listening", "working", "trying", "going", "looking",
            "watching", "playing", "thinking", "a", "an", "the", "not", "just",
            "also", "very", "really", "so", "software", "developer", "engineer", "designer",
            "hello", "hi", "hey", "sir", "like", "love", "prefer"
        }

        name_match = re.search(r"\b(?:my name is|call me)\s+([a-zA-Z]+)", user_text, re.IGNORECASE)
        if not name_match and not learned.get("mood"):
            iam_match = re.search(r"\bi am\s+([a-zA-Z]+)\b", user_text, re.IGNORECASE)
            if iam_match:
                candidate = iam_match.group(1)
                if (candidate.lower() not in non_name_words 
                        and not candidate.lower().endswith("ing") 
                        and not candidate.lower().endswith("ed")):
                    name_match = iam_match

        if name_match and not any(w in text_lower for w in ["who", "what", "where", "how", "why"]):
            detected_name = name_match.group(1).capitalize()
            if (detected_name.lower() not in non_name_words 
                    and not detected_name.lower().endswith("ing") 
                    and not detected_name.lower().endswith("ed")):
                if self.user_memory["user_facts"].get("name") != detected_name:
                    self.add_fact("name", detected_name)
                    learned["name"] = detected_name

        # Profession / Role detection
        prof_match = re.search(r"\b(?:i am a|i work as a|is a|is)\s+([a-zA-Z\s]+(?:developer|engineer|designer|doctor|student|teacher|scientist|programmer|coder))\b", user_text, re.IGNORECASE)
        if prof_match:
            detected_prof = prof_match.group(1).strip()
            if self.user_memory["user_facts"].get("profession") != detected_prof:
                self.add_fact("profession", detected_prof)
                learned["profession"] = detected_prof

        # 4. Project detection
        proj_match = re.search(r"(?:my project is|working on|building) ([a-zA-Z0-9\s]+)", user_text, re.IGNORECASE)
        if proj_match:
            proj = proj_match.group(1).strip()
            if len(proj) > 2 and not any(w in proj.lower() for w in ["it", "this", "that", "something", "a project"]):
                self.add_fact("projects", proj)
                learned["project"] = proj

        # 5. General likes / preferences
        like_match = re.search(r"i (?:like|love|prefer) ([a-zA-Z0-9\s]+)", user_text, re.IGNORECASE)
        if like_match and not learned.get("song_preferences") and not learned.get("response_style"):
            item = like_match.group(1).strip()
            # filter common conversational phrases
            if item and not any(w in item.lower() for w in ["you", "that", "it", "this", "to know", "to ask"]):
                self.add_fact("likes", item)
                learned["likes"] = item

        # 6. Advanced LLM-assisted detection if candidate keywords exist
        if not learned and llm_detector and any(w in text_lower for w in ["prefer", "always", "never", "remember", "hate", "favorite", "favourite", "style"]):
            try:
                extra = llm_detector(user_text)
                if extra and isinstance(extra, dict):
                    for k, v in extra.items():
                        if k.startswith("pref_"):
                            pref_key = k.replace("pref_", "")
                            self.set_preference(pref_key, v)
                            learned[pref_key] = v
                        else:
                            self.add_fact(k, v)
                            learned[k] = v
            except Exception as e:
                print(f"[MemoryManager] LLM preference detector note: {e}")

        return learned if learned else None
