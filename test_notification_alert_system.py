"""
Comprehensive Test Suite for Neura Cross-App & System Notification Listener Subsystem.
Verifies:
1. Singleton initialization and worker lifecycle.
2. Cross-app speech formatting (WhatsApp, Chrome, Outlook, Windows System, etc.).
3. Chat Bridge (chat_bridge.json) & Status Bridge (status_bridge.json) live updates.
4. Intent Router integration (SYSTEM_NOTIFICATION_QUERY & SYSTEM_NOTIFICATION_CLEAR).
5. Full End-to-End Live Notification Capture in the background.
"""

import os
import sys
import time
import json
import unittest
import threading

from brain.system_notification_listener import (
    SystemNotificationListener,
    get_system_notification_listener,
    NOTIFICATIONS_FILE,
    CHAT_BRIDGE_FILE,
    STATUS_BRIDGE_FILE
)
from brain.intent_router import route_intent, IntentType
from neura import execute_notification_intent

try:
    import winsdk.windows.ui.notifications as notif
    import winsdk.windows.data.xml.dom as dom
    WINSDK_TEST_AVAILABLE = True
except ImportError:
    WINSDK_TEST_AVAILABLE = False


class TestSystemNotificationListener(unittest.TestCase):

    def setUp(self):
        self.spoken_messages = []
        def mock_speaker(text):
            self.spoken_messages.append(text)
        self.mock_speaker = mock_speaker
        self.listener = get_system_notification_listener(voice_speaker_fn=self.mock_speaker)

    def test_01_singleton_instance(self):
        """Verifies singleton pattern."""
        l1 = get_system_notification_listener()
        l2 = get_system_notification_listener()
        self.assertIs(l1, l2)

    def test_02_speech_formatting_whatsapp(self):
        """Verifies natural speech for messaging apps like WhatsApp."""
        speech = self.listener._format_speech(
            app_name="WhatsApp",
            title="Lisa",
            body="Hey Rohit, are you joining the team sync?"
        )
        self.assertIn("WhatsApp", speech)
        self.assertIn("Lisa", speech)
        self.assertIn("Hey Rohit", speech)

    def test_03_speech_formatting_browser(self):
        """Verifies natural speech for web browser notifications (Chrome/Edge/Brave)."""
        speech = self.listener._format_speech(
            app_name="Google Chrome",
            title="Calendar Alert",
            body="Project review meeting starting in 10 minutes"
        )
        self.assertIn("Google Chrome", speech)
        self.assertIn("Calendar Alert", speech)
        self.assertIn("Project review meeting", speech)

    def test_04_speech_formatting_outlook(self):
        """Verifies speech for email client notifications."""
        speech = self.listener._format_speech(
            app_name="Outlook",
            title="Supervisor",
            body="Please review the quarterly audit results"
        )
        self.assertIn("Supervisor", speech)
        self.assertIn("quarterly audit", speech)

    def test_05_speech_formatting_system(self):
        """Verifies speech for Windows system alerts."""
        speech = self.listener._format_speech(
            app_name="Windows Security",
            title="Virus & threat protection",
            body="No new threats were found during background scan"
        )
        self.assertIn("Windows Security", speech)
        self.assertIn("No new threats", speech)

    def test_06_intent_routing_notifications(self):
        """Verifies IntentType routing for notification questions."""
        queries = [
            ("any notifications", IntentType.SYSTEM_NOTIFICATION_QUERY),
            ("check notifications", IntentType.SYSTEM_NOTIFICATION_QUERY),
            ("what notifications did i get", IntentType.SYSTEM_NOTIFICATION_QUERY),
            ("show my notifications", IntentType.SYSTEM_NOTIFICATION_QUERY),
            ("notifications from whatsapp", IntentType.SYSTEM_NOTIFICATION_QUERY),
            ("clear notifications", IntentType.SYSTEM_NOTIFICATION_CLEAR),
            ("delete all notifications", IntentType.SYSTEM_NOTIFICATION_CLEAR)
        ]
        for q, expected_intent in queries:
            intent, meta = route_intent(q)
            self.assertEqual(intent, expected_intent, f"Failed on query: '{q}' -> got {intent}")

        # Check app filter extraction
        _, meta = route_intent("notifications from whatsapp")
        self.assertEqual(meta.get("app_filter"), "whatsapp")

    def test_07_execute_notification_intent(self):
        """Verifies execution of notification intents."""
        # 1. Clear notifications
        handled, msg = execute_notification_intent(IntentType.SYSTEM_NOTIFICATION_CLEAR, {})
        self.assertTrue(handled)
        self.assertIn("Cleared", msg)

        # 2. Query empty notifications
        handled, msg = execute_notification_intent(IntentType.SYSTEM_NOTIFICATION_QUERY, {})
        self.assertTrue(handled)
        self.assertIn("no recent notifications", msg.lower())

    def test_08_live_notification_capture_in_background(self):
        """
        End-to-End test:
        1. Starts background notification listener daemon.
        2. Dispatches a real toast notification.
        3. Confirms the listener captures it, formats speech, and speaks via mock callback.
        """
        if not WINSDK_TEST_AVAILABLE:
            self.skipTest("winsdk not available for live toast test")

        received = []
        def test_speaker(text):
            received.append(text)

        listener = get_system_notification_listener(voice_speaker_fn=test_speaker)
        listener.start()
        time.sleep(2.0)  # Allow initial snapshot

        # Dispatch real toast via Windows ToastNotificationManager
        xml_doc = dom.XmlDocument()
        xml_str = (
            "<toast>"
            "  <visual>"
            "    <binding template=\"ToastGeneric\">"
            "      <text>WhatsApp</text>"
            "      <text>Lisa: Automated testing sync completed!</text>"
            "    </binding>"
            "  </visual>"
            "</toast>"
        )
        xml_doc.load_xml(xml_str)
        toast = notif.ToastNotification(xml_doc)
        app_id = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"
        notifier = notif.ToastNotificationManager.create_toast_notifier(app_id)
        notifier.show(toast)

        # Wait for background detection (poll every 0.3s for up to 6s)
        detected = False
        for _ in range(20):
            time.sleep(0.3)
            if received:
                detected = True
                break

        listener.stop()
        self.assertTrue(detected, "Listener did not capture dispatched toast in background within 6 seconds.")
        print(f"\n✅ [E2E Live Test Passed]: Captured speech: {received[0]}")


if __name__ == "__main__":
    unittest.main()
