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
    SYSTEM_ALERT_SET = "SYSTEM_ALERT_SET"
    SYSTEM_ALERT_LIST = "SYSTEM_ALERT_LIST"
    SYSTEM_ALERT_CANCEL = "SYSTEM_ALERT_CANCEL"
    SYSTEM_ALERT_STOP = "SYSTEM_ALERT_STOP"
    SYSTEM_MEDIA = "SYSTEM_MEDIA"
    SYSTEM_YOUTUBE_PLAY = "SYSTEM_YOUTUBE_PLAY"
    SYSTEM_YOUTUBE_SEARCH = "SYSTEM_YOUTUBE_SEARCH"
    SYSTEM_NETWORK_SPEED = "SYSTEM_NETWORK_SPEED"
    SYSTEM_CONDITION = "SYSTEM_CONDITION"
    SYSTEM_FOLDER_OPEN = "SYSTEM_FOLDER_OPEN"
    SYSTEM_FILE_OPEN = "SYSTEM_FILE_OPEN"
    SYSTEM_JOKE = "SYSTEM_JOKE"
    SYSTEM_PERMISSION = "SYSTEM_PERMISSION"
    SYSTEM_BACKGROUND_STATUS = "SYSTEM_BACKGROUND_STATUS"
    SYSTEM_SCREEN_AND_BACKGROUND_STATUS = "SYSTEM_SCREEN_AND_BACKGROUND_STATUS"
    
    MEMORY_CLEAR = "MEMORY_CLEAR"
    MEMORY_INSPECT = "MEMORY_INSPECT"
    MEMORY_RESET_CONVERSATION = "MEMORY_RESET_CONVERSATION"
    MEMORY_REMEMBER = "MEMORY_REMEMBER"
    MEMORY_CONTEXT_QUERY = "MEMORY_CONTEXT_QUERY"

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

    # Screen Vision
    SCREEN_DESCRIBE = "SCREEN_DESCRIBE"
    SCREEN_CLICK = "SCREEN_CLICK"
    SCREEN_OPEN = "SCREEN_OPEN"
    SCREEN_PLAY = "SCREEN_PLAY"
    SCREEN_SCROLL = "SCREEN_SCROLL"
    SCREEN_TYPE = "SCREEN_TYPE"
    SCREEN_SEARCH = "SCREEN_SEARCH"
    SCREEN_INTERACT = "SCREEN_INTERACT"

    # File CRUD Operations
    FILE_CREATE = "FILE_CREATE"
    FILE_READ = "FILE_READ"
    FILE_UPDATE = "FILE_UPDATE"
    FILE_DELETE = "FILE_DELETE"
    FILE_LIST = "FILE_LIST"

    # Multi-Agent Orchestration
    AGENT_PROJECT_TEST = "AGENT_PROJECT_TEST"
    AGENT_PROJECT_DIAGNOSTIC = "AGENT_PROJECT_DIAGNOSTIC"
    AGENT_MONITOR_START = "AGENT_MONITOR_START"
    AGENT_MONITOR_STOP = "AGENT_MONITOR_STOP"
    AGENT_STATUS = "AGENT_STATUS"
    AGENT_SKILL_LEARN = "AGENT_SKILL_LEARN"
    AGENT_SKILL_RUN = "AGENT_SKILL_RUN"
    AGENT_SCREEN_INSPECT = "AGENT_SCREEN_INSPECT"
    AGENT_OFFICE_SHOW = "AGENT_OFFICE_SHOW"
    AGENT_OFFICE_CLOSE = "AGENT_OFFICE_CLOSE"
    AGENT_COMPUTER_USE = "AGENT_COMPUTER_USE"
    AGENT_VULNERABILITY_SCAN = "AGENT_VULNERABILITY_SCAN"
    AGENT_ERROR_AUDIT = "AGENT_ERROR_AUDIT"
    AGENT_FULL_AUDIT_REPORT = "AGENT_FULL_AUDIT_REPORT"

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

    # 0. Compound Screen / Background Permission with Task or Follow-up Action
    # e.g., "by taking screen permission i want to perform some tasks and ask what happens in the screen and at the backgroud. make setup all these"
    # or "take screen permission and tell me what is on the screen"
    # or "with screen permission click the first link"
    perm_compound_match = re.search(
        r"^(?:by\s+)?(?:taking|take|grant|granting|allow|allowing|enable|enabling|give|giving|with|after\s+taking)\s+(?:the\s+)?(?:screen\s+and\s+background\s+permission[s]?|background\s+and\s+screen\s+permission[s]?|screen\s+permission[s]?|background\s+permission[s]?|screen\s+access|background\s+access|permission[s]?\s+for\s+screen(?:\s+and\s+background)?)\s*(?:[,;]|\s+and|\s+then|\s+to|\s+i\s+want\s+to|\s+please)?\s*(.*)$",
        q,
        re.IGNORECASE
    )
    if perm_compound_match:
        remainder = perm_compound_match.group(1).strip()
        remainder_cleaned = re.sub(
            r"^(?:and\s+|then\s+|to\s+|i\s+want\s+to\s+(?:perform\s+some\s+tasks\s+and\s+)?|i\s+want\s+to\s+|perform\s+some\s+tasks\s+and\s+|please\s+|ask\s+)+",
            "",
            remainder,
            flags=re.IGNORECASE
        ).strip()
        remainder_cleaned = re.sub(r"[,\.]?\s*make\s+setup\s+all\s+(?:of\s+)?these.*$", "", remainder_cleaned, flags=re.IGNORECASE).strip()
        if remainder_cleaned:
            sub_intent, sub_meta = route_intent(remainder_cleaned)
            sub_meta["permission_granted"] = True
            return sub_intent, sub_meta

    # 3D Agent Visualization / Virtual Office Display & Close (Switches Neura Optics Camera View)
    if any(p in q for p in [
        'show 3d visualization', 'show 3d visual', 'open 3d visualization', 'open 3d visual',
        'show 3d visualisation', 'open 3d visualisation', 'show the 3d visualisation',
        'show 3d office', 'open 3d office', 'show the 3d office', 'open the 3d office',
        'show agent visualization', 'open agent visualization', 'show agent office', 'open agent office',
        'show agent visualisation', 'open agent visualisation',
        'show the 3d visualization', 'open the 3d visualization',
        'show 3d visualization of the agent works', 'show 3d visualization of the agent work',
        'show 3d visualisation of the agent works', 'show 3d visualisation of the agent work',
        'show 3d visualization of agent works', 'show 3d visualization of agent',
        'show 3d visualisation of agent works', 'show 3d visualisation of agent',
        'show agent visualizer', 'open agent visualizer',
        '3d visualization of the agent', 'show 3d agent', 'open 3d agent',
        'open agent 3d office', 'show agent 3d office', 'show agent works',
        'visualisation of agents', 'visualization of agents',
        'show me the visualisation', 'show me the visualization'
    ]) or re.search(r"\b(?:show|open|display)\s+(?:me\s+)?(?:the\s+)?(?:3d\s+)?(?:agent\s+)?(?:visuali[sz]ation|visual|office|visualizer)(?:\s+of\s+(?:the\s+)?(?:agent\s+works?|agents?))?\b", q):
        return IntentType.AGENT_OFFICE_SHOW, {}

    if any(p in q for p in [
        'close visualization', 'close the visualization', 'hide visualization',
        'close visualisation', 'close the visualisation', 'hide visualisation',
        'close 3d visualization', 'close 3d visual', 'hide 3d visualization', 'hide 3d visual',
        'close 3d visualisation', 'hide 3d visualisation',
        'close 3d office', 'hide 3d office', 'close the 3d office', 'hide the 3d office',
        'close agent visualization', 'hide agent visualization', 'close agent office', 'hide agent office',
        'close agent visualisation', 'hide agent visualisation',
        'close the 3d visualization', 'hide the 3d visualization',
        'close the 3d visualisation', 'hide the 3d visualisation',
        'close 3d visualization of the agent works', 'close 3d visualizer', 'close agent visualizer',
        'close that one', 'close that', 'show camera', 'switch to camera',
        'close the 3d visual', 'close 3d view', 'close the agent office'
    ]) or re.search(r"\b(?:close|hide|dismiss|shut|exit)\s+(?:the\s+)?(?:3d\s+)?(?:agent\s+)?(?:visuali[sz]ation|visual|office|visualizer)\b", q) \
       or re.search(r"\bclose\s+(?:that\s+one|that|it|visuali[sz]ation|the\s+visuali[sz]ation)\b", q):
        return IntentType.AGENT_OFFICE_CLOSE, {}

    # Multi-Agent Subsystem: Task Status / "What are you doing?"
    if any(phrase in q for phrase in [
        'what are you doing', 'what are you working on', 'what are your active tasks',
        'what tasks are running', 'show active tasks', 'active tasks', 'current tasks',
        'task status', 'agent status', 'show task status', 'what is running'
    ]):
        return IntentType.AGENT_STATUS, {}

    # Multi-Agent Subsystem: Full-Screen Autonomous Computer Use (Gemini & Claude style)
    if any(p in q for p in [
        'take full screen access', 'take full-screen access', 'full screen access',
        'full-screen access', 'computer use', 'take screen access to perform',
        'take screen access and perform', 'screen automation task', 'take full access of the screen',
        'take access of the screen', 'automate task on screen', 'automation task on screen',
        'automation task', 'perform a automation task', 'perform an automation task',
        'perform automation task', 'screen automation'
    ]) or re.search(r"\b(?:take\s+full\s+screen\s+access|take\s+(?:the\s+)?full\s+access\s+of\s+the\s+screen|automate\s+(?:task\s+)?on\s+screen|automation\s+task\s+on\s+screen)\b", q):
        goal = query
        for p in [
            'take full screen access as like gemini or claude does',
            'take full screen access as like gemini or claude',
            'take full screen access and', 'take full screen access to',
            'take full access of the screen and', 'take full access of the screen to',
            'take full screen access', 'take screen access and', 'take screen access to',
            'computer use:', 'computer use'
        ]:
            if p in goal.lower():
                idx = goal.lower().find(p) + len(p)
                sub_goal = goal[idx:].strip(" :,-")
                if sub_goal:
                    goal = sub_goal
                break
        return IntentType.AGENT_COMPUTER_USE, {"goal": goal}

    # Multi-Agent Subsystem: Full Vulnerability & Error Audit with .doc Report Generation
    has_doc_request = any(d in q for d in ['doc file', '.doc file', '.doc', 'doc report', 'report.doc', 'generate doc', 'create doc', 'word file', 'document file'])
    has_dual_audit = ('vulnerabilit' in q and ('error' in q or 'logging' in q or 'audit' in q))

    if has_doc_request or (has_dual_audit and any(r in q for r in ['report', 'doc', 'email', 'voice', 'generate', 'create'])):
        force_email = any(e in q for e in ['email', 'by email', 'via email', 'mail'])
        return IntentType.AGENT_FULL_AUDIT_REPORT, {"force_email": force_email}

    # Multi-Agent Subsystem: Error Logging, Auditing & Diagnostic Interpretation
    if any(p in q for p in [
        'checking the logging, auditing and understanding the errors',
        'checking the logging, auditing and understanding',
        'checking the logging', 'checking logging',
        'audit error logs', 'audit errors', 'audit logging and errors',
        'audit logging and understand errors', 'audit logging', 'understand the errors',
        'understand errors and report', 'understand errors', 'scan error logs',
        'diagnose error logs', 'error log audit', 'system error audit', 'check error logs'
    ]) or re.search(r"\b(?:check|audit|scan|understand)\s+(?:the\s+)?(?:error\s+logs?|logging|exceptions?)\b", q):
        return IntentType.AGENT_ERROR_AUDIT, {}

    # Multi-Agent Subsystem: Automated Project Vulnerability Scanning
    if any(p in q for p in [
        'check vulnerabilities', 'check vulnerability', 'vulnerability scan', 'vulnerability check',
        'checking vulnerabilities', 'security audit', 'scan vulnerabilities', 'check security flaws',
        'scan for vulnerabilities', 'find vulnerabilities', 'major vulnerabilities',
        'tell major vulnerabilities', 'only major vulnerabilities', 'major security vulnerabilities',
        'major vulnerabilities only', 'only the major vulnerabilities'
    ]) or re.search(r"\b(?:check|scan|audit|find|tell|show|report)\s+(?:only\s+)?(?:the\s+)?(?:major\s+)?vulnerabilit\w*\b", q):
        return IntentType.AGENT_VULNERABILITY_SCAN, {}

    # Multi-Agent Subsystem: Comprehensive Project Testing Workflow
    # "Neura, test my project", "test this project", "inspect my project", "run project tests"
    if re.search(r"\b(?:test|inspect|audit|check)\s+(?:my\s+|this\s+|the\s+)?project\b", q) or any(p in q for p in [
        'test my project', 'test this project', 'test the project', 'test project',
        'run project tests', 'run tests on my project', 'inspect project', 'audit project'
    ]):
        return IntentType.AGENT_PROJECT_TEST, {}

    # Multi-Agent Subsystem: Multi-Agent Failure Investigation & Diagnostic
    # "find out why my project is failing", "why is my project crashing", "check what's wrong with my project"
    if any(p in q for p in [
        'why my project is failing', 'why is my project failing', 'find out why my project is failing',
        'why is my project crashing', 'find out why my project crashed', 'diagnose my project',
        'debug my project', "check what's wrong with my project", "check whats wrong with my project",
        'what is wrong with my project', 'investigate project failure'
    ]):
        return IntentType.AGENT_PROJECT_DIAGNOSTIC, {}

    # Multi-Agent Subsystem: Background Process & Task Monitoring
    # "monitor this task", "start my model training and monitor it", "monitor my model training"
    if any(p in q for p in [
        'stop monitoring', 'stop monitor', 'cancel monitoring', 'end monitoring'
    ]):
        return IntentType.AGENT_MONITOR_STOP, {}

    if any(p in q for p in [
        'monitor this task', 'monitor the task', 'monitor my task', 'start monitoring',
        'monitor training', 'monitor my model training', 'monitor this process',
        'monitor background task', 'monitor the process', 'monitor this job'
    ]) or re.search(r"\b(?:start|run)\s+.*?\s+and\s+monitor\s+it\b", q) or re.search(r"\bmonitor\s+(?:this|the|my)?\s*(?:training|process|task|job|build)\b", q):
        cmd = None
        # Extract command if specified, e.g. "start my model training and monitor it"
        if "model training" in q or "training" in q:
            cmd_name = "Model Training"
        else:
            cmd_name = "Background Task"
        return IntentType.AGENT_MONITOR_START, {"name": cmd_name}

    # Multi-Agent Subsystem: Reusable Skill Learning
    # "learn this workflow", "learn this skill", "create a skill for"
    if any(p in q for p in [
        'learn this workflow', 'learn the workflow', 'learn workflow',
        'learn this skill', 'learn repetitive workflow', 'learn repeated workflow',
        'create a skill for', 'learn a skill'
    ]):
        skill_name_match = re.search(r"(?:for|named|called)\s+([a-zA-Z0-9_\-\s]+)$", q)
        skill_name = skill_name_match.group(1).strip() if skill_name_match else "learned_workflow"
        return IntentType.AGENT_SKILL_LEARN, {"name": skill_name}

    if any(p in q for p in ['run skill', 'execute skill', 'start skill']):
        skill_name_match = re.search(r"(?:skill)\s+([a-zA-Z0-9_\-]+)$", q)
        skill_name = skill_name_match.group(1).strip() if skill_name_match else ""
        return IntentType.AGENT_SKILL_RUN, {"name": skill_name}

    # Multi-Agent Subsystem: Visual Screen and Terminal Error Inspection
    if any(p in q for p in [
        'inspect screen errors', 'check terminal errors', 'check screen for errors',
        "what's wrong on my screen", 'what is wrong on my screen', 'scan screen for errors'
    ]):
        return IntentType.AGENT_SCREEN_INSPECT, {}

    # Dual Screen and Background Activity Inspection
    has_screen_kw = any(w in q for w in ['screen', 'display', 'desktop', 'monitor', 'foreground'])
    has_bg_kw = any(w in q for w in ['background', 'backgroud', 'back ground'])
    if (has_screen_kw and has_bg_kw) or any(phrase in q for phrase in [
        'screen and background', 'background and screen',
        'what happens in the screen and at the background',
        'what is happening in the screen and at the background',
        'what happens on the screen and in the background',
        'what is happening on screen and in the background',
        'what happens on screen and at the background'
    ]):
        return IntentType.SYSTEM_SCREEN_AND_BACKGROUND_STATUS, {}

    # Background Activity Inspection
    if any(phrase in q for phrase in [
        'what happens at the background', 'what happens in the background',
        'what is happening in the background', 'what is happening at the background',
        "what's happening in the background", "what's happening at the background",
        'what is running in the background', "what's running in the background",
        'what is running at the background', "what's running at the background",
        'what background apps are running', 'what apps are in the background',
        'what is working in the background', 'what is happening in background',
        'check background tasks', 'check background activity', 'check the background',
        'background activity', 'background status', 'background tasks',
        'what processes are in the background', 'show background processes',
        'show background activity', 'what is going on in the background',
        'what is on the background', "what's on the background"
    ]) or (has_bg_kw and any(w in q for w in ['running', 'happening', 'happens', 'tasks', 'activity', 'status', 'apps', 'processes', 'going on', 'what'])):
        return IntentType.SYSTEM_BACKGROUND_STATUS, {}

    # Screen and Background Work Permissions (standalone grant/revoke or compound screen inspection)
    has_perm_phrase = any(p in q for p in [
        'screen permission', 'screen access', 'background permission', 'background work permission',
        'background work', 'take screen permission', 'take the screen permission', 'take my screen permission',
        'allow screen access', 'grant screen access', 'allow screen permission', 'grant screen permission',
        'take background permission', 'take background work permission', 'grant background permission',
        'grant background work permission', 'allow background work', 'enable background work',
        'skin permission', 'skin access', 'take my skin permission', 'take skin permission'
    ])
    if has_perm_phrase:
        is_revoke = any(w in q for w in ['stop', 'disable', 'revoke', 'deny'])
        if is_revoke:
            return IntentType.SYSTEM_PERMISSION, {"action": "revoke"}

        # Check if user also asked to see, read, summarize or inspect screen in the same command
        if any(w in q for w in ['see', 'written', 'read', 'summarize', 'summary', 'context', 'tell me what', 'what is on', 'look', 'what can you see']):
            screen_mode = "read_text" if any(w in q for w in ['written', 'read', 'text', 'hair']) else ("summarize" if any(w in q for w in ['summarize', 'summary', 'context']) else "describe")
            return IntentType.SCREEN_DESCRIBE, {"mode": screen_mode, "query": query.strip(), "permission_granted": True}

        return IntentType.SYSTEM_PERMISSION, {"action": "grant"}

    if any(phrase in q for phrase in ['what do you know about me', 'show my memory', 'what are my preferences', 'my profile']):
        return IntentType.MEMORY_INSPECT, {}

    # Explicit remember command
    if any(q.startswith(p) for p in ['remember this', 'remember that', 'remember:', 'remember ']) or any(p in q for p in ["don't forget that", "dont forget that", "store this in memory", "keep in mind that"]):
        note = q
        for prefix in ['remember this is', 'remember this:', 'remember this', 'remember that', 'remember:', 'remember', "don't forget that", "dont forget that", "keep in mind that"]:
            if note.startswith(prefix):
                note = note[len(prefix):].strip(" :,-")
                break
        return IntentType.MEMORY_REMEMBER, {"note": note}

    # Context memory queries (mood, feelings, weather query recall, explicit notes recall)
    if any(phrase in q for phrase in [
        'what did i tell you to remember', 'what did i ask you to remember', 'do you remember what i told you',
        'what is in your fixed memory', 'check fixed memory', 'show fixed memory',
        'how am i feeling', 'how do i feel', 'what is my mood', "what's my mood", 'am i bored', 'did i say i am bored',
        'what weather did i ask', 'what was the weather i asked',
    ]):
        return IntentType.MEMORY_CONTEXT_QUERY, {"query": q}

    # Clear conversation
    if any(phrase in q for phrase in ['clear conversation', 'reset conversation', 'clear chat', 'new chat']):
        return IntentType.MEMORY_RESET_CONVERSATION, {}

    # Local diagnostics
    if any(phrase in q for phrase in [
        'network speed', 'internet speed', 'internet connection speed',
        'wifi speed', 'wi-fi speed', 'check my internet', 'check the internet',
        'how fast is my internet', 'download speed', 'upload speed',
        'check my network', 'network performance', 'internet performance',
    ]):
        return IntentType.SYSTEM_NETWORK_SPEED, {}

    if any(phrase in q for phrase in [
        'system condition', 'system status', 'computer condition',
        'computer status', 'pc condition', 'pc status', 'system health',
        'cpu usage', 'ram usage', 'memory usage', 'disk usage',
        'how is my system', 'how is my computer',
    ]):
        return IntentType.SYSTEM_CONDITION, {}
    if any(term in q for term in ['cpu', 'ram', 'processor']) and any(
        term in q for term in ['usage', 'status', 'condition', 'health', 'how', 'check', 'tell']
    ):
        return IntentType.SYSTEM_CONDITION, {}

    # Desktop Automation - Screenshot
    if any(s in q for s in ['take a screenshot', 'take screenshot', 'capture screen', 'screenshot']):
        return IntentType.DESKTOP_SCREENSHOT, {}

    # ==========================================
    # Screen Vision Intents
    # ==========================================

    # 1. Screen Describe / Reading / Content Awareness / Summarization
    is_screen_query = False
    screen_mode = "describe"

    screen_phrases = [
        'what happens in the screen', 'what happens on the screen', 'what happens on screen',
        'what is happening in the screen', 'what is happening on the screen', 'what is happening on screen',
        "what's happening on the screen", "what's happening in the screen", "what's happening on screen",
        'what is going on on my screen', 'what is going on in the screen', 'what is going on on screen',
        'what is currently open on my screen', 'what is open on my screen', "what's open on my screen",
        'what is on my screen', "what's on my screen", 'what is on the screen', "what's on the screen",
        'what is on screen', "what's on screen", 'what is currently on the screen',
        'what is this page about', "what's this page about", 'what is on this page', "what's on this page",
        'describe my screen', 'describe the screen', 'describe what you see', 'describe what is on screen',
        'read my screen', 'read the screen', 'read the text', 'read text on screen', 'read what is written',
        'read what is on screen', 'read what is on the screen', 'read what you see', 'read the context',
        'read screen context', 'read context',
        'what do you see on my screen', 'what can you see on my screen', 'scan screen and describe',
        'what can you see now', 'what do you see now', 'what can you see', 'what do you see',
        'tell me what you see', 'tell me what can you see', 'tell me what is on the screen', 'tell me what is on screen',
        'can you tell me what can you see', 'can you tell me what you see', 'can you see now', 'can you see the screen',
        'can you see my screen', 'can you see what is on the screen', 'can you see what is on screen',
        'what are you seeing', 'what can be seen',
        'what is written on hair', 'what is written on here', 'what is written here', 'what is written on screen',
        'what is written on the screen', 'what is written in this window', 'what is written on the page',
        'what is written', "what's written here", "what's written on screen", "what's written",
        'what text is on screen', 'what text is written', 'tell me what is written',
        'summarize this page', 'summarize current screen', 'summarize the screen', 'summarize my screen',
        'summarize what you see', 'summarize what is on the screen', 'summarize what is on screen',
        'summarize what is written', 'summarize screen context', 'summarize context',
        'check the screen', 'check my screen', 'inspect the screen', 'inspect my screen',
        'look at my screen', 'look at the screen'
    ]

    if any(phrase in q for phrase in screen_phrases):
        is_screen_query = True
    elif (
        re.search(r"\b(?:what|tell me|can you tell me|read|summarize)\b.*\b(?:see|written|reading|screen|display)\b", q)
        and not any(w in q for w in ["youtube", "google search", "wikipedia", "calculator", "weather", "volume", "brightness"])
    ):
        is_screen_query = True

    if is_screen_query:
        if any(w in q for w in ['written', 'read', 'text', 'hair']):
            screen_mode = "read_text"
        elif any(w in q for w in ['summarize', 'summary', 'context']):
            screen_mode = "summarize"
        else:
            screen_mode = "describe"
        return IntentType.SCREEN_DESCRIBE, {"mode": screen_mode, "query": query.strip()}

    # 2. Compound Scroll & Action: e.g. "scroll down and open the third result"
    scroll_compound = re.search(r"scroll\s+(down|up|bottom|top)\s+(?:and\s+)?(?:then\s+)?(open|click|play)\s+(?:the\s+)?(.+)", q, re.IGNORECASE)
    if scroll_compound:
        return IntentType.SCREEN_SCROLL, {
            "direction": scroll_compound.group(1).lower(),
            "then_action": scroll_compound.group(2).lower(),
            "then_target": scroll_compound.group(3).strip()
        }

    # 3. Screen Typing: e.g. "type Python into search box"
    screen_type_match = re.search(r"^(?:please\s+)?type\s+(.+?)\s+(?:in|into|on)\s+(?:the\s+)?(.+)$", q, re.IGNORECASE)
    if screen_type_match and any(fld in screen_type_match.group(2).lower() for fld in ["box", "field", "input", "bar", "text", "search"]):
        return IntentType.SCREEN_TYPE, {
            "text": screen_type_match.group(1).strip(),
            "target": screen_type_match.group(2).strip()
        }

    # 4. Screen Play: e.g. "play the second song", "play the third video"
    screen_play_match = re.match(
        r"^(?:please\s+)?play\s+(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th|\d+)\s*(video|song|track|item|card|one)$",
        q,
        re.IGNORECASE
    )
    if screen_play_match:
        ord_val = screen_play_match.group(1).strip()
        item_kind = screen_play_match.group(2).strip()
        return IntentType.SCREEN_PLAY, {"target": f"{ord_val} {item_kind}"}

    # 5. Screen Open: e.g. "open the second Google search result", "open the link about Python", "open images tab", "open search bar"
    screen_open_patterns = [
        # "open the link about Python", "open link about Python"
        r"^(?:please\s+)?open\s+(?:the\s+)?link\s+about\s+(.+)$",
        # "open the second Google search result", "open the third search result"
        r"^(?:please\s+)?open\s+(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th|\d+)?\s*(?:google\s+)?search\s+result$",
        # "open the second link", "open the third result"
        r"^(?:please\s+)?open\s+(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th|\d+)\s+(result|link|video|song|item)$",
        # "open images tab", "open short videos tab", "open search bar", "open link description"
        r"^(?:please\s+)?open\s+(?:the\s+)?(.+?\s+tab|tab\s+.+|search\s+bar|search\s+box|link\s+description|description)$",
        # "open the Python link"
        r"^(?:please\s+)?open\s+(?:the\s+)?(.+?)\s+link$"
    ]
    for sop in screen_open_patterns:
        m = re.match(sop, q, re.IGNORECASE)
        if m:
            clean_tgt = re.sub(r"^(?:please\s+)?open\s+(?:the\s+)?", "", q, flags=re.IGNORECASE).strip()
            return IntentType.SCREEN_OPEN, {"target": clean_tgt}

    # Tab navigation / switching on screen: "switch to images tab", "go to videos tab", "select ai mode tab"
    tab_nav_match = re.match(r"^(?:please\s+)?(?:go\s+to|switch\s+to|select)\s+(?:the\s+)?(.+?\s+tab|search\s+bar|search\s+box)$", q, re.IGNORECASE)
    if tab_nav_match:
        return IntentType.SCREEN_CLICK, {"target": tab_nav_match.group(1).strip()}

    # Search bar focus / click: "focus search bar", "select search bar", "focus the search bar"
    if any(q.startswith(p) for p in ["focus search bar", "select search bar", "focus the search bar", "select the search bar"]):
        return IntentType.SCREEN_CLICK, {"target": "search bar"}

    # 6. Screen Click: e.g. "click the third video", "click the second result", "click button called Submit"
    screen_click_match = re.match(r"^(?:please\s+)?click\s+(?:on\s+)?(?:the\s+)?(.+)$", q, re.IGNORECASE)
    if screen_click_match:
        tgt = screen_click_match.group(1).strip()
        return IntentType.SCREEN_CLICK, {"target": tgt}

    # 7. Screen Scroll: "scroll down", "scroll up"
    if q in ["scroll down", "scroll up", "scroll screen down", "scroll screen up", "page down", "page up"]:
        direction = "down" if "down" in q else "up"
        return IntentType.SCREEN_SCROLL, {"direction": direction}

    # Desktop Automation - Open / Play Nth Link, Song, Video, or Result on Active Screen (1st, 2nd, 3rd, 4th, etc.)
    ordinal_map = {
        'first': 1, '1st': 1, 'top': 1, 'one': 1, '1': 1,
        'second': 2, '2nd': 2, 'two': 2, '2': 2,
        'third': 3, '3rd': 3, 'three': 3, '3': 3,
        'fourth': 4, '4th': 4, 'four': 4, '4': 4,
        'fifth': 5, '5th': 5, 'five': 5, '5': 5,
        'sixth': 6, '6th': 6, 'six': 6, '6': 6,
        'seventh': 7, '7th': 7, 'seven': 7, '7': 7,
        'eighth': 8, '8th': 8, 'eight': 8, '8': 8,
        'ninth': 9, '9th': 9, 'nine': 9, '9': 9,
        'tenth': 10, '10th': 10, 'ten': 10, '10': 10
    }
    ord_words = 'first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th|top|one|two|three|four|five|six|seven|eight|nine|ten'

    nth_item_patterns = [
        rf"^(?:please\s+)?(?:play|open|click|select|choose|start)\s+(?:the\s+)?({ord_words}|\d+(?:st|nd|rd|th)?)\s*(?:one|song|video|link|result|track|item)?$",
        rf"^(?:please\s+)?(?:play|open|click|select|choose|start)\s+(?:song|video|link|result|track|item|number|no\.?)\s*(?:#|no\.?)?\s*(\d+|{ord_words})$",
        rf"^(?:the\s+)?({ord_words}|\d+(?:st|nd|rd|th)?)\s+(?:one|song|video|link|result|track|item)$",
        rf"^(?:the\s+)?(second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th)$"
    ]

    for pat in nth_item_patterns:
        nth_match = re.match(pat, q, re.IGNORECASE)
        if nth_match:
            tok = nth_match.group(1).lower()
            idx = ordinal_map.get(tok)
            if idx is None:
                num = re.search(r'\d+', tok)
                if num:
                    idx = int(num.group(0))
            if idx:
                return IntentType.DESKTOP_FIRST_LINK, {"index": idx}


    # Desktop Automation - Search In Active Tab (e.g. browser tab or active app)
    in_tab_patterns = [
        r"(?:search on this tab|search in this tab|search on their|search on there|search here)\s+(?:for\s+)?(.+)",
        r"(?:search this tab for|search tab for)\s+(.+)",
        r"search\s+(.+?)\s+(?:on this tab|in this tab|on there|on their|here)$",
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
    if (
        read_file_match
        and not q.startswith("open file ")
        and not any(w in q for w in ["note", "camera", "app"])
    ):
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

    folder_open_match = re.match(
        r"^(?:please\s+)?open\s+(?:this\s+)?(.+?)\s+folder\s+"
        r"(?:from|in|on)\s+(?:my\s+)?(desktop|downloads|documents|music|pictures)$",
        q,
        re.IGNORECASE,
    )
    if folder_open_match:
        return IntentType.SYSTEM_FOLDER_OPEN, {
            "folder": folder_open_match.group(1).strip(),
            "location": folder_open_match.group(2).strip(),
        }

    file_open_match = re.match(
        r"^(?:please\s+)?open\s+(?:this\s+)?(?:file\s+)?(.+?)"
        r"(?:\s+(?:from|in|on)\s+(?:my\s+)?"
        r"(desktop|downloads|documents|music|pictures))?$",
        q,
        re.IGNORECASE,
    )
    if file_open_match:
        target = file_open_match.group(1).strip()
        location = file_open_match.group(2)
        known_file_extension = bool(re.search(
            r"\.(?:pdf|docx?|xlsx?|pptx?|txt|csv|rtf|odt|ods|zip|rar|png|jpe?g|gif)$",
            target,
            re.IGNORECASE,
        ))
        known_file_description = bool(re.search(
            r"\b(?:pdf|word|excel|spreadsheet|powerpoint|text|csv|image|"
            r"document|file|sheet)\s*(?:file|document|sheet|file)?\b",
            target,
            re.IGNORECASE,
        ))
        if location or known_file_extension or known_file_description or q.startswith("open file "):
            return IntentType.SYSTEM_FILE_OPEN, {
                "file": target,
                "location": location,
            }

    # Compound YouTube Search command: "open youtube and search for...", "search ... on youtube", etc.
    youtube_search_patterns = [
        r"^(?:please\s+)?open\s+(?:up\s+)?youtube(?:\s+(?:and|then)\s+)?(?:search\s+(?:for\s+)?|find\s+)(.+)$",
        r"^(?:please\s+)?(?:search\s+(?:for\s+)?|find\s+)(.+?)\s+(?:on\s+youtube|in\s+youtube)$",
        r"^(?:please\s+)?(?:search\s+(?:on\s+|in\s+)?youtube\s+(?:for\s+)?)(.+)$",
    ]
    for pattern in youtube_search_patterns:
        yt_search_match = re.match(pattern, q, re.IGNORECASE)
        if yt_search_match:
            search_target = yt_search_match.group(1).strip()
            search_target = re.sub(r"^for\s+", "", search_target, flags=re.IGNORECASE).strip()
            if search_target:
                return IntentType.SYSTEM_YOUTUBE_SEARCH, {"query": search_target}

    # Compound YouTube Play command: opening the site is part of the play request
    youtube_play_match = re.match(
        r"^(?:please\s+)?open\s+(?:up\s+)?youtube(?:\s+(?:and|then)\s+)?"
        r"(?:play\s+(?:a\s+|the\s+)?|playa\s+)(.+)$",
        q,
        re.IGNORECASE,
    )
    if youtube_play_match:
        song = youtube_play_match.group(1).strip()
        if song:
            return IntentType.SYSTEM_YOUTUBE_PLAY, {"song": song}

    play_on_yt_match = re.match(
        r"^(?:please\s+)?play\s+(.+?)\s+(?:on\s+youtube|in\s+youtube)$",
        q,
        re.IGNORECASE,
    )
    if play_on_yt_match:
        song = play_on_yt_match.group(1).strip()
        if song:
            return IntentType.SYSTEM_YOUTUBE_PLAY, {"song": song}

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

    # A requested song is a YouTube playback request, not a conversation.
    song_play_match = re.match(
        r"^(?:please\s+)?(?:play\s+(?:a\s+|an\s+|the\s+)?|playa\s+)(.+)$",
        q,
        re.IGNORECASE,
    )
    if song_play_match:
        song = song_play_match.group(1).strip()
        if song and song not in {"song", "music"} and any(
            word in song for word in ["song", "music", "track"]
        ):
            return IntentType.SYSTEM_YOUTUBE_PLAY, {"song": song}

    # Notes
    if any(n in q for n in ['take a note', 'write a note', 'make a note', 'save a note']):
        return IntentType.SYSTEM_NOTES, {"action": "write"}
    if any(n in q for n in ['read note', 'show note', 'check note', 'read notes']):
        return IntentType.SYSTEM_NOTES, {"action": "read"}

    # Alarms, Alerts, and Reminders
    if any(k in q for k in ['alarm', 'alert', 'remind', 'reminder', 'timer']):
        from brain.alert_service import parse_alert_request
        alert_data = parse_alert_request(query)
        action = alert_data.get("action")
        if action == "set":
            return IntentType.SYSTEM_ALERT_SET, alert_data
        elif action == "list":
            return IntentType.SYSTEM_ALERT_LIST, alert_data
        elif action == "cancel":
            return IntentType.SYSTEM_ALERT_CANCEL, alert_data
        elif action == "stop":
            return IntentType.SYSTEM_ALERT_STOP, alert_data
        elif any(r in q for r in ['set a reminder', 'set reminder', 'remind me', 'add reminder', 'set alert', 'set alarm', 'give me alert']):
            return IntentType.SYSTEM_ALERT_SET, alert_data

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
