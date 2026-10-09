"""
Unit and integration tests for Neura Alert and Alarm Subsystem.
Validates exact calculations for relative offset loophole queries, direct timers,
scheduling, cancellation, listing, and background trigger execution.
"""

import os
import sys
import time
import datetime
import unittest

# Ensure workspace root is on sys.path
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

from brain.alert_service import (
    parse_alert_request,
    extract_duration,
    extract_clock_time,
    format_duration_friendly,
    AlertService,
    get_alert_service
)


class TestAlertSystem(unittest.TestCase):
    def setUp(self):
        self.now = datetime.datetime(2026, 10, 9, 11, 0, 0)

    def test_01_loophole_before_offset(self):
        """
        User: 'i have a meeting after 5 minutes, so alert me before 2 minutes of that'
        Expected: 5 min - 2 min = 3 min (180 seconds).
        """
        q = "i have a meeting after 5 minutes, so alert me before 2 minutes of that"
        res = parse_alert_request(q, base_dt=self.now)
        self.assertTrue(res["success"])
        self.assertEqual(res["action"], "set")
        self.assertEqual(res["delay_seconds"], 180.0)
        self.assertIn("Meeting", res["label"])
        print("\n[TEST 1 PASSED] 5m - 2m before offset => 180s (3m):", res["explanation"])

    def test_02_loophole_explicit_after_offset(self):
        """
        User: 'i have a meeting after 5 minutes, so alert me after 3 minutes'
        Expected: 3 min (180 seconds).
        """
        q = "i have a meeting after 5 minutes, so alert me after 3 minutes"
        res = parse_alert_request(q, base_dt=self.now)
        self.assertTrue(res["success"])
        self.assertEqual(res["action"], "set")
        self.assertEqual(res["delay_seconds"], 180.0)
        self.assertIn("Meeting", res["label"])
        print("\n[TEST 2 PASSED] 5m meeting, alert after 3m => 180s (3m):", res["explanation"])

    def test_03_loophole_10m_before_3m(self):
        """
        User: 'i have a meeting in 10 minutes, alert me 3 minutes before that'
        Expected: 10 min - 3 min = 7 min (420 seconds).
        """
        q = "i have a meeting in 10 minutes, alert me 3 minutes before that"
        res = parse_alert_request(q, base_dt=self.now)
        self.assertTrue(res["success"])
        self.assertEqual(res["delay_seconds"], 420.0)
        print("\n[TEST 3 PASSED] 10m - 3m => 420s (7m):", res["explanation"])

    def test_04_direct_timer_with_event(self):
        """
        User: 'give me alert after 5 minutes that i have a meeting'
        Expected: 5 min (300 seconds), label = 'meeting'.
        """
        q = "give me alert after 5 minutes that i have a meeting"
        res = parse_alert_request(q, base_dt=self.now)
        self.assertTrue(res["success"])
        self.assertEqual(res["delay_seconds"], 300.0)
        self.assertIn("Meeting", res["label"])
        print("\n[TEST 4 PASSED] Direct 5m alert for meeting => 300s:", res["explanation"])

    def test_05_conversational_grammar_timer(self):
        """
        User: 'can you set a alert that i have after 5 minutes i have a meeting'
        Expected: 5 min (300 seconds), label = 'meeting'.
        """
        q = "can you set a alert that i have after 5 minutes i have a meeting"
        res = parse_alert_request(q, base_dt=self.now)
        self.assertTrue(res["success"])
        self.assertEqual(res["delay_seconds"], 300.0)
        print("\n[TEST 5 PASSED] Conversational grammar 5m => 300s:", res["explanation"])

    def test_06_direct_alarm(self):
        """
        User: 'set an alarm for 5 minutes'
        Expected: 5 min (300 seconds).
        """
        q = "set an alarm for 5 minutes"
        res = parse_alert_request(q, base_dt=self.now)
        self.assertTrue(res["success"])
        self.assertEqual(res["delay_seconds"], 300.0)
        print("\n[TEST 6 PASSED] Direct alarm for 5m => 300s:", res["explanation"])

    def test_07_seconds_timer(self):
        """
        User: 'alert me in 30 seconds'
        Expected: 30 seconds.
        """
        q = "alert me in 30 seconds"
        res = parse_alert_request(q, base_dt=self.now)
        self.assertTrue(res["success"])
        self.assertEqual(res["delay_seconds"], 30.0)
        print("\n[TEST 7 PASSED] Direct 30s timer => 30s:", res["explanation"])

    def test_08_list_and_cancel_parsing(self):
        """
        Validates querying and cancellation intents.
        """
        res_list = parse_alert_request("what alarms are set")
        self.assertEqual(res_list["action"], "list")

        res_cancel = parse_alert_request("cancel all alarms")
        self.assertEqual(res_cancel["action"], "cancel")

        res_stop = parse_alert_request("stop alarm")
        self.assertEqual(res_stop["action"], "stop")
        print("\n[TEST 8 PASSED] List and Cancel actions recognized.")

    def test_09_alert_service_lifecycle_and_execution(self):
        """
        Validates AlertService scheduling, active listing, and real triggering.
        """
        spoken_messages = []

        def mock_speaker(msg):
            spoken_messages.append(msg)

        service = AlertService.get_instance(voice_speaker_fn=mock_speaker)
        # Cancel any previous leftover alerts
        service.cancel_alerts("all")

        # Schedule a 1-second alert to test actual trigger execution
        record = service.schedule_alert(
            label="Fast Test Meeting",
            delay_seconds=1.0,
            explanation="Testing fast trigger"
        )
        self.assertEqual(record["status"], "active")

        # Verify active list
        active = service.list_active_alerts()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["label"], "Fast Test Meeting")

        # Wait for trigger (background loop runs every 0.5s)
        time.sleep(2.0)

        # Verify it has triggered
        triggered_alerts = [a for a in service.alerts if a.get("id") == record["id"] and a.get("status") == "triggered"]
        self.assertEqual(len(triggered_alerts), 1)
        self.assertGreaterEqual(len(spoken_messages), 1)
        self.assertIn("fast test meeting", spoken_messages[0].lower())
        print("\n[TEST 9 PASSED] AlertService fired trigger, played alarm & spoke voice message:", spoken_messages[0])

    def test_10_loophole_without_of_that(self):
        """
        User: 'i have a meeting after 5 minutes so alert me before 2 minutes'
        Expected: 5 min - 2 min = 3 min (180 seconds).
        """
        q = "i have a meeting after 5 minutes so alert me before 2 minutes"
        res = parse_alert_request(q, base_dt=self.now)
        self.assertTrue(res["success"])
        self.assertEqual(res["delay_seconds"], 180.0)
        print("\n[TEST 10 PASSED] Without 'of that' 5m - 2m => 180s:", res["explanation"])

    def test_11_clock_time_with_offset(self):
        """
        User: 'i have a meeting at 4:30 pm, alert me 15 minutes before'
        Base time: 11:00 AM -> Meeting: 4:30 PM -> Alert: 4:15 PM (5h 15m = 18900s).
        """
        q = "i have a meeting at 4:30 pm, alert me 15 minutes before"
        res = parse_alert_request(q, base_dt=self.now)
        self.assertTrue(res["success"])
        self.assertEqual(res["delay_seconds"], 18900.0)
        self.assertEqual(res["target_time"].hour, 16)
        self.assertEqual(res["target_time"].minute, 15)
        print("\n[TEST 11 PASSED] 4:30 PM meeting - 15m before => 4:15 PM (18900s):", res["explanation"])

    def test_12_cancel_specific_label(self):
        """
        User: 'cancel the meeting alert'
        """
        res = parse_alert_request("cancel the meeting alert")
        self.assertEqual(res["action"], "cancel")
        self.assertEqual(res["label"], "meeting")
        print("\n[TEST 12 PASSED] Cancel specific alert target recognized:", res["label"])

    def test_13_route_intent_end_to_end(self):
        """
        Validates that route_intent correctly dispatches to SYSTEM_ALERT_SET with parsed metadata.
        """
        from brain.intent_router import route_intent, IntentType
        from neura import execute_alert_intent

        q = "i have a meeting after 5 minutes, so alert me before 2 minutes of that"
        intent, metadata = route_intent(q)
        self.assertEqual(intent, IntentType.SYSTEM_ALERT_SET)
        self.assertEqual(metadata["delay_seconds"], 180.0)

        handled, response = execute_alert_intent(intent, metadata, q)
        self.assertTrue(handled)
        self.assertIn("Sure Sir!", response)
        self.assertIn("3 minutes", response)
        print("\n[TEST 13 PASSED] route_intent -> execute_alert_intent:\n", response)

    def test_14_route_intent_list_and_cancel(self):
        """
        Validates that route_intent correctly handles query listing and cancellation.
        """
        from brain.intent_router import route_intent, IntentType
        from neura import execute_alert_intent

        # List
        intent_list, meta_list = route_intent("what alarms are set")
        self.assertEqual(intent_list, IntentType.SYSTEM_ALERT_LIST)
        handled_l, resp_l = execute_alert_intent(intent_list, meta_list, "what alarms are set")
        self.assertTrue(handled_l)
        self.assertIsInstance(resp_l, str)

        # Cancel
        intent_c, meta_c = route_intent("cancel all alarms")
        self.assertEqual(intent_c, IntentType.SYSTEM_ALERT_CANCEL)
        handled_c, resp_c = execute_alert_intent(intent_c, meta_c, "cancel all alarms")
        self.assertTrue(handled_c)
        self.assertIn("cancelled", resp_c)
        print("\n[TEST 14 PASSED] route_intent List & Cancel:\n", resp_c)

    def test_15_contextual_important_meeting_alert_speech(self):
        """
        Validates exact user example:
        User: 'neura please alert me after 5 minutes that i have an important meeting.'
        Neura Confirmation: 'Sure Sir! I am setting an alert for 5 minutes from now for your important meeting...'
        Trigger Speech: 'Sir! You have an important meeting right now as you have told me. Please get ready for the meeting.'
        """
        from brain.intent_router import route_intent, IntentType
        from neura import execute_alert_intent

        q = "neura please alert me after 5 minutes that i have an important meeting."
        intent, metadata = route_intent(q)
        self.assertEqual(intent, IntentType.SYSTEM_ALERT_SET)
        self.assertEqual(metadata["delay_seconds"], 300.0)

        # Check contextual trigger speech generated
        expected_trigger = "Sir! You have an important meeting right now as you have told me. Please get ready for the meeting."
        self.assertEqual(metadata["trigger_speech"], expected_trigger)

        # Check conversational confirmation
        handled, resp = execute_alert_intent(intent, metadata, q)
        self.assertTrue(handled)
        self.assertIn("Sure Sir!", resp)
        self.assertIn("important meeting", resp)
        self.assertIn("5 minutes", resp)
        print("\n[TEST 15 PASSED] Contextual meeting speech:\n  Confirmation:", resp, "\n  Trigger Speech:", metadata["trigger_speech"])

    def test_16_trigger_speaks_contextual_message(self):
        """
        Tests that when the alert fires, AlertService speaks the exact contextual sentence aloud.
        """
        spoken = []
        def spk(msg):
            spoken.append(msg)

        service = AlertService.get_instance(voice_speaker_fn=spk)
        service.cancel_alerts("all")

        q = "neura please alert me after 5 minutes that i have an important meeting."
        meta = parse_alert_request(q)

        # Schedule for 1 second to test real trigger delivery
        service.schedule_alert(
            label=meta["label"],
            delay_seconds=1.0,
            source_query=q,
            trigger_speech=meta["trigger_speech"]
        )

        time.sleep(2.0)
        self.assertGreaterEqual(len(spoken), 1)
        expected_text = "Sir! You have an important meeting right now as you have told me. Please get ready for the meeting."
        self.assertEqual(spoken[-1], expected_text)
        print("\n[TEST 16 PASSED] Real trigger spoke context:\n", spoken[-1])


if __name__ == "__main__":
    unittest.main()



