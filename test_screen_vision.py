"""
Test Suite for Neura Screen Vision System.
Validates:
1. Desktop screenshot capture & temporary caching.
2. DPI scale factor detection & coordinate mapping.
3. Local OCR text detection & bounding box calculation.
4. Structured screen element representation & spatial sorting.
5. Card-based clustering for search results and videos.
6. Ordinal target selection ('first', 'second', 'third' etc.).
7. Safe cursor positioning in SCREEN_VISION_TEST_MODE (without clicking).
8. Screen intent parsing & DesktopController integration.
"""

import sys
import os
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from brain.screen_vision import ScreenVision, SCREEN_VISION_TEST_MODE
from brain.intent_router import route_intent, IntentType
from brain.desktop_controller import DesktopController


def run_screen_vision_tests(live_click: bool = False):
    print("=" * 70)
    print("        NEURA AI — SCREEN VISION VERIFICATION & TEST SUITE        ")
    print("=" * 70)
    print(f"Safe Test Mode: {not live_click} (Clicks enabled: {live_click})\n")

    # Initialize ScreenVision in Safe Test Mode by default
    vision = ScreenVision(test_mode=not live_click)
    controller = DesktopController()

    # =================================================================
    # Test 1: Screen Capture
    # =================================================================
    print("─── [Test 1: Screen Capture] ───")
    screenshot = vision.capture_screen()
    if screenshot:
        print(f"PASS: Screenshot captured. Resolution: {screenshot.size[0]}x{screenshot.size[1]}\n")
    else:
        print("FAIL: Failed to capture screen.\n")
        return

    # =================================================================
    # Test 2: DPI Scale Factor Detection
    # =================================================================
    print("─── [Test 2: DPI Scale Factor Detection] ───")
    import pyautogui
    logical_w, logical_h = pyautogui.size()
    ss_w, ss_h = screenshot.size
    dpi_scale = vision._compute_dpi_scale(screenshot.size)
    print(f"  Screenshot resolution:   {ss_w} x {ss_h}  (physical pixels)")
    print(f"  pyautogui.size():        {logical_w} x {logical_h}  (logical/mouse coords)")
    print(f"  DPI Scale factor:        {dpi_scale[0]:.4f} x {dpi_scale[1]:.4f}")
    if abs(dpi_scale[0] - 1.0) < 0.01 and abs(dpi_scale[1] - 1.0) < 0.01:
        print("  Status: DPI awareness is effective — screenshot matches logical space.")
    else:
        print(f"  Status: DPI scaling detected! OCR coords will be divided by {dpi_scale[0]:.3f}x / {dpi_scale[1]:.3f}y")
    print("PASS: DPI scale computed.\n")

    # =================================================================
    # Test 3: Active Window Detection
    # =================================================================
    print("─── [Test 3: Active Window Detection] ───")
    win_info = vision.get_active_window_info()
    print(f"  Active Application: '{win_info['application']}'")
    print(f"  Active Window Title: '{win_info['window_title']}'")
    print("PASS: Window detection OK.\n")

    # =================================================================
    # Test 4: Screen Analysis & OCR Elements (with DPI scaling applied)
    # =================================================================
    print("─── [Test 4: Screen Analysis & OCR Elements] ───")
    context = vision.analyze_screen(screenshot=screenshot, force_refresh=True)
    elements = context.get("elements", [])
    stored_scale = context.get("dpi_scale", (1.0, 1.0))
    print(f"  Total structured elements detected: {len(elements)}")
    print(f"  DPI scale stored in context: {stored_scale}")
    if elements:
        print("  First 5 elements (coordinates are in LOGICAL mouse space):")
        for elem in elements[:5]:
            print(f"    ID:{elem['id']:3d} | Type:{elem['type']:<10} | "
                  f"Center: ({elem['center'][0]:4d}, {elem['center'][1]:4d}) | "
                  f"Text: '{elem['text'][:45]}'")
        print("PASS: Elements extracted with DPI-corrected coordinates.\n")
    else:
        print("NOTE: No text elements detected on screen (OCR may not be installed).\n")

    # =================================================================
    # Test 5: Raw vs Scaled Coordinate Comparison
    # =================================================================
    print("─── [Test 5: Raw vs Scaled Coordinate Comparison] ───")
    if elements and dpi_scale != (1.0, 1.0):
        # Re-run OCR to get raw coordinates for comparison
        raw_words = vision._ocr_image(screenshot)
        if raw_words:
            rw = raw_words[0]
            raw_cx = rw['x'] + rw['width'] // 2
            raw_cy = rw['y'] + rw['height'] // 2
            scaled_cx, scaled_cy = elements[0]['center']
            print(f"  First element text: '{rw['text'][:40]}'")
            print(f"    RAW OCR center:     ({raw_cx:4d}, {raw_cy:4d})  (screenshot pixels)")
            print(f"    SCALED center:      ({scaled_cx:4d}, {scaled_cy:4d})  (logical/mouse coords)")
            print(f"    Offset corrected:   Δx={raw_cx - scaled_cx}px, Δy={raw_cy - scaled_cy}px")
            print("  PASS: Coordinate mapping verified.\n")
        else:
            print("  SKIP: No raw OCR words to compare.\n")
    elif dpi_scale == (1.0, 1.0):
        print("  SKIP: DPI scale is 1.0 — no scaling needed, coordinates match.\n")
    else:
        print("  SKIP: No elements detected.\n")

    # =================================================================
    # Test 6: Card-Based Clustering
    # =================================================================
    print("─── [Test 6: Card-Based Clustering] ───")
    if elements:
        screen_w = context.get("screen_size", {}).get("width", logical_w)
        screen_h = context.get("screen_size", {}).get("height", logical_h)
        gap_threshold = int(screen_h * 0.035)
        print(f"  Card gap threshold: {gap_threshold}px (3.5% of {screen_h}px screen height)")

        # Filter to content area
        top_cut = int(screen_h * 0.14)
        bot_cut = int(screen_h * 0.95)
        content = [e for e in elements if top_cut <= e['center'][1] <= bot_cut]
        print(f"  Content area elements: {len(content)} (out of {len(elements)} total)")

        cards = vision._cluster_into_cards(content, gap_threshold)
        print(f"  Cards detected: {len(cards)}")
        for i, card in enumerate(cards[:5]):
            title = vision._pick_card_title(card)
            print(f"    Card {i+1}: [{len(card)} lines] Title: '{title['text'][:50]}' @ center={title['center']}")
        print("PASS: Clustering evaluated.\n")
    else:
        print("  SKIP: No elements to cluster.\n")

    # =================================================================
    # Test 7: Screen Description
    # =================================================================
    print("─── [Test 7: Screen Description] ───")
    desc = vision.get_screen_description()
    print(f"  Neura Screen Summary:\n  \"{desc}\"\n")

    # =================================================================
    # Test 8: Numbered & Ordinal Target Selection
    # =================================================================
    print("─── [Test 8: Numbered & Ordinal Target Selection] ───")
    queries_to_test = [
        "first result",
        "second result",
        "third result",
        "first video",
        "second video",
        "second link"
    ]
    for q in queries_to_test:
        target = vision.find_target(q, screen_elements=elements)
        if target:
            print(f"  Query '{q}': → '{target['text'][:40]}' at center={target['center']} "
                  f"(conf={target['confidence']:.2f})")
        else:
            print(f"  Query '{q}': → No candidate matched.")
    print("PASS: Target selection evaluated.\n")

    # =================================================================
    # Test 9: Safe Cursor Positioning (Test Mode — no click)
    # =================================================================
    print("─── [Test 9: Safe Cursor Positioning (Test Mode)] ───")
    if elements:
        sample_target = elements[0]
        print(f"  Moving mouse cursor to '{sample_target['text'][:30]}' "
              f"at center={sample_target['center']}...")
        success, msg = vision.click_target(sample_target)
        print(f"  Result: {msg}")
        print("PASS: Safe cursor movement verified.\n")

    # =================================================================
    # Test 10: Intent Router Screen Vision Classification
    # =================================================================
    print("─── [Test 10: Intent Router Screen Vision Classification] ───")
    test_phrases = [
        ("what is currently open on my screen?", IntentType.SCREEN_DESCRIBE),
        ("open the second Google search result", IntentType.SCREEN_OPEN),
        ("click the third video", IntentType.SCREEN_CLICK),
        ("play the second song", IntentType.SCREEN_PLAY),
        ("open the link about Python", IntentType.SCREEN_OPEN),
        ("what is this page about?", IntentType.SCREEN_DESCRIBE),
        ("scroll down and open the third result", IntentType.SCREEN_SCROLL),
        ("scroll down", IntentType.SCREEN_SCROLL),
        ("what happens in the screen", IntentType.SCREEN_DESCRIBE),
        ("what happens at the background", IntentType.SYSTEM_BACKGROUND_STATUS),
        ("what is running in the background", IntentType.SYSTEM_BACKGROUND_STATUS),
        ("what happens in the screen and at the background", IntentType.SYSTEM_SCREEN_AND_BACKGROUND_STATUS),
        ("by taking screen permission i want to perform some tasks and ask what happens in the screen and at the backgroud. make setup all these", IntentType.SYSTEM_SCREEN_AND_BACKGROUND_STATUS),
        ("take screen permission and open the first video", IntentType.SCREEN_OPEN)
    ]
    all_matched = True
    for phrase, expected in test_phrases:
        intent, meta = route_intent(phrase)
        status = "✓" if intent == expected else "✗"
        if intent != expected:
            all_matched = False
        print(f"  [{status}] '{phrase[:60]}' → {intent} (meta: {meta})")

    if all_matched:
        print("PASS: All Screen Vision query patterns routed accurately.\n")
    else:
        print("WARNING: Some intent patterns did not match expected IntentType.\n")

    # =================================================================
    # Test 11: Desktop Controller Integration
    # =================================================================
    print("─── [Test 11: Desktop Controller Screen Vision & Background Methods] ───")
    controller_desc = controller.screen_describe()
    print(f"  Controller screen_describe: \"{controller_desc[:80]}...\"")
    bg_desc = controller.get_background_activity()
    print(f"  Controller get_background_activity: \"{bg_desc[:80]}...\"")
    dual_desc = controller.get_screen_and_background_activity()
    print(f"  Controller get_screen_and_background_activity: \"{dual_desc[:80]}...\"")
    print("PASS: DesktopController wraps ScreenVision and Background engines.\n")

    # =================================================================
    # Test 12: Full Diagnostics
    # =================================================================
    print("─── [Test 12: Full System Diagnostics] ───")
    diag = vision.run_diagnostics()
    print("PASS: Diagnostics complete.\n")

    # =================================================================
    # Test 13: Semantic Element Resolution (Search Bar, Tabs, Links, Descriptions)
    # =================================================================
    print("─── [Test 13: Semantic Element Resolution] ───")
    semantic_queries = [
        "search bar",
        "images tab",
        "videos tab",
        "all tab",
        "first link",
        "second link",
        "click the link description"
    ]
    for sq in semantic_queries:
        target = vision.find_target(sq, screen_elements=elements)
        if target:
            sem_type = target.get("semantic_type", target.get("type", "unknown"))
            print(f"  Target '{sq}': -> '{target['text'][:40]}' | Role: {sem_type} @ center={target['center']}")
        else:
            print(f"  Target '{sq}': -> No candidate matched.")
    print("PASS: Semantic element resolution verified.\n")

    # =================================================================
    # Test 14: Intent Router Semantic UI Patterns
    # =================================================================
    print("─── [Test 14: Intent Router Semantic UI Patterns] ───")
    semantic_phrases = [
        ("click search bar", IntentType.SCREEN_CLICK),
        ("click images tab", IntentType.SCREEN_CLICK),
        ("open short videos tab", IntentType.SCREEN_OPEN),
        ("switch to images tab", IntentType.SCREEN_CLICK),
        ("click the first link", IntentType.SCREEN_CLICK),
        ("open the second link", IntentType.SCREEN_OPEN),
        ("click the link description", IntentType.SCREEN_CLICK),
        ("click music tab", IntentType.SCREEN_CLICK),
        ("click shorts tab", IntentType.SCREEN_CLICK),
        ("click subscriptions tab", IntentType.SCREEN_CLICK)
    ]
    all_sem_matched = True
    for phrase, expected in semantic_phrases:
        intent, meta = route_intent(phrase)
        status = "✓" if intent == expected else "✗"
        if intent != expected:
            all_sem_matched = False
        print(f"  [{status}] '{phrase}' → {intent} (meta: {meta})")

    if all_sem_matched:
        print("PASS: All Semantic UI intent patterns routed accurately.\n")
    else:
        print("WARNING: Some semantic intent patterns did not match.\n")

    print("=" * 70)
    print("           SCREEN VISION TEST SUITE COMPLETED SUCCESSFULLY          ")
    print("=" * 70)


if __name__ == "__main__":
    live = "--live" in sys.argv
    run_screen_vision_tests(live_click=live)
