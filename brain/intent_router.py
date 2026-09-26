"""
Intent Router for Neura AI.
Classifies user queries into System Actions, Memory Operations, External Lookups, or Conversational Queries.
"""

import re
from typing import Tuple, Dict, Any

class IntentType:
    EXIT = "EXIT"
    SYSTEM_VOLUME = "SYSTEM_VOLUME"
    SYSTEM_BRIGHTNESS = "SYSTEM_BRIGHTNESS"
    SYSTEM_CAMERA = "SYSTEM_CAMERA"
    VISION_FACE_RECOGNIZE = "VISION_FACE_RECOGNIZE"
    SYSTEM_APP_OPEN = "SYSTEM_APP_OPEN"
    SYSTEM_APP_CLOSE = "SYSTEM_APP_CLOSE"
    SYSTEM_NOTES = "SYSTEM_NOTES"
    SYSTEM_REMINDER = "SYSTEM_REMINDER"
    SYSTEM_MEDIA = "SYSTEM_MEDIA"
    SYSTEM_JOKE = "SYSTEM_JOKE"
    
    MEMORY_CLEAR = "MEMORY_CLEAR"
    MEMORY_INSPECT = "MEMORY_INSPECT"
    MEMORY_RESET_CONVERSATION = "MEMORY_RESET_CONVERSATION"

    LOOKUP_WIKIPEDIA = "LOOKUP_WIKIPEDIA"
    LOOKUP_SEARCH = "LOOKUP_SEARCH"
    LOOKUP_WEATHER = "LOOKUP_WEATHER"

    MOOD_SUPPORT = "MOOD_SUPPORT"
    
    # Desktop Automation
    DESKTOP_SEARCH_IN_TAB = "DESKTOP_SEARCH_IN_TAB"
    DESKTOP_TYPE = "DESKTOP_TYPE"
    DESKTOP_HOTKEY = "DESKTOP_HOTKEY"
    DESKTOP_FIRST_LINK = "DESKTOP_FIRST_LINK"
    DESKTOP_SCREENSHOT = "DESKTOP_SCREENSHOT"

    # File CRUD Operations
    FILE_CREATE = "FILE_CREATE"
    FILE_READ = "FILE_READ"
    FILE_UPDATE = "FILE_UPDATE"
    FILE_DELETE = "FILE_DELETE"
    FILE_LIST = "FILE_LIST"

    CONVERSATION = "CONVERSATION"

