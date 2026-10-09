import os
import sys

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from brain.intent_router import route_intent, IntentType

def run_tests():
    open_phrases = [
        "open agent workspace",
        "show agent workspace",
        "open workspace",
        "show workspace",
        "open the agent workspace",
        "show the agent workspace",
        "display workspace",
        "launch workspace",
        "view workspace",
        "open 3d workspace",
        "show 3d workspace",
        "take me to agent workspace",
        "open agent office",
        "show agent office",
        "show 3d visualization of the agent works",
        "show me what the agents are doing",
        "agent workspace",
    ]

    close_phrases = [
        "close agent workspace",
        "close the agent workspace",
        "close workspace",
        "close the workspace",
        "hide agent workspace",
        "hide workspace",
        "exit workspace",
        "exit agent workspace",
        "leave workspace",
        "dismiss workspace",
        "close agent office",
        "close office",
        "hide office",
        "back to hud",
        "return to hud",
        "back to main screen",
        "return to main screen",
        "close popup",
        "close that one",
        "close that",
        "switch to camera",
        "back to camera"
    ]

    exit_phrases = [
        "exit",
        "quit",
        "bye",
        "goodbye",
        "exit neura",
        "quit assistant"
    ]

    print("--- TESTING OPEN WORKSPACE INTENTS ---")
    for phrase in open_phrases:
        intent, meta = route_intent(phrase)
        assert intent == IntentType.AGENT_OFFICE_SHOW, f"Failed for '{phrase}': got {intent}"
        print(f"  [PASS] '{phrase}' -> {intent}")

    print("\n--- TESTING CLOSE WORKSPACE INTENTS ---")
    for phrase in close_phrases:
        intent, meta = route_intent(phrase)
        assert intent == IntentType.AGENT_OFFICE_CLOSE, f"Failed for '{phrase}': got {intent}"
        print(f"  [PASS] '{phrase}' -> {intent}")

    print("\n--- TESTING ASSISTANT EXIT INTENTS ---")
    for phrase in exit_phrases:
        intent, meta = route_intent(phrase)
        assert intent == IntentType.EXIT, f"Failed for '{phrase}': got {intent}"
        print(f"  [PASS] '{phrase}' -> {intent}")

    print("\nALL WORKSPACE VOICE COMMAND ROUTING TESTS PASSED!")

if __name__ == "__main__":
    run_tests()
