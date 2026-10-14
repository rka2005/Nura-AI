"""
Neura Cross-App & System Notification Listener Subsystem.
Continuously captures desktop notifications from all applications (WhatsApp, Outlook,
Discord, Slack, Telegram, etc.), web browsers (Chrome, Edge, Firefox, Brave websites),
and Windows System services in real-time in the background.

Dispatches non-blocking alerts:
- Human-like voice announcements with context awareness
- Rich UI cards in chat_bridge.json for the frontend HUD
- Real-time updates in status_bridge.json
- Persistent structured storage in memory/notifications.json
"""

import os
import sys
import time
import json
import uuid
import datetime
import threading
import asyncio
from typing import Dict, Any, List, Optional, Tuple, Callable

# Windows Runtime / Toast Notification APIs
try:
    import winsdk.windows.ui.notifications as notif
    import winsdk.windows.ui.notifications.management as mgmt
    WINSDK_AVAILABLE = True
except ImportError:
    WINSDK_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTIFICATIONS_FILE = os.path.join(BASE_DIR, "memory", "notifications.json")
CHAT_BRIDGE_FILE = os.path.join(BASE_DIR, "chat_bridge.json")
STATUS_BRIDGE_FILE = os.path.join(BASE_DIR, "status_bridge.json")

# Applications to ignore (internal developer IDE prompts / self-echoes)
IGNORED_APP_PATTERNS = [
    "antigravity ide",  # Ignore internal terminal permission toasts during pairing
    "neura ai",         # Avoid echo of self-generated toasts
]


