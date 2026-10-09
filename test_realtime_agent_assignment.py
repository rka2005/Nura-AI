import os
import sys
import json
import time

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from brain.intent_router import route_intent, IntentType
from brain.agents.orchestrator import AgentOrchestrator
from office_view import OfficeView

def test_intent_routing():
    print("--- 1. TESTING INTENT ROUTING FOR TESTING COMMANDS ---")
    test_queries = [
        "test",
        "testing",
        "run tests",
        "run the tests",
        "start testing",
        "test project",
        "test the project",
        "test this project",
        "test my project",
        "test codebase",
        "test the codebase",
        "test app",
        "run unit tests",
        "test all",
        "test everything"
    ]
    for q in test_queries:
        intent, meta = route_intent(q)
        assert intent == IntentType.AGENT_PROJECT_TEST, f"Query '{q}' routed to {intent}, expected AGENT_PROJECT_TEST"
        print(f"  [PASS] '{q}' -> {intent}")

def test_realtime_assignment_and_bridge_sync():
    print("\n--- 2. TESTING REALTIME AGENT ASSIGNMENT & BRIDGE SYNC ---")
    orch = AgentOrchestrator()
    view = OfficeView()

    # 1. Project Testing Assignment
    print("\nTesting task assignment: AGENT_PROJECT_TEST")
    orch.assign_agents_for_intent(IntentType.AGENT_PROJECT_TEST, query="test the codebase")
    
    status_dict = orch.get_agents_status_dict()
    assert "project_tester" in status_dict, "Missing project_tester in status_dict"
    assert status_dict["project_tester"]["status"] == "BUSY", f"Expected BUSY, got {status_dict['project_tester']['status']}"
    assert "test" in status_dict["project_tester"]["task"].lower(), f"Unexpected task: {status_dict['project_tester']['task']}"
    print(f"  [PASS] Orchestrator project_tester status: {status_dict['project_tester']['status']}, task: {status_dict['project_tester']['task']}")

    # Verify status_bridge.json was updated
    with open(orch.status_bridge_file, "r", encoding="utf-8") as f:
        bridge_data = json.load(f)
    assert "agents" in bridge_data, "Missing agents in bridge file"
    assert bridge_data["agents"]["project_tester"]["status"] == "BUSY"
    print(f"  [PASS] status_bridge.json has project_tester: BUSY")

    # Verify OfficeView syncs and activates tester
    view.sync_from_bridge(bridge_data["agents"])
    tester = view.agents["project_tester"]
    assert tester.status == "BUSY", f"OfficeView tester agent status is {tester.status}, expected BUSY"
    assert tester.phase in ("to_room", "working"), f"Unexpected tester phase: {tester.phase}"
    print(f"  [PASS] OfficeView tester agent is {tester.status} (phase: {tester.phase}, task: '{tester.task}')")

    # 2. Diagnostic Multi-Agent Assignment
    print("\nTesting task assignment: AGENT_PROJECT_DIAGNOSTIC")
    orch.assign_agents_for_intent(IntentType.AGENT_PROJECT_DIAGNOSTIC, query="why is my project failing")
    status_dict = orch.get_agents_status_dict()
    assert status_dict["project_tester"]["status"] == "BUSY"
    assert status_dict["screen_vision"]["status"] == "BUSY"
    assert status_dict["system_monitor"]["status"] == "BUSY"
    print("  [PASS] Diagnostic assigned Project, Screen, and Monitor agents simultaneously.")

    # 3. Screen Vision Assignment
    print("\nTesting task assignment: SCREEN_DESCRIBE")
    orch.assign_agents_for_intent(IntentType.SCREEN_DESCRIBE, query="inspect screen")
    status_dict = orch.get_agents_status_dict()
    assert status_dict["screen_vision"]["status"] == "BUSY"
    print(f"  [PASS] Screen vision assigned: {status_dict['screen_vision']['task']}")

    # 4. Computer Use Assignment
    print("\nTesting task assignment: AGENT_COMPUTER_USE")
    orch.assign_agents_for_intent(IntentType.AGENT_COMPUTER_USE, {"goal": "automate browser"}, "automate browser")
    status_dict = orch.get_agents_status_dict()
    assert status_dict["skill_runner"]["status"] == "BUSY"
    assert status_dict["screen_vision"]["status"] == "BUSY"
    print("  [PASS] Computer use assigned Skill Runner and Screen Vision.")

    # 5. Immediate Release Test
    print("\nTesting release_agents")
    orch.release_agents(grace_period=0) # Immediate release for testing
    status_dict = orch.get_agents_status_dict()
    assert status_dict["project_tester"]["status"] == "IDLE"
    assert status_dict["screen_vision"]["status"] == "IDLE"
    print("  [PASS] Agents released back to IDLE successfully.")

    print("\nALL REAL-TIME AGENT ASSIGNMENT TESTS PASSED!")

if __name__ == "__main__":
    test_intent_routing()
    test_realtime_assignment_and_bridge_sync()