def route_intent(query: str) -> Tuple[str, Dict[str, Any]]:
    """
    Analyzes raw input text and returns (IntentType, metadata_dict).
    """
    q = query.strip().lower()
    if not q:
        return IntentType.CONVERSATION, {}

    # Exit
    if any(phrase in q for phrase in ['good bye', 'goodbye', 'exit', 'bye', 'quit', 'good night']):
        return IntentType.EXIT, {}

    # Emotional State / Mood Support (when not asking for a specific command like joke or music directly)
    if any(m in q for m in ['bored', 'feeling bored', 'i am bored', "i'm bored", 'feeling tired', 'i am tired', 'feeling sad', 'i am sad', 'feeling stressed']):
        if not any(k in q for k in ['joke', 'music', 'song', 'play']):
            mood = "bored"
            if "tired" in q:
                mood = "tired"
            elif "sad" in q:
                mood = "sad"
            elif "stressed" in q:
                mood = "stressed"
            return IntentType.MOOD_SUPPORT, {"mood": mood}

    # Memory operations
    if any(phrase in q for phrase in ['clear memory', 'reset memory', 'wipe memory', 'forget everything']):
        return IntentType.MEMORY_CLEAR, {}

    if any(phrase in q for phrase in ['what do you know about me', 'show my memory', 'what are my preferences', 'my profile']):
        return IntentType.MEMORY_INSPECT, {}

    # Clear conversation
    if any(phrase in q for phrase in ['clear conversation', 'reset conversation', 'clear chat', 'new chat']):
        return IntentType.MEMORY_RESET_CONVERSATION, {}

    # Desktop Automation - Screenshot
    if any(s in q for s in ['take a screenshot', 'take screenshot', 'capture screen', 'screenshot']):
        return IntentType.DESKTOP_SCREENSHOT, {}

    # Desktop Automation - Open First Link / Search Result
    if any(f in q for f in ['open the first link', 'click the first link', 'open first link', 'click first link', 'first link', 'first video', 'play the first video', 'first result']):
        return IntentType.DESKTOP_FIRST_LINK, {}

    # Desktop Automation - Search In Active Tab (e.g. YouTube tab, browser tab, or active app)
    in_tab_patterns = [
        r"(?:search on youtube|search in youtube|search youtube for|search youtube)\s+(?:for\s+)?(.+)",
        r"(?:search on this tab|search in this tab|search on their|search on there|search here)\s+(?:for\s+)?(.+)",
        r"(?:search this tab for|search tab for)\s+(.+)",
        r"search\s+(.+?)\s+(?:on youtube|in youtube|on this tab|in this tab|on there|on their|here)$",
    ]
    for pattern in in_tab_patterns:
        match = re.search(pattern, q)
        if match:
            term = match.group(1).strip()
            return IntentType.DESKTOP_SEARCH_IN_TAB, {"query": term}

    # Desktop Automation - Hotkeys & Window Navigation
    hotkey_keywords = {
        'new tab': 'new tab',
        'open a new tab': 'new tab',
        'close tab': 'close tab',
        'close this tab': 'close tab',
        'switch tab': 'switch tab',
        'next tab': 'switch tab',
        'previous tab': 'previous tab',
        'scroll down': 'scroll down',
        'page down': 'scroll down',
        'scroll up': 'scroll up',
        'page up': 'scroll up',
        'press enter': 'enter',
        'hit enter': 'enter',
        'select all': 'select all',
        'copy this': 'copy',
        'copy text': 'copy',
        'paste this': 'paste',
        'paste text': 'paste',
        'save this': 'save',
        'save file': 'save',
        'refresh page': 'refresh',
        'reload page': 'refresh',
        'maximize window': 'maximize',
        'minimize window': 'minimize'
    }
    for hk_phrase, hk_action in hotkey_keywords.items():
        if hk_phrase in q:
            return IntentType.DESKTOP_HOTKEY, {"action": hk_action}

    # Desktop Automation - Direct Typing at Cursor
    type_match = re.search(r"^(?:type|write at cursor|type this|write)\s+(.+)", query, re.IGNORECASE)
    if type_match and not any(w in q for w in ["note", "file", "folder", "email"]):
        extracted = type_match.group(1).strip()
        return IntentType.DESKTOP_TYPE, {"text": extracted}

    # File CRUD Operations
    # 1. Create File / Folder
    create_folder_match = re.search(r"(?:create folder|make folder|new folder)\s+([a-zA-Z0-9_\-\.\s/\\]+)", query, re.IGNORECASE)
    if create_folder_match:
        return IntentType.FILE_CREATE, {"type": "folder", "path": create_folder_match.group(1).strip()}

    create_file_match = re.search(r"(?:create file|make file|new file)\s+([a-zA-Z0-9_\-\.\s/\\]+?)(?:\s+with content\s+(.*)|\s+with\s+(.*))?$", query, re.IGNORECASE)
    if create_file_match:
        fpath = create_file_match.group(1).strip()
        fcontent = (create_file_match.group(2) or create_file_match.group(3) or "").strip()
        return IntentType.FILE_CREATE, {"type": "file", "path": fpath, "content": fcontent}

    # 2. Read File
    read_file_match = re.search(r"(?:read file|show file|open file|view file|what is in file)\s+([a-zA-Z0-9_\-\.\s/\\]+)", query, re.IGNORECASE)
    if read_file_match and not any(w in q for w in ["note", "camera", "app"]):
        return IntentType.FILE_READ, {"path": read_file_match.group(1).strip()}

    # 3. Update / Append File
    append_file_match = re.search(r"(?:append to file|write to file|add to file)\s+([a-zA-Z0-9_\-\.\s/\\]+?)\s+(?:content\s+|text\s+)?(.*)", query, re.IGNORECASE)
    if append_file_match:
        fpath = append_file_match.group(1).strip()
        fcontent = append_file_match.group(2).strip()
        return IntentType.FILE_UPDATE, {"path": fpath, "content": fcontent}

    # 4. Delete File / Folder
    del_folder_match = re.search(r"(?:delete folder|remove folder)\s+([a-zA-Z0-9_\-\.\s/\\]+)", query, re.IGNORECASE)
    if del_folder_match:
        return IntentType.FILE_DELETE, {"type": "folder", "path": del_folder_match.group(1).strip()}

    del_file_match = re.search(r"(?:delete file|remove file)\s+([a-zA-Z0-9_\-\.\s/\\]+)", query, re.IGNORECASE)
    if del_file_match and not any(w in q for w in ["memory", "note"]):
        return IntentType.FILE_DELETE, {"type": "file", "path": del_file_match.group(1).strip()}

    # 5. List Files
    list_files_match = re.search(r"(?:list files|show files|explore folder|show directory)(?:\s+in\s+|\s+on\s+)?(.*)?", query, re.IGNORECASE)
    if list_files_match and ('list' in q or 'show files' in q):
        target_f = (list_files_match.group(1) or "").strip()
        return IntentType.FILE_LIST, {"path": target_f}

    # System controls - Volume
    if any(v in q for v in ['volume up', 'increase volume', 'louder']):
        return IntentType.SYSTEM_VOLUME, {"action": "up"}
    if any(v in q for v in ['volume down', 'decrease volume', 'lower volume', 'softer']):
        return IntentType.SYSTEM_VOLUME, {"action": "down"}
    if any(v in q for v in ['mute volume', 'mute', 'unmute']):
        return IntentType.SYSTEM_VOLUME, {"action": "toggle_mute"}
    if 'volume' in q:
        numbers = re.findall(r'\d+', q)
        if numbers:
            return IntentType.SYSTEM_VOLUME, {"action": "set", "level": int(numbers[0])}
        return IntentType.SYSTEM_VOLUME, {"action": "ask_level"}

    # System controls - Brightness
    if any(b in q for b in ['brightness up', 'increase brightness', 'brighter']):
        return IntentType.SYSTEM_BRIGHTNESS, {"action": "up"}
    if any(b in q for b in ['brightness down', 'decrease brightness', 'dimmer']):
        return IntentType.SYSTEM_BRIGHTNESS, {"action": "down"}
    if 'brightness' in q:
        numbers = re.findall(r'\d+', q)
        if numbers:
            return IntentType.SYSTEM_BRIGHTNESS, {"action": "set", "level": int(numbers[0])}
        return IntentType.SYSTEM_BRIGHTNESS, {"action": "ask_level"}

    # Vision / Face Recognition
    if any(phrase in q for phrase in [
        'recognize face', 'recognize my face', 'face recognition', 'scan my face',
        'scan face', 'verify face', 'verify my identity', 'verify identity',
        'who is in front of the camera', 'who is at the camera', 'who is in camera',
        'look at me', 'who am i', 'identify me', 'identify face'
    ]):
        return IntentType.VISION_FACE_RECOGNIZE, {}

    # Camera
    if any(c in q for c in ['camera', 'open camera', 'webcam', 'take photo']):
        return IntentType.SYSTEM_CAMERA, {}

    # Application management
    if 'close outlook' in q or 'close mail' in q:
        return IntentType.SYSTEM_APP_CLOSE, {"app_name": "outlook"}
    if q.startswith('close ') or ' close ' in q:
        app_target = q.split('close', 1)[1].strip()
        return IntentType.SYSTEM_APP_CLOSE, {"app_name": app_target}

    if q.startswith('open ') or q.startswith('launch '):
        app_target = q.replace('launch', '').replace('open', '').strip()
        # Ensure it's not "open camera" (already handled above)
        if app_target != "camera":
            return IntentType.SYSTEM_APP_OPEN, {"app_name": app_target}

    # Notes
    if any(n in q for n in ['take a note', 'write a note', 'make a note', 'save a note']):
        return IntentType.SYSTEM_NOTES, {"action": "write"}
    if any(n in q for n in ['read note', 'show note', 'check note', 'read notes']):
        return IntentType.SYSTEM_NOTES, {"action": "read"}

    # Reminders
    if any(r in q for r in ['set a reminder', 'set reminder', 'remind me', 'add reminder']):
        return IntentType.SYSTEM_REMINDER, {}

    # Media controls
    if any(m in q for m in ['pause song', 'pause video', 'pause music', 'resume music', 'pause or resume', 'pause media']):
        return IntentType.SYSTEM_MEDIA, {"action": "play_pause"}
    if any(m in q for m in ['next song', 'next track', 'skip song', 'next media']):
        return IntentType.SYSTEM_MEDIA, {"action": "next"}
    if any(m in q for m in ['previous song', 'last song', 'previous track', 'previous media']):
        return IntentType.SYSTEM_MEDIA, {"action": "previous"}
    if any(m in q for m in ['what song is playing', 'media status', 'check media']):
        return IntentType.SYSTEM_MEDIA, {"action": "status"}

    # Jokes
    if 'joke' in q or 'jokes' in q:
        return IntentType.SYSTEM_JOKE, {}

    # Lookups - Wikipedia
    if 'wikipedia' in q:
        target = q.replace('wikipedia', '').strip()
        return IntentType.LOOKUP_WIKIPEDIA, {"query": target}
    if q.startswith('who is ') or q.startswith('what is ') or q.startswith('about '):
        # Could be quick wikipedia lookup if short query, or conversational
        words = q.split()
        if len(words) <= 5:
            # Let wikipedia or conversation handle
            target = q.replace('who is', '').replace('what is', '').replace('about', '').strip()
            return IntentType.LOOKUP_WIKIPEDIA, {"query": target}

    # Lookups - Search
    if q.startswith('search ') or q.startswith('find ') or 'google ' in q:
        search_target = q.replace('search for', '').replace('search', '').replace('find', '').replace('google', '').strip()
        return IntentType.LOOKUP_SEARCH, {"query": search_target}

    # Lookups - Weather
    if 'weather' in q:
        return IntentType.LOOKUP_WEATHER, {}

    # Default to LLM Brain / Conversation
    return IntentType.CONVERSATION, {}