class SystemNotificationListener:
    """
    Background daemon listener capturing notifications across all Windows applications,
    browsers, and system alerts using Windows UserNotificationListener WinRT API.
    """

    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls, voice_speaker_fn: Optional[Callable[[str], None]] = None):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = SystemNotificationListener(voice_speaker_fn=voice_speaker_fn)
            elif voice_speaker_fn is not None:
                cls._instance.voice_speaker = voice_speaker_fn
            return cls._instance

    def __init__(self, voice_speaker_fn: Optional[Callable[[str], None]] = None):
        self.voice_speaker = voice_speaker_fn
        self.notifications: List[Dict[str, Any]] = []
        self.seen_ids: set = set()
        self._lock = threading.RLock()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._initialized_seen = False
        self._announcement_queue: List[str] = []
        self._is_announcing = False

        self.load_notifications()

    def load_notifications(self):
        """Loads historical notifications from memory storage."""
        with self._lock:
            if os.path.exists(NOTIFICATIONS_FILE):
                try:
                    with open(NOTIFICATIONS_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            self.notifications = data
                            # Populate seen IDs from storage
                            for item in self.notifications:
                                notif_id = item.get("id")
                                if notif_id is not None:
                                    self.seen_ids.add(notif_id)
                except Exception as e:
                    print(f"⚠️ [NotificationListener] Load storage note: {e}")
                    self.notifications = []
            else:
                self.notifications = []

    def save_notifications(self):
        """Persists notification history safely to disk."""
        with self._lock:
            try:
                os.makedirs(os.path.dirname(NOTIFICATIONS_FILE), exist_ok=True)
                temp_file = f"{NOTIFICATIONS_FILE}.tmp"
                # Keep up to 100 recent notifications
                save_data = self.notifications[-100:]
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(save_data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_file, NOTIFICATIONS_FILE)
            except Exception as e:
                print(f"⚠️ [NotificationListener] Save storage error: {e}")

    def start(self):
        """Starts the background continuous notification listener thread."""
        with self._lock:
            if self._running:
                return
            if not WINSDK_AVAILABLE:
                print("⚠️ [NotificationListener] winsdk is not installed; notification listening disabled.")
                return

            self._running = True
            self._worker_thread = threading.Thread(
                target=self._run_async_worker,
                daemon=True,
                name="NeuraNotificationListenerWorker"
            )
            self._worker_thread.start()
            print("🔔 [NotificationListener] Continuous cross-app background notification listener active.")

    def stop(self):
        """Stops the notification listener gracefully."""
        with self._lock:
            self._running = False

    def _run_async_worker(self):
        """Entry point for the async event loop in the daemon worker thread."""
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._worker_loop())
        except Exception as e:
            print(f"⚠️ [NotificationListener Worker Exception]: {e}")
        finally:
            try:
                loop.close()
            except Exception:
                pass
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass

    async def _worker_loop(self):
        """Continuously inspects Windows notifications in the background."""
        listener = None
        try:
            listener = mgmt.UserNotificationListener.current
            status = listener.get_access_status()
            # If not allowed, attempt requesting access
            if status != mgmt.UserNotificationListenerAccessStatus.ALLOWED:
                print("🔔 [NotificationListener] Requesting Windows notification listener access...")
                status = await listener.request_access_async()
                print(f"🔔 [NotificationListener] Access request status: {status}")
        except Exception as e:
            print(f"⚠️ [NotificationListener] WinRT initialization note: {e}")
            return

        # Phase 1: Snapshot existing notifications so Neura doesn't blurt out stale alerts
        try:
            initial_toasts = await listener.get_notifications_async(notif.NotificationKinds.TOAST)
            initial_count = len(initial_toasts)
            for i in range(initial_count):
                try:
                    t = initial_toasts[i]
                    self.seen_ids.add(t.id)
                except Exception:
                    pass
            self._initialized_seen = True
            print(f"🔔 [NotificationListener] Initialized: {len(self.seen_ids)} existing notifications snapshot as acknowledged.")
        except Exception as e:
            print(f"⚠️ [NotificationListener] Initial snapshot note: {e}")
            self._initialized_seen = True

        # Phase 2: Continuous monitoring loop
        while self._running:
            try:
                raw_toasts = await listener.get_notifications_async(notif.NotificationKinds.TOAST)
                count = len(raw_toasts)
                new_items = []

                for i in range(count):
                    try:
                        t = raw_toasts[i]
                        if t.id not in self.seen_ids:
                            self.seen_ids.add(t.id)
                            new_items.append(t)
                    except Exception:
                        continue

                # Process all detected new notifications
                for item in new_items:
                    self._process_single_notification(item)

            except Exception as e:
                # Sleep briefly on error to prevent busy looping
                await asyncio.sleep(2.0)
                continue

            # Check every 1.0 second non-blockingly
            await asyncio.sleep(1.0)

    def _process_single_notification(self, toast_item):
        """Parses and handles a single new incoming notification."""
        try:
            notif_id = toast_item.id
            app_info = toast_item.app_info
            app_name = "Windows"
            app_id = ""

            if app_info and app_info.display_info and app_info.display_info.display_name:
                app_name = app_info.display_info.display_name.strip()
            elif app_info and app_info.id:
                app_name = app_info.id.strip()

            if app_info and app_info.id:
                app_id = app_info.id.strip()

            # Filter out ignored internal developer apps
            app_lower = app_name.lower()
            if any(p in app_lower for p in IGNORED_APP_PATTERNS):
                return

            # Extract visual text elements (Title, Body, etc.)
            texts = []
            try:
                binding = toast_item.notification.visual.get_binding(notif.KnownNotificationBindings.toast_generic)
                if binding:
                    elements = binding.get_text_elements()
                    texts = [el.text.strip() for el in elements if el.text and el.text.strip()]
            except Exception:
                pass

            # Fallback: inspect any bindings if toast_generic was empty
            if not texts:
                try:
                    for b in toast_item.notification.visual.bindings:
                        elements = b.get_text_elements()
                        t_list = [el.text.strip() for el in elements if el.text and el.text.strip()]
                        if t_list:
                            texts = t_list
                            break
                except Exception:
                    pass

            if not texts:
                texts = ["Notification Alert"]

            title = texts[0]
            body = " ".join(texts[1:]) if len(texts) > 1 else ""

            # Ignore internal developer toasts matching terminal permission requests
            if "Requesting your permission in Terminal" in title or "Command:" in body:
                return

            # Format spoken text and user notification
            spoken_text = self._format_speech(app_name, title, body)
            now_dt = datetime.datetime.now()

            record = {
                "id": notif_id,
                "app_name": app_name,
                "app_id": app_id,
                "title": title,
                "body": body,
                "raw_texts": texts,
                "spoken_text": spoken_text,
                "timestamp": now_dt.isoformat(),
                "time_str": now_dt.strftime("%I:%M %p"),
                "date_str": now_dt.strftime("%Y-%m-%d"),
                "read": False
            }

            with self._lock:
                self.notifications.append(record)
                self.save_notifications()

            print(f"\n🔔 [NEW NOTIFICATION DETECTED]")
            print(f"   From App: {app_name}")
            print(f"   Title   : {title}")
            print(f"   Message : {body}")
            print(f"   Spoken  : {spoken_text}")

            # 1. Dispatch Audio Cue Chime (gentle beep)
            self._play_notification_chime()

            # 2. Update Chat Bridge (Instant frontend UI reflection)
            self._push_chat_bridge(app_name, title, body, now_dt.strftime("%I:%M %p"))

            # 3. Update Status Bridge
            self._update_status_bridge(app_name, title)

            # 4. Speak notification verbally to the user
            self._announce_voice(spoken_text)

        except Exception as e:
            print(f"⚠️ [NotificationListener] Error processing notification: {e}")

    def _format_speech(self, app_name: str, title: str, body: str) -> str:
        """
        Creates a natural, courteous, context-aware verbal announcement for Neura.
        """
        app_clean = app_name.strip()
        app_lower = app_clean.lower()
        title_clean = title.strip()
        body_clean = body.strip()

        # Shorten very long bodies for spoken voice while full text is in chat
        spoken_body = body_clean
        if len(spoken_body) > 130:
            spoken_body = spoken_body[:125].rsplit(" ", 1)[0] + "..."

        # Check if title indicates source app (e.g. browser forwarding WhatsApp/Telegram)
        title_lower = title_clean.lower()
        if any(m in title_lower for m in ["whatsapp", "telegram", "slack", "discord", "outlook", "gmail"]):
            if spoken_body:
                return f"Sir, you have a new notification from {title_clean}: {spoken_body}"
            else:
                return f"Sir, you have a new notification from {title_clean}."

        # Messaging apps (WhatsApp, Telegram, Signal, Discord, Slack, Messenger)
        if any(m in app_lower for m in ["whatsapp", "telegram", "signal", "discord", "slack", "messenger", "messages"]):
            if spoken_body:
                return f"Sir, you have a new {app_clean} message from {title_clean}. They say: {spoken_body}"
            else:
                return f"Sir, you have a new message from {title_clean} on {app_clean}."

        # Web Browsers (Chrome, Edge, Brave, Firefox, Opera)
        if any(b in app_lower for b in ["chrome", "edge", "brave", "firefox", "opera"]):
            if spoken_body:
                return f"Sir, you have a website notification from {app_clean}. {title_clean}: {spoken_body}"
            else:
                return f"Sir, you received a web alert from {app_clean}: {title_clean}."

        # Email clients (Outlook, Mail, Thunderbird, Gmail)
        if any(e in app_lower for e in ["outlook", "mail", "thunderbird", "gmail"]):
            if spoken_body:
                return f"Sir, you have a new email from {title_clean}. Subject: {spoken_body}"
            else:
                return f"Sir, you received a new email from {title_clean}."

        # System & Windows alerts
        if any(s in app_lower for s in ["windows", "system", "security", "defender", "update", "battery", "lenovo"]):
            if spoken_body:
                return f"Sir, system notification from {app_clean}. {title_clean}: {spoken_body}"
            else:
                return f"Sir, system notification from {app_clean}: {title_clean}."

        # General apps
        if spoken_body:
            return f"Sir, you have a new notification from {app_clean}. {title_clean}: {spoken_body}"
        else:
            return f"Sir, you have a notification from {app_clean}: {title_clean}."

    def _play_notification_chime(self):
        """Plays a gentle native Windows chime non-blockingly."""
        def _chime_thread():
            try:
                import winsound
                # Subtle pleasant system asterisk chime
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass
        threading.Thread(target=_chime_thread, daemon=True, name="NeuraNotifChime").start()

    def _push_chat_bridge(self, app_name: str, title: str, body: str, time_str: str):
        """Appends notification card to chat_bridge.json so the frontend HUD displays it."""
        try:
            body_block = f"\n{body}" if body else ""
            msg = f"🔔 **Notification Alert • {app_name}**\n**{title}**{body_block}\n*Received at {time_str}*"
            payload = {
                "time": time_str,
                "role": "neura",
                "message": msg
            }
            data = []
            if os.path.exists(CHAT_BRIDGE_FILE):
                try:
                    with open(CHAT_BRIDGE_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = []

            data.append(payload)
            if len(data) > 60:
                data = data[-60:]

            temp_bridge = f"{CHAT_BRIDGE_FILE}.tmp"
            with open(temp_bridge, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_bridge, CHAT_BRIDGE_FILE)
        except Exception as e:
            print(f"⚠️ [NotificationListener] Chat bridge note: {e}")

    def _update_status_bridge(self, app_name: str, title: str):
        """Publishes the notification to status_bridge.json for UI status indicators."""
        try:
            data = {}
            if os.path.exists(STATUS_BRIDGE_FILE):
                try:
                    with open(STATUS_BRIDGE_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {}

            unread_count = sum(1 for n in self.notifications if not n.get("read", False))
            data["last_system_notification"] = f"{app_name}: {title}"
            data["unread_notifications_count"] = unread_count
            data["notification_listener_active"] = True

            temp_bridge = f"{STATUS_BRIDGE_FILE}.tmp"
            with open(temp_bridge, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_bridge, STATUS_BRIDGE_FILE)
        except Exception:
            pass

    def _announce_voice(self, spoken_text: str):
        """Dispatches voice announcement safely without blocking the listener thread."""
        def _speak_worker():
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass

            # Wait briefly if assistant is currently speaking to avoid speech collision
            attempts = 0
            while attempts < 10:
                # If a global speaking flag is active, pause briefly
                import __main__
                is_speaking = getattr(__main__, "ASSISTANT_IS_SPEAKING", False)
                if not is_speaking:
                    break
                time.sleep(0.4)
                attempts += 1

            if self.voice_speaker:
                try:
                    self.voice_speaker(spoken_text)
                except Exception as e:
                    print(f"⚠️ [NotificationListener Voice Note]: {e}")
            else:
                print(f"🔊 [Neura Notification Voice]: {spoken_text}")

            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass

        threading.Thread(target=_speak_worker, daemon=True, name="NeuraNotifSpeaker").start()

    # =========================================================================
    # Query & Command Methods (for natural voice queries)
    # =========================================================================

    def get_recent_notifications(
        self,
        limit: int = 5,
        app_filter: Optional[str] = None,
        unread_only: bool = False
    ) -> List[Dict[str, Any]]:
        """Returns recent notifications, optionally filtered by application."""
        with self._lock:
            items = list(reversed(self.notifications))
            if app_filter:
                flt = app_filter.strip().lower()
                items = [n for n in items if flt in n.get("app_name", "").lower()]
            if unread_only:
                items = [n for n in items if not n.get("read", False)]
            return items[:limit]

    def format_notifications_summary(
        self,
        limit: int = 3,
        app_filter: Optional[str] = None
    ) -> str:
        """Returns spoken summary of recent notifications."""
        items = self.get_recent_notifications(limit=limit, app_filter=app_filter)
        if not items:
            if app_filter:
                return f"Sir, you currently have no recent notifications from {app_filter.capitalize()}."
            return "Sir, you currently have no recent notifications."

        count = len(items)
        if count == 1:
            it = items[0]
            app = it.get("app_name", "an application")
            title = it.get("title", "")
            body = it.get("body", "")
            body_part = f" It says: {body}" if body else ""
            return f"Sir, you have 1 recent notification from {app}. {title}.{body_part}"

        lines = [f"Sir, you have {count} recent notifications:"]
        for idx, it in enumerate(items, 1):
            app = it.get("app_name", "App")
            title = it.get("title", "")
            lines.append(f"{idx}. From {app}: {title}.")
        return " ".join(lines)

    def format_notifications_card(
        self,
        limit: int = 5,
        app_filter: Optional[str] = None
    ) -> str:
        """Returns Markdown UI card for HUD chat."""
        items = self.get_recent_notifications(limit=limit, app_filter=app_filter)
        lines = [
            "🔔 **Neura Notification Monitor**\n",
            "• **Background Listener**: Active & Parallel ✅",
            f"• **Stored Notifications**: {len(self.notifications)} total",
        ]
        if not items:
            lines.append("\n*Sir, you currently have no notifications on record.*")
        else:
            lines.append(f"\n**Recent Notifications:**")
            for idx, it in enumerate(items, 1):
                app = it.get("app_name", "App")
                title = it.get("title", "")
                body = it.get("body", "")
                t_str = it.get("time_str", "")
                lines.append(f"{idx}. 📲 **{app}** — *{t_str}*")
                lines.append(f"   **{title}**")
                if body:
                    lines.append(f"   > {body}")
            lines.append(f"\n*I will automatically notify you with voice as new notifications arrive, Sir.*")
        return "\n".join(lines)

    def clear_notifications(self) -> Tuple[int, str]:
        """Clears all stored notifications."""
        with self._lock:
            count = len(self.notifications)
            self.notifications.clear()
            self.save_notifications()
        self._update_status_bridge("None", "Clear")
        return count, f"Cleared {count} stored notifications, Sir."


def get_system_notification_listener(voice_speaker_fn: Optional[Callable[[str], None]] = None) -> SystemNotificationListener:
    """Returns singleton instance of SystemNotificationListener."""
    return SystemNotificationListener.get_instance(voice_speaker_fn=voice_speaker_fn)
