"""
Test Suite for Neura AI Email and WhatsApp Messaging Automation.
Verifies permission management, default mail ID resolution, structured email drafting,
WhatsApp Web URL generation, intent routing, and regression safety.
"""

import os
import unittest
from unittest.mock import patch, MagicMock

from brain.intent_router import route_intent, IntentType
from brain.communication_controller import CommunicationController, get_communication_controller
from memory.memory_manager import MemoryManager
from neura import execute_communication_intent, ask_neura

class TestCommunicationSystem(unittest.TestCase):

    def setUp(self):
        self.mem_mgr = MemoryManager()
        self.comm_ctrl = CommunicationController(memory_manager=self.mem_mgr)
        # Ensure permission is enabled for functional tests
        self.comm_ctrl.set_permission(True)

    def test_01_permission_grant_and_revoke_routing(self):
        """Verifies intent routing for email and messaging permissions."""
        i1, m1 = route_intent("give permission to send any email or message")
        self.assertEqual(i1, IntentType.SYSTEM_PERMISSION)
        self.assertEqual(m1.get("action"), "grant")
        self.assertEqual(m1.get("permission_type"), "email_messaging")

        i2, m2 = route_intent("now i want to give permission to send any email or message")
        self.assertEqual(i2, IntentType.SYSTEM_PERMISSION)
        self.assertEqual(m2.get("action"), "grant")

        i3, m3 = route_intent("grant permission to send email or message")
        self.assertEqual(i3, IntentType.SYSTEM_PERMISSION)
        self.assertEqual(m3.get("action"), "grant")

        i4, m4 = route_intent("revoke email and message permission")
        self.assertEqual(i4, IntentType.SYSTEM_PERMISSION)
        self.assertEqual(m4.get("action"), "revoke")
        self.assertEqual(m4.get("permission_type"), "email_messaging")

    def test_02_permission_persistence_and_enforcement(self):
        """Verifies permission persistence and blocking when revoked."""
        # Grant
        res = self.comm_ctrl.set_permission(True)
        self.assertTrue(self.comm_ctrl.is_permission_granted())
        self.assertIn("granted", res.lower())

        # Revoke
        res = self.comm_ctrl.set_permission(False)
        self.assertFalse(self.comm_ctrl.is_permission_granted())
        self.assertIn("revoked", res.lower())

        # Attempt sending email while permission is revoked
        handled, msg, meta = self.comm_ctrl.send_structured_email(
            to_email="test@example.com",
            subject="Test",
            body="Hello"
        )
        self.assertFalse(handled)
        self.assertIn("disabled", msg.lower())

        # Attempt WhatsApp message while revoked
        handled_wa, msg_wa = self.comm_ctrl.send_whatsapp_message(
            recipient="+919876543210",
            message="Hi"
        )
        self.assertFalse(handled_wa)
        self.assertIn("disabled", msg_wa.lower())

        # Re-grant for remaining tests
        self.comm_ctrl.set_permission(True)

    def test_03_default_mail_id_resolution(self):
        """Verifies default mail ID resolution when sender is not specified."""
        default_email = self.comm_ctrl.get_default_email()
        self.assertTrue(bool(default_email))
        self.assertIn("@", default_email)
        # Should resolve to rohitadak0@gmail.com by default
        self.assertEqual(default_email, "rohitadak0@gmail.com")

    def test_04_structured_email_default_sender_and_formatting(self):
        """Verifies structured email composition uses default mail ID and builds HTML + plain text."""
        with patch("webbrowser.open") as mock_browser:
            handled, speech, meta = self.comm_ctrl.send_structured_email(
                to_email="colleague@example.com",
                subject="Sprint Review Meeting",
                body="The review meeting has been scheduled for tomorrow at 11 AM.\nPlease review the roadmap."
            )

            self.assertTrue(handled)
            self.assertIn("colleague@example.com", speech)
            self.assertEqual(meta["from_email"], "rohitadak0@gmail.com")
            self.assertEqual(meta["to_email"], "colleague@example.com")
            self.assertEqual(meta["subject"], "Sprint Review Meeting")

            # Check that files were created on disk
            self.assertTrue(os.path.exists(meta["html_path"]))
            self.assertTrue(os.path.exists(meta["text_path"]))

            # Verify HTML contents
            with open(meta["html_path"], "r", encoding="utf-8") as f:
                html_text = f.read()
            self.assertIn("Sprint Review Meeting", html_text)
            self.assertIn("The review meeting has been scheduled", html_text)
            self.assertIn("rohitadak0@gmail.com", html_text)
            self.assertIn("NEURA AI • COMMUNICATION DISPATCH", html_text)

            # Verify Plain Text contents
            with open(meta["text_path"], "r", encoding="utf-8") as f:
                plain_text = f.read()
            self.assertIn("Dear Colleague,", plain_text)
            self.assertIn("Best regards,", plain_text)
            self.assertIn("Sent via Neura AI Assistant", plain_text)

    def test_05_structured_email_custom_sender(self):
        """Verifies structured email respects an explicitly stated from_email."""
        with patch("webbrowser.open"):
            handled, speech, meta = self.comm_ctrl.send_structured_email(
                to_email="client@example.com",
                subject="Invoice #1024",
                body="Please find attached invoice.",
                from_email="custom.work@enterprise.com"
            )
            self.assertTrue(handled)
            self.assertEqual(meta["from_email"], "custom.work@enterprise.com")

    def test_06_whatsapp_number_browser_dispatch(self):
        """Verifies WhatsApp Web opens in default browser with target phone number and encoded text."""
        with patch("webbrowser.open") as mock_browser, \
             patch("brain.desktop_controller.DesktopController.copy_text_to_clipboard") as mock_clip:
            
            handled, speech = self.comm_ctrl.send_whatsapp_message(
                recipient="+919876543210",
                message="Hello from Neura AI automated test!"
            )

            self.assertTrue(handled)
            self.assertIn("+919876543210", speech)
            mock_browser.assert_called_once()
            opened_url = mock_browser.call_args[0][0]
            self.assertTrue(opened_url.startswith("https://web.whatsapp.com/send?phone=919876543210&text="))
            self.assertIn("Hello%20from%20Neura%20AI", opened_url)
            mock_clip.assert_called_once_with("Hello from Neura AI automated test!")

    def test_07a_whatsapp_contact_name_switches_existing_tab(self):
        """Verifies WhatsApp Web switches to existing tab when already open in default browser."""
        with patch.object(self.comm_ctrl, "is_whatsapp_open_in_browser", return_value=(True, 66886, "tab_item")), \
             patch.object(self.comm_ctrl, "focus_window_hwnd", return_value=True) as mock_focus, \
             patch("webbrowser.open") as mock_browser, \
             patch("brain.desktop_controller.DesktopController.copy_text_to_clipboard") as mock_clip:

            handled, speech = self.comm_ctrl.send_whatsapp_message(
                recipient="Puja",
                message="Are you coming today?"
            )

            self.assertTrue(handled)
            self.assertIn("Puja", speech)
            self.assertIn("switched", speech.lower())
            mock_browser.assert_not_called()
            mock_focus.assert_called_once_with(66886)
            mock_clip.assert_called_once_with("Are you coming today?")

    def test_07b_whatsapp_contact_name_opens_new_tab_when_not_open(self):
        """Verifies WhatsApp Web opens in default browser when not already open."""
        with patch.object(self.comm_ctrl, "is_whatsapp_open_in_browser", return_value=(False, None, "not_found")), \
             patch("webbrowser.open") as mock_browser, \
             patch("brain.desktop_controller.DesktopController.copy_text_to_clipboard") as mock_clip:

            handled, speech = self.comm_ctrl.send_whatsapp_message(
                recipient="Puja",
                message="Are you coming today?"
            )

            self.assertTrue(handled)
            self.assertIn("Puja", speech)
            self.assertIn("opening", speech.lower())
            mock_browser.assert_called_once_with("https://web.whatsapp.com")
            mock_clip.assert_called_once_with("Are you coming today?")

    def test_07c_switch_to_or_open_whatsapp_web_logic(self):
        """Directly verifies switch_to_or_open_whatsapp_web logic."""
        with patch.object(self.comm_ctrl, "is_whatsapp_open_in_browser", return_value=(True, 12345, "window_title")), \
             patch.object(self.comm_ctrl, "focus_window_hwnd", return_value=True) as mock_focus, \
             patch("webbrowser.open") as mock_browser:
            
            is_open, action = self.comm_ctrl.switch_to_or_open_whatsapp_web()
            self.assertTrue(is_open)
            self.assertEqual(action, "switched_existing")
            mock_focus.assert_called_once_with(12345)
            mock_browser.assert_not_called()

        with patch.object(self.comm_ctrl, "is_whatsapp_open_in_browser", return_value=(False, None, "not_found")), \
             patch("webbrowser.open") as mock_browser:
            
            is_open, action = self.comm_ctrl.switch_to_or_open_whatsapp_web("https://web.whatsapp.com/test")
            self.assertFalse(is_open)
            self.assertEqual(action, "opened_new")
            mock_browser.assert_called_once_with("https://web.whatsapp.com/test")

    def test_08_intent_routing_whatsapp_queries(self):
        """Verifies diverse natural language WhatsApp commands route cleanly."""
        queries = [
            ("send whatsapp message to +919876543210 saying hello how are you", "+919876543210", "hello how are you"),
            ("send whatsapp to 9876543210 that I have arrived", "9876543210", "I have arrived"),
            ("send message to Puja on whatsapp saying let's meet at 5", "Puja", "let's meet at 5"),
            ("whatsapp Rohan that I am on my way", "Rohan", "I am on my way"),
            ("open whatsapp web and send message to 9876543210 saying test", "9876543210", "test")
        ]

        for q, expected_rec, expected_msg in queries:
            intent, meta = route_intent(q)
            self.assertEqual(intent, IntentType.COMMUNICATION_WHATSAPP, f"Failed on query: {q}")
            self.assertEqual(meta.get("recipient"), expected_rec, f"Wrong recipient for: {q}")
            self.assertEqual(meta.get("message"), expected_msg, f"Wrong message for: {q}")

    def test_09_intent_routing_email_queries(self):
        """Verifies diverse natural language Email commands route cleanly."""
        queries = [
            ("send email to rohitadak0@gmail.com saying please check the code", "rohitadak0@gmail.com", None, "please check the code"),
            ("send an email to test@domain.com with subject Project Report saying here is the doc", "test@domain.com", "Project Report", "here is the doc"),
            ("send mail from custom@work.com to rohitadak0@gmail.com saying hi there", "rohitadak0@gmail.com", None, "hi there"),
            ("mail to colleague@test.com that we are delayed", "colleague@test.com", None, "we are delayed")
        ]

        for q, expected_rec, expected_subj, expected_body in queries:
            intent, meta = route_intent(q)
            self.assertEqual(intent, IntentType.COMMUNICATION_EMAIL, f"Failed on query: {q}")
            self.assertEqual(meta.get("recipient"), expected_rec, f"Wrong recipient for: {q}")
            if expected_subj:
                self.assertEqual(meta.get("subject"), expected_subj)
            self.assertEqual(meta.get("body"), expected_body)

    def test_10_neura_integration_execution(self):
        """Verifies end-to-end execution of communication intents via execute_communication_intent and ask_neura."""
        with patch("webbrowser.open"), patch("neura.speak"):
            # Test direct intent execution
            h1, res1 = execute_communication_intent(
                IntentType.COMMUNICATION_EMAIL,
                {"recipient": "tester@test.com", "body": "End to end test passing."},
                "send email to tester@test.com saying End to end test passing."
            )
            self.assertTrue(h1)
            self.assertIn("tester@test.com", res1)

            h2, res2 = execute_communication_intent(
                IntentType.COMMUNICATION_WHATSAPP,
                {"recipient": "+919876543210", "message": "Automated Neura verification."},
                "send whatsapp message to +919876543210 saying Automated Neura verification."
            )
            self.assertTrue(h2)
            self.assertIn("+919876543210", res2)

            # Test ask_neura top-level integration
            res_ask = ask_neura("give permission to send any email or message")
            self.assertIn("granted", res_ask.lower())

if __name__ == "__main__":
    unittest.main()
