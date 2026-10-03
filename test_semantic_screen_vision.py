"""
Unit Test: Semantic Screen Vision (Google Search & YouTube UI Understanding)
Tests element classification, search bar targeting, tab selection, link titles vs descriptions.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from brain.screen_vision import ScreenVision

def test_google_search_semantics():
    print("=" * 60)
    print("  TEST 1: GOOGLE SEARCH SEMANTIC LAYOUT UNDERSTANDING")
    print("=" * 60)

    vision = ScreenVision(test_mode=True)
    screen_w, screen_h = 1920, 1080

    # Mock OCR elements from Google Search (matching user's screenshot)
    # y=90-110: Search bar with "rohit adak"
    # y=142: Tabs row: AI Mode, All, Images, Videos, News, Forums, Short videos, More, Tools
    # y=200+: Search result cards
    mock_elements = [
        # Search bar area
        {"id": 1, "type": "text", "text": "Google", "bbox": [150, 85, 230, 115], "center": [190, 100], "confidence": 0.95, "width": 80, "height": 30},
        {"id": 2, "type": "text", "text": "rohit adak", "bbox": [280, 85, 600, 115], "center": [440, 100], "confidence": 0.95, "width": 320, "height": 30},

        # Tabs row (y ≈ 142)
        {"id": 3, "type": "text", "text": "AI Mode", "bbox": [150, 135, 210, 155], "center": [180, 145], "confidence": 0.95, "width": 60, "height": 20},
        {"id": 4, "type": "text", "text": "All", "bbox": [225, 135, 255, 155], "center": [240, 145], "confidence": 0.95, "width": 30, "height": 20},
        {"id": 5, "type": "text", "text": "Images", "bbox": [270, 135, 330, 155], "center": [300, 145], "confidence": 0.95, "width": 60, "height": 20},
        {"id": 6, "type": "text", "text": "Videos", "bbox": [345, 135, 400, 155], "center": [372, 145], "confidence": 0.95, "width": 55, "height": 20},
        {"id": 7, "type": "text", "text": "News", "bbox": [415, 135, 460, 155], "center": [437, 145], "confidence": 0.95, "width": 45, "height": 20},
        {"id": 8, "type": "text", "text": "Forums", "bbox": [475, 135, 535, 155], "center": [505, 145], "confidence": 0.95, "width": 60, "height": 20},
        {"id": 9, "type": "text", "text": "Short videos", "bbox": [550, 135, 640, 155], "center": [595, 145], "confidence": 0.95, "width": 90, "height": 20},
        {"id": 10, "type": "text", "text": "More", "bbox": [655, 135, 700, 155], "center": [677, 145], "confidence": 0.95, "width": 45, "height": 20},
        {"id": 11, "type": "text", "text": "Tools", "bbox": [715, 135, 760, 155], "center": [737, 145], "confidence": 0.95, "width": 45, "height": 20},

        # Result Card 1 (LinkedIn)
        {"id": 12, "type": "text", "text": "linkedin.com > in > rohit-adak", "bbox": [150, 210, 360, 225], "center": [255, 217], "confidence": 0.95, "width": 210, "height": 15},
        {"id": 13, "type": "text", "text": "Rohit Adak - Software Engineer - Tech Mahindra | LinkedIn", "bbox": [150, 235, 650, 260], "center": [400, 247], "confidence": 0.95, "width": 500, "height": 25},
        {"id": 14, "type": "text", "text": "View Rohit Adak's profile on LinkedIn, a professional community of 1 billion members.", "bbox": [150, 265, 750, 290], "center": [450, 277], "confidence": 0.95, "width": 600, "height": 25},

        # Result Card 2 (Instagram / Reel)
        {"id": 15, "type": "text", "text": "instagram.com > rohit_adak", "bbox": [150, 340, 340, 355], "center": [245, 347], "confidence": 0.95, "width": 190, "height": 15},
        {"id": 16, "type": "text", "text": "Rohit Adak (@rohit_adak) - Instagram photos and videos", "bbox": [150, 365, 620, 390], "center": [385, 377], "confidence": 0.95, "width": 470, "height": 25},
        {"id": 17, "type": "text", "text": "Explore photos, reels, and stories shared by Rohit Adak on Instagram.", "bbox": [150, 395, 700, 420], "center": [425, 407], "confidence": 0.95, "width": 550, "height": 25}
    ]

    # Run semantic classification
    classified = vision._classify_elements_semantically(mock_elements, "google_search", screen_w, screen_h)

    # 1. Verify Search Bar
    sb_elem = vision.find_target("search bar", screen_elements=classified)
    assert sb_elem is not None, "Search bar not found"
    assert "rohit adak" in sb_elem["text"] or "Google" in sb_elem["text"], f"Unexpected search bar text: {sb_elem['text']}"
    print(f"  [PASS] Search Bar detected: '{sb_elem['text']}' @ {sb_elem['center']}")

    # 2. Verify Specific Tabs
    tabs_to_test = ["Images", "Videos", "Short videos", "All", "AI Mode", "News", "Tools"]
    for tab_name in tabs_to_test:
        tab_elem = vision.find_target(f"{tab_name} tab", screen_elements=classified)
        assert tab_elem is not None, f"Tab '{tab_name}' not found"
        assert tab_name.lower() in tab_elem["text"].lower(), f"Expected '{tab_name}', got '{tab_elem['text']}'"
        print(f"  [PASS] Tab '{tab_name}' located: center={tab_elem['center']}")

    # 3. Verify Links vs Descriptions Separation
    # First Link MUST be the Title, NOT the description or URL
    link1 = vision.find_target("first link", screen_elements=classified)
    assert link1 is not None, "First link not found"
    assert "Rohit Adak - Software Engineer" in link1["text"], f"First link should be title, got: '{link1['text']}'"
    print(f"  [PASS] First Link Title correctly identified: '{link1['text'][:45]}'")

    # Second Link MUST be Card 2's Title
    link2 = vision.find_target("second link", screen_elements=classified)
    assert link2 is not None, "Second link not found"
    assert "Instagram photos and videos" in link2["text"], f"Second link should be card 2 title, got: '{link2['text']}'"
    print(f"  [PASS] Second Link Title correctly identified: '{link2['text'][:45]}'")

    # Link Description MUST be the Description snippet, NOT the title
    desc1 = vision.find_target("click the link description", screen_elements=classified)
    assert desc1 is not None, "Link description not found"
    assert "View Rohit Adak's profile" in desc1["text"], f"Expected snippet description, got: '{desc1['text']}'"
    print(f"  [PASS] First Link Description correctly isolated: '{desc1['text'][:45]}'")

    # Description of 2nd result
    desc2 = vision.find_target("description of second link", screen_elements=classified)
    assert desc2 is not None, "Second link description not found"
    assert "Explore photos, reels" in desc2["text"], f"Expected card 2 snippet, got: '{desc2['text']}'"
    print(f"  [PASS] Second Link Description correctly isolated: '{desc2['text'][:45]}'")


def test_youtube_semantics():
    print("\n" + "=" * 60)
    print("  TEST 2: YOUTUBE SEMANTIC LAYOUT UNDERSTANDING")
    print("=" * 60)

    vision = ScreenVision(test_mode=True)
    screen_w, screen_h = 1920, 1080

    mock_yt_elements = [
        # Search bar
        {"id": 1, "type": "text", "text": "Search", "bbox": [400, 45, 900, 80], "center": [650, 62], "confidence": 0.95, "width": 500, "height": 35},

        # Horizontal Filter Chips (y ≈ 110)
        {"id": 2, "type": "text", "text": "All", "bbox": [250, 100, 290, 125], "center": [270, 112], "confidence": 0.95, "width": 40, "height": 25},
        {"id": 3, "type": "text", "text": "Music", "bbox": [310, 100, 370, 125], "center": [340, 112], "confidence": 0.95, "width": 60, "height": 25},
        {"id": 4, "type": "text", "text": "Podcasts", "bbox": [390, 100, 470, 125], "center": [430, 112], "confidence": 0.95, "width": 80, "height": 25},

        # Left Sidebar Navigation (x < 15%)
        {"id": 5, "type": "text", "text": "Home", "bbox": [20, 100, 80, 125], "center": [50, 112], "confidence": 0.95, "width": 60, "height": 25},
        {"id": 6, "type": "text", "text": "Shorts", "bbox": [20, 145, 80, 170], "center": [50, 157], "confidence": 0.95, "width": 60, "height": 25},
        {"id": 7, "type": "text", "text": "Subscriptions", "bbox": [20, 190, 120, 215], "center": [70, 202], "confidence": 0.95, "width": 100, "height": 25},

        # Video Card 1
        {"id": 8, "type": "timestamp", "text": "4:15", "bbox": [250, 220, 290, 235], "center": [270, 227], "confidence": 0.95, "width": 40, "height": 15},
        {"id": 9, "type": "text", "text": "MAJHEY MAJHEY TOBO - Official Bengali Song Video", "bbox": [550, 220, 1100, 250], "center": [825, 235], "confidence": 0.95, "width": 550, "height": 30},
        {"id": 10, "type": "text", "text": "SVF Music", "bbox": [550, 255, 650, 275], "center": [600, 265], "confidence": 0.95, "width": 100, "height": 20},
        {"id": 11, "type": "metadata", "text": "12M views • 3 years ago", "bbox": [550, 280, 750, 300], "center": [650, 290], "confidence": 0.95, "width": 200, "height": 20},

        # Video Card 2
        {"id": 12, "type": "timestamp", "text": "5:30", "bbox": [250, 360, 290, 375], "center": [270, 367], "confidence": 0.95, "width": 40, "height": 15},
        {"id": 13, "type": "text", "text": "Rimjhim E Dhara Te - Premer Kahini Romantic Track", "bbox": [550, 360, 1080, 390], "center": [815, 375], "confidence": 0.95, "width": 530, "height": 30},
        {"id": 14, "type": "text", "text": "Zee Music Bangla", "bbox": [550, 395, 700, 415], "center": [625, 405], "confidence": 0.95, "width": 150, "height": 20},
        {"id": 15, "type": "metadata", "text": "8.5M views • 1 year ago", "bbox": [550, 420, 740, 440], "center": [645, 430], "confidence": 0.95, "width": 190, "height": 20}
    ]

    # Run semantic classification
    classified = vision._classify_elements_semantically(mock_yt_elements, "youtube", screen_w, screen_h)

    # 1. YouTube Search Bar
    sb_elem = vision.find_target("search bar", screen_elements=classified)
    assert sb_elem is not None, "YouTube search bar not found"
    assert "Search" in sb_elem["text"], f"Expected 'Search', got: {sb_elem['text']}"
    print(f"  [PASS] YouTube Search Bar detected @ {sb_elem['center']}")

    # 2. YouTube Chips & Sidebar Tabs
    music_chip = vision.find_target("music tab", screen_elements=classified)
    assert music_chip is not None and "Music" in music_chip["text"], f"Music chip error: {music_chip}"
    print(f"  [PASS] YouTube Music Chip located @ {music_chip['center']}")

    shorts_tab = vision.find_target("shorts tab", screen_elements=classified)
    assert shorts_tab is not None and "Shorts" in shorts_tab["text"], f"Shorts tab error: {shorts_tab}"
    print(f"  [PASS] YouTube Shorts Nav Tab located @ {shorts_tab['center']}")

    subs_tab = vision.find_target("subscriptions tab", screen_elements=classified)
    assert subs_tab is not None and "Subscriptions" in subs_tab["text"], f"Subs tab error: {subs_tab}"
    print(f"  [PASS] YouTube Subscriptions Nav Tab located @ {subs_tab['center']}")

    # 3. Video Title targeting (MUST pick the video title, NOT channel name or views!)
    vid1 = vision.find_target("first video", screen_elements=classified)
    assert vid1 is not None, "First video not found"
    assert "MAJHEY MAJHEY TOBO" in vid1["text"], f"First video should be title, got: {vid1['text']}"
    assert "SVF Music" not in vid1["text"], "First video selected channel name instead of title!"
    print(f"  [PASS] Video #1 Title correctly selected: '{vid1['text'][:45]}'")

    vid2 = vision.find_target("second video", screen_elements=classified)
    assert vid2 is not None, "Second video not found"
    assert "Rimjhim E Dhara Te" in vid2["text"], f"Second video should be title, got: {vid2['text']}"
    print(f"  [PASS] Video #2 Title correctly selected: '{vid2['text'][:45]}'")

    print("\nALL SEMANTIC LAYOUT & CLICK TARGETING TESTS PASSED!")

if __name__ == "__main__":
    test_google_search_semantics()
    test_youtube_semantics()
