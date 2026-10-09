"""
Neura Alert & Alarm Service.
Handles intelligent timer, alarm, and scheduled alert management with relative offset calculation,
background worker loop, audible alarm ringing, voice notification, chat bridge updates,
and persistent storage.
"""

import os
import re
import time
import json
import uuid
import ctypes
import datetime
import threading
import subprocess
from typing import Dict, Any, List, Optional, Tuple, Callable

ALERTS_STORAGE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "memory",
    "alerts.json"
)
STATUS_BRIDGE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "status_bridge.json"
)
CHAT_BRIDGE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "chat_bridge.json"
)

WORD_TO_NUMBER = {
    "zero": 0, "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "twenty-five": 25, "twenty five": 25,
    "thirty": 30, "thirty-five": 35, "thirty five": 35, "forty": 40, "forty-five": 45,
    "forty five": 45, "fifty": 50, "fifty-five": 55, "fifty five": 55, "sixty": 60,
    "half": 0.5, "quarter": 0.25
}


def parse_numeric_phrase(text: str) -> Optional[float]:
    """Converts numeric words or digit strings into a float."""
    t = text.strip().lower()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        pass

    if t in WORD_TO_NUMBER:
        return float(WORD_TO_NUMBER[t])

    # Check compounds like "twenty five" or "one and a half"
    if "and a half" in t:
        base = t.replace("and a half", "").strip()
        val = parse_numeric_phrase(base)
        return (val + 0.5) if val is not None else 1.5

    parts = t.split()
    total = 0.0
    matched = False
    for p in parts:
        if p in WORD_TO_NUMBER:
            total += WORD_TO_NUMBER[p]
            matched = True
        else:
            try:
                total += float(p)
                matched = True
            except ValueError:
                pass
    return total if matched else None


def extract_duration(text: str) -> Optional[float]:
    """
    Extracts total duration in seconds from a textual phrase.
    Handles phrases like:
    - '5 minutes', '30 seconds', '2 hours'
    - '1 hour and 30 minutes', 'half an hour', 'quarter of an hour'
    - 'three minutes', 'five mins', '10 sec'
    """
    if not text:
        return None
    t = text.strip().lower()

    if "half an hour" in t or "half hour" in t:
        return 1800.0
    if "quarter of an hour" in t or "quarter hour" in t:
        return 900.0

    total_seconds = 0.0
    found_any = False

    # Hours
    hr_match = re.search(r"(\d+(?:\.\d+)?|\b[a-z\- ]+?\b)\s*(?:hours?|hrs?|hr|h)\b", t)
    if hr_match:
        val = parse_numeric_phrase(hr_match.group(1))
        if val is not None:
            total_seconds += val * 3600.0
            found_any = True

    # Minutes
    min_match = re.search(r"(\d+(?:\.\d+)?|\b[a-z\- ]+?\b)\s*(?:minutes?|mins?|min|m)\b", t)
    if min_match:
        val = parse_numeric_phrase(min_match.group(1))
        if val is not None:
            total_seconds += val * 60.0
            found_any = True

    # Seconds
    sec_match = re.search(r"(\d+(?:\.\d+)?|\b[a-z\- ]+?\b)\s*(?:seconds?|secs?|sec|s)\b", t)
    if sec_match:
        val = parse_numeric_phrase(sec_match.group(1))
        if val is not None:
            total_seconds += val
            found_any = True

    if found_any:
        return total_seconds

    # Plain number fallback if input is just e.g. "5" and context implied minutes
    plain_num = parse_numeric_phrase(t)
    if plain_num is not None:
        return plain_num * 60.0

    return None


def extract_clock_time(text: str, base_dt: Optional[datetime.datetime] = None) -> Optional[datetime.datetime]:
    """
    Extracts a specific clock time (e.g., '5:30 pm', '7 am', '14:00', 'at 6 o'clock')
    and returns a datetime object in the future.
    Rejects strings with duration units like minutes, seconds, hours.
    """
    if not text:
        return None
    now = base_dt or datetime.datetime.now()
    t = text.strip().lower()

    # Reject if it's clearly a duration
    if any(unit in t for unit in ["minute", "min", "second", "sec", "hour", "hr"]):
        return None

    # Must have clock indicators: 'am', 'pm', ':', "o'clock", or preceded by 'at '
    has_meridiem = bool(re.search(r"\b(am|pm|a\.m\.|p\.m\.)\b", t))
    has_colon = ":" in t
    has_oclock = "o'clock" in t
    has_at_prefix = bool(re.search(r"\bat\s+\d{1,2}\b", t))

    if not (has_meridiem or has_colon or has_oclock or has_at_prefix):
        return None

    # Match formats like 5:30 pm, 5:30pm, 17:30, 7 am, 7pm, 6 o'clock, at 5
    m = re.search(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.|o'clock)?\b", t)
    if not m:
        return None

    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    meridiem = (m.group(3) or "").replace(".", "").lower()

    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    elif not meridiem and hour < 7:
        if now.hour >= 12:
            hour += 12

    try:
        target_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target_dt <= now:
            # If target time has already passed today, schedule for tomorrow
            target_dt += datetime.timedelta(days=1)
        return target_dt
    except ValueError:
        return None


def format_duration_friendly(seconds: float) -> str:
    """Formats seconds into human friendly duration like '3 minutes', '1 hour 15 minutes'."""
    sec = int(round(seconds))
    if sec < 60:
        return f"{sec} second{'s' if sec != 1 else ''}"
    minutes = sec // 60
    rem_sec = sec % 60
    hours = minutes // 60
    rem_min = minutes % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if rem_min > 0:
        parts.append(f"{rem_min} minute{'s' if rem_min != 1 else ''}")
    if rem_sec > 0 and hours == 0:
        parts.append(f"{rem_sec} second{'s' if rem_sec != 1 else ''}")
    return " ".join(parts) if parts else "0 seconds"


def clean_label(label: str) -> str:
    """Cleans up raw label text into a clean presentation string."""
    lbl = label.strip()
    lbl = re.sub(r"^(?:that|for|to|about|because)\s+", "", lbl, flags=re.IGNORECASE)
    lbl = re.sub(r"^(?:i have|there is|we have)\s+(?:a|an\s+)?", "", lbl, flags=re.IGNORECASE)
    lbl = re.sub(r"^(?:a|an|the)\s+", "", lbl, flags=re.IGNORECASE)
    lbl = lbl.strip(" .,?!")
    if not lbl:
        return "Scheduled Task"
    return lbl[:1].upper() + lbl[1:]



def build_contextual_alert_speech(
    label: str,
    remaining_to_event_sec: Optional[float] = None,
    duration_sec: Optional[float] = None,
    source_query: str = ""
) -> str:
    """
    Constructs a polite, natural, and context-aware spoken reminder for when the alert triggers.
    Examples:
    - Direct event: 'Sir! You have an important meeting right now as you have told me. Please get ready for the meeting.'
    - Offset event: 'Sir! As you told me, you have a meeting in 2 minutes. Please get ready for the meeting.'
    - Action reminder: 'Sir! It is time to take your medicine right now as you have told me.'
    - Plain timer: 'Sir! Your 5-minute timer has completed as you requested.'
    """
    lbl = (label or "").strip(" .?!")
    lbl_lower = lbl.lower()
    sq_lower = (source_query or "").lower()

    # 1. Action tasks (starts with 'to ' or verb like take, check, drink, etc.)
    if lbl_lower.startswith("to "):
        action = lbl[3:].strip()
        if "medicine" in action and "your" not in action:
            action = action.replace("medicine", "your medicine")
        return f"Sir! It is time to {action} right now as you have told me."

    verbs = ["take ", "check ", "drink ", "submit ", "call ", "leave ", "wake up", "turn off"]
    for v in verbs:
        if lbl_lower.startswith(v):
            action = lbl
            if "medicine" in action and "your" not in action:
                action = action.replace("medicine", "your medicine")
            return f"Sir! It is time to {action} right now as you have told me."

    # 2. Events (meeting, interview, call, class, exam, appointment, webinar, presentation, etc.)
    event_words = [
        "meeting", "interview", "call", "class", "exam", "appointment",
        "webinar", "presentation", "session", "discussion", "event", "flight", "train"
    ]
    is_event = any(ew in lbl_lower for ew in event_words) or any(ew in sq_lower for ew in event_words)

    if is_event:
        noun = "meeting"
        for ew in event_words:
            if ew in lbl_lower:
                noun = ew
                break
            elif ew in sq_lower:
                noun = ew
                break

        clean_text = lbl
        for p in ["that i have", "i have", "there is", "we have", "scheduled"]:
            if clean_text.lower().startswith(p):
                clean_text = clean_text[len(p):].strip()

        clean_text = re.sub(r"\s*\(in\s+[^)]+\)", "", clean_text).strip()

        words = clean_text.split()
        first_w = words[0].lower() if words else ""
        if first_w in ["a", "an", "the", "my", "your"]:
            art_phrase = clean_text[:1].lower() + clean_text[1:]
        else:
            art = "an" if clean_text and clean_text[0].lower() in "aeiou" else "a"
            clean_part = clean_text[:1].lower() + clean_text[1:] if clean_text else noun
            art_phrase = f"{art} {clean_part}"


        if remaining_to_event_sec and remaining_to_event_sec >= 15:
            rem_str = format_duration_friendly(remaining_to_event_sec)
            return f"Sir! As you told me, you have {art_phrase} in {rem_str}. Please get ready for the {noun}."
        else:
            return f"Sir! You have {art_phrase} right now as you have told me. Please get ready for the {noun}."

    # 3. Plain alarm / timer
    if lbl_lower in ["alarm", "timer", "scheduled task", "alert me"]:
        dur_str = format_duration_friendly(duration_sec) if duration_sec else "scheduled"
        return f"Sir! Your {dur_str} alarm has arrived as you have told me."

    # 4. Fallback
    return f"Sir! You have {lbl} right now as you have told me. Please get ready for it."


def parse_alert_request(query: str, base_dt: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    """
    Comprehensive natural language parser for alerts, alarms, and reminders.
    """
    now = base_dt or datetime.datetime.now()
    q = query.strip()
    q_lower = q.lower()
    # Normalize assistant address and conversational openers
    q_lower = re.sub(r"^(?:neura|nura|hey neura|hello neura)\s+", "", q_lower).strip()
    q_lower = re.sub(r"^(?:please\s+)?(?:can you\s+)?(?:please\s+)?", "", q_lower).strip()

    result: Dict[str, Any] = {
        "action": "none",
        "delay_seconds": None,
        "target_time": None,
        "label": "Alarm",
        "explanation": "",
        "trigger_speech": "",
        "raw_query": query,
        "success": False,
        "error": None
    }

    # 1. Stop / Silence Active Ringing Alarm
    if any(phrase in q_lower for phrase in [
        "stop alarm", "turn off alarm", "silence alarm", "shut up alarm", "stop ringing", "cancel ringing"
    ]):
        result["action"] = "stop"
        result["success"] = True
        return result

    # 2. Cancel Existing Alerts
    is_cancel_cmd = any(word in q_lower for word in ["cancel", "delete", "clear", "remove"]) and any(kw in q_lower for kw in ["alarm", "alert", "reminder", "timer"])
    if is_cancel_cmd:
        result["action"] = "cancel"
        target_lbl = "all"
        m = re.search(r"(?:cancel|delete|clear|remove)\s+(?:the\s+|all\s+)?([a-z0-9_\-\s]+?)\s+(?:alarm|alert|reminder|timer)", q_lower)
        if m:
            extracted = m.group(1).strip()
            if extracted and extracted not in ["all", "the", "my"]:
                target_lbl = extracted
        result["label"] = target_lbl
        result["success"] = True
        return result

    # 3. List Active Alerts
    if any(phrase in q_lower for phrase in [
        "list alarms", "list alerts", "list reminders", "show my alarms", "show alarms",
        "show my alerts", "show alerts", "what alarms are set", "what alerts are set",
        "check my alarms", "check alarms", "check my alerts", "any alarms set", "do i have any alarms",
        "what are my alarms", "what are my alerts", "tell me my alarms", "active alarms"
    ]):
        result["action"] = "list"
        result["success"] = True
        return result

    # 4. Check for Set Alert / Alarm Intent
    has_alarm_keyword = any(kw in q_lower for kw in [
        "alarm", "alert", "remind", "reminder", "timer"
    ])

    if not has_alarm_keyword:
        return result

    result["action"] = "set"

    # =========================================================================
    # Pattern A: Relative Offset / Loophole Pattern
    # E.g.: "I have a meeting after 5 minutes, so alert me before 2 minutes of that"
    # E.g.: "I have a meeting in 10 minutes, alert me 3 minutes before that"
    # E.g.: "I have a meeting after 5 minutes, alert me after 3 minutes"
    # =========================================================================

    # Pattern A1: Event phrase first, then alert with offset
    # "i have [a] <event> (in|after|at) <event_time> ... alert me (before|after) <offset> (of that|before that|after that)?"
    regex_loophole_1 = re.compile(
        r"(?:i have|there is|we have|my)\s+(?:a|an\s+)?(?P<event>[a-z0-9_\-\s]+?)\s+"
        r"(?:in|after|at)\s+(?P<event_time>[a-z0-9_\-:\.\s]+?)"
        r"(?:,|\s+so|\s+and|\s+then|\s+please)*\s+"
        r"(?:so\s+)?(?:please\s+)?(?:alert|remind|give me (?:an? )?alert|set (?:an? )?(?:alarm|alert|reminder))(?: me)?\s+"
        r"(?P<offset_clause>(?:before|after)\s+[a-z0-9_\-:\.\s]+|[a-z0-9_\-:\.\s]+\s+(?:before|after)(?:\s+(?:that|of that))?)",
        re.IGNORECASE
    )

    m1 = regex_loophole_1.search(q_lower)
    if m1:
        raw_event = m1.group("event").strip()
        raw_event_time = m1.group("event_time").strip()
        raw_offset_clause = m1.group("offset_clause").strip()

        event_dur = extract_duration(raw_event_time)
        event_clock = extract_clock_time(raw_event_time, now)
        offset_dur = extract_duration(raw_offset_clause)

        # Detect direction ("before" vs "after")
        is_before = "before" in raw_offset_clause
        is_after = "after" in raw_offset_clause
        has_of_that = ("of that" in raw_offset_clause) or ("after that" in raw_offset_clause) or ("before that" in raw_offset_clause)

        # Case: event given in clock time (e.g., "meeting at 4:00 pm, alert me 15 minutes before")
        if event_clock and offset_dur:
            if is_before:
                target_dt = event_clock - datetime.timedelta(seconds=offset_dur)
            else:
                target_dt = event_clock + datetime.timedelta(seconds=offset_dur)
            delay = (target_dt - now).total_seconds()
            if delay <= 0:
                result["error"] = f"Calculated alert time {target_dt.strftime('%I:%M %p')} is already in the past."
                return result

            result["delay_seconds"] = delay
            result["target_time"] = target_dt
            result["label"] = clean_label(raw_event)
            event_clock_str = event_clock.strftime("%I:%M %p")
            alert_clock_str = target_dt.strftime("%I:%M %p")
            direction_str = "before" if is_before else "after"
            result["explanation"] = (
                f"Your {clean_label(raw_event)} is at {event_clock_str}. "
                f"Alert scheduled for {format_duration_friendly(offset_dur)} {direction_str} that "
                f"(at {alert_clock_str}, in {format_duration_friendly(delay)})."
            )
            result["trigger_speech"] = build_contextual_alert_speech(
                raw_event,
                remaining_to_event_sec=offset_dur if is_before else 0,
                duration_sec=delay,
                source_query=query
            )
            result["success"] = True
            return result

        # Case: event given in duration (e.g., "meeting after 5 minutes")
        if event_dur:
            # Subcase A: "before 2 minutes of that" or "2 minutes before"
            if is_before and offset_dur:
                delay = event_dur - offset_dur
                if delay <= 0:
                    result["error"] = (
                        f"Your {raw_event} is in {format_duration_friendly(event_dur)}, "
                        f"so {format_duration_friendly(offset_dur)} before that is already past!"
                    )
                    return result
                target_dt = now + datetime.timedelta(seconds=delay)
                result["delay_seconds"] = delay
                result["target_time"] = target_dt
                result["label"] = f"{clean_label(raw_event)} (in {format_duration_friendly(offset_dur)})"
                result["explanation"] = (
                    f"Your {clean_label(raw_event)} is in {format_duration_friendly(event_dur)}. "
                    f"Alert scheduled for {format_duration_friendly(offset_dur)} before that "
                    f"(in {format_duration_friendly(delay)}, at {target_dt.strftime('%I:%M %p')})."
                )
                result["trigger_speech"] = build_contextual_alert_speech(
                    raw_event,
                    remaining_to_event_sec=offset_dur,
                    duration_sec=delay,
                    source_query=query
                )
                result["success"] = True
                return result

            # Subcase B: "alert me after 2 minutes of that" (meaning after the event)
            elif is_after and has_of_that and offset_dur:
                delay = event_dur + offset_dur
                target_dt = now + datetime.timedelta(seconds=delay)
                result["delay_seconds"] = delay
                result["target_time"] = target_dt
                result["label"] = f"{clean_label(raw_event)}"
                result["explanation"] = (
                    f"Your {clean_label(raw_event)} is in {format_duration_friendly(event_dur)}. "
                    f"Alert scheduled for {format_duration_friendly(offset_dur)} after that "
                    f"(in {format_duration_friendly(delay)}, at {target_dt.strftime('%I:%M %p')})."
                )
                result["trigger_speech"] = build_contextual_alert_speech(
                    raw_event,
                    remaining_to_event_sec=0,
                    duration_sec=delay,
                    source_query=query
                )
                result["success"] = True
                return result

            # Subcase C: "alert me after 3 minutes" (explicit absolute relative delay)
            elif offset_dur:
                delay = offset_dur
                target_dt = now + datetime.timedelta(seconds=delay)
                rem_to_event = event_dur - delay
                rem_str = f", {format_duration_friendly(rem_to_event)} before your event" if rem_to_event > 0 else ""
                result["delay_seconds"] = delay
                result["target_time"] = target_dt
                result["label"] = f"{clean_label(raw_event)}"
                result["explanation"] = (
                    f"Your {clean_label(raw_event)} is in {format_duration_friendly(event_dur)}. "
                    f"Alert scheduled for {format_duration_friendly(delay)} from now{rem_str} "
                    f"(at {target_dt.strftime('%I:%M %p')})."
                )
                result["trigger_speech"] = build_contextual_alert_speech(
                    raw_event,
                    remaining_to_event_sec=rem_to_event,
                    duration_sec=delay,
                    source_query=query
                )
                result["success"] = True
                return result

    # Pattern A2: Reverse order (Alert first with offset, then event)
    # E.g.: "alert me 15 minutes before my meeting at 4 pm"
    # E.g.: "alert me 2 minutes before my meeting in 5 minutes"
    regex_reverse_loophole = re.compile(
        r"(?:alert|remind|give me (?:an? )?alert|set (?:an? )?(?:alarm|alert|reminder))(?: me)?\s+"
        r"(?P<offset_spec>[a-z0-9_\-:\.\s]+?\s+(?:before|after)|(?:before|after)\s+[a-z0-9_\-:\.\s]+?)\s+"
        r"(?:my|the|that)\s+(?P<event>[a-z0-9_\-\s]+?)\s+"
        r"(?:in|after|at)\s+(?P<event_time>[a-z0-9_\-:\.\s]+)",
        re.IGNORECASE
    )
    m2 = regex_reverse_loophole.search(q_lower)
    if m2:
        raw_offset_spec = m2.group("offset_spec").strip()
        raw_event = m2.group("event").strip()
        raw_event_time = m2.group("event_time").strip()

        offset_dur = extract_duration(raw_offset_spec)
        event_dur = extract_duration(raw_event_time)
        event_clock = extract_clock_time(raw_event_time, now)
        is_before = "before" in raw_offset_spec

        if event_clock and offset_dur:
            target_dt = (event_clock - datetime.timedelta(seconds=offset_dur)) if is_before else (event_clock + datetime.timedelta(seconds=offset_dur))
            delay = (target_dt - now).total_seconds()
            if delay > 0:
                result["delay_seconds"] = delay
                result["target_time"] = target_dt
                result["label"] = clean_label(raw_event)
                result["explanation"] = (
                    f"Your {clean_label(raw_event)} is at {event_clock.strftime('%I:%M %p')}. "
                    f"Alert scheduled for {format_duration_friendly(offset_dur)} {'before' if is_before else 'after'} "
                    f"(at {target_dt.strftime('%I:%M %p')})."
                )
                result["trigger_speech"] = build_contextual_alert_speech(
                    raw_event,
                    remaining_to_event_sec=offset_dur if is_before else 0,
                    duration_sec=delay,
                    source_query=query
                )
                result["success"] = True
                return result
        elif event_dur and offset_dur:
            delay = (event_dur - offset_dur) if is_before else (event_dur + offset_dur)
            if delay > 0:
                target_dt = now + datetime.timedelta(seconds=delay)
                result["delay_seconds"] = delay
                result["target_time"] = target_dt
                result["label"] = f"{clean_label(raw_event)}"
                result["explanation"] = (
                    f"Your {clean_label(raw_event)} is in {format_duration_friendly(event_dur)}. "
                    f"Alert scheduled for {format_duration_friendly(offset_dur)} {'before' if is_before else 'after'} that "
                    f"(in {format_duration_friendly(delay)}, at {target_dt.strftime('%I:%M %p')})."
                )
                result["trigger_speech"] = build_contextual_alert_speech(
                    raw_event,
                    remaining_to_event_sec=offset_dur if is_before else 0,
                    duration_sec=delay,
                    source_query=query
                )
                result["success"] = True
                return result

    # =========================================================================
    # Pattern B: Direct Relative Timers / Alerts
    # E.g.: "give me alert after 5 minutes that i have a meeting"
    # E.g.: "can you set a alert that i have after 5 minutes i have a meeting"
    # E.g.: "neura please alert me after 5 minutes that i have an important meeting"
    # E.g.: "set an alert after 10 minutes to take medicine"
    # E.g.: "alert me in 30 seconds"
    # E.g.: "set an alarm for 5 minutes"
    # =========================================================================

    # Look for duration phrase following "after", "in", or "for"
    dur_match = re.search(
        r"(?:after|in|for)\s+((?:\d+(?:\.\d+)?|\b[a-z\- ]+?\b)\s*(?:hours?|hrs?|hr|h|minutes?|mins?|min|m|seconds?|secs?|sec|s))\b",
        q_lower
    )
    if dur_match:
        dur_str = dur_match.group(1)
        delay = extract_duration(dur_str)
        if delay and delay > 0:
            target_dt = now + datetime.timedelta(seconds=delay)
            result["delay_seconds"] = delay
            result["target_time"] = target_dt

            # Extract event label from remaining text
            remaining = q_lower
            remaining = re.sub(r"^(?:neura|nura|hey neura|hello neura)\s+", "", remaining).strip()
            remaining = re.sub(r"^(?:please\s+)?(?:can you\s+)?(?:please\s+)?", "", remaining).strip()
            remaining = re.sub(r"^(?:set|give me|create|add|schedule)\s+(?:an? )?(?:alert|alarm|reminder|timer)(?:\s+that)?", "", remaining).strip()
            remaining = re.sub(r"^(?:alert|remind)(?: me)?(?:\s+that)?", "", remaining).strip()
            remaining = re.sub(re.escape(dur_match.group(0)), "", remaining).strip()
            remaining = re.sub(r"^(?:that|for|about|i have after [a-z0-9\s]+)\s*", "", remaining).strip()

            m_event = re.search(r"^(?:that\s+)?(?:i have|there is|we have)\s+(?:(an|a)\s+)?(.+)", remaining, flags=re.I)
            if m_event:
                ev_name = m_event.group(2).strip(" .?!")
                label = clean_label(ev_name)
            else:
                label = clean_label(remaining) if remaining else "Alarm"

            trigger_speech = build_contextual_alert_speech(
                label,
                remaining_to_event_sec=0,
                duration_sec=delay,
                source_query=query
            )

            result["label"] = label
            result["trigger_speech"] = trigger_speech
            result["explanation"] = (
                f"Alert set for {format_duration_friendly(delay)} from now "
                f"(at {target_dt.strftime('%I:%M %p')}) for: {label}."
            )
            result["success"] = True
            return result

    # =========================================================================
    # Pattern C: Direct Clock Times (Absolute Times)
    # E.g.: "set an alarm for 7:30 am", "alert me at 6:00 pm to call mom"
    # =========================================================================
    clock_dt = extract_clock_time(q_lower, now)
    if clock_dt:
        delay = (clock_dt - now).total_seconds()
        if delay > 0:
            result["delay_seconds"] = delay
            result["target_time"] = clock_dt

            # Clean label
            remaining = q_lower
            remaining = re.sub(r"^(?:neura|nura|hey neura|hello neura)\s+", "", remaining).strip()
            remaining = re.sub(r"^(?:can you\s+)?(?:please\s+)?(?:set|give me|create|add|schedule)\s+(?:an? )?(?:alert|alarm|reminder|timer)", "", remaining).strip()
            remaining = re.sub(r"\b(?:for|at)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|o'clock)?\b", "", remaining).strip()
            m_event = re.search(r"^(?:that\s+)?(?:i have|there is|we have)\s+(?:(an|a)\s+)?(.+)", remaining, flags=re.I)
            if m_event:
                art = m_event.group(1) or ("an" if m_event.group(2).strip()[0].lower() in "aeiou" else "a")
                label = f"{art} {m_event.group(2).strip(' .?!')}"
            else:
                label = clean_label(remaining) if remaining else "Alarm"

            trigger_speech = build_contextual_alert_speech(
                label,
                remaining_to_event_sec=0,
                duration_sec=delay,
                source_query=query
            )

            result["label"] = label
            result["trigger_speech"] = trigger_speech
            result["explanation"] = (
                f"Alarm set for {clock_dt.strftime('%I:%M %p')} "
                f"(in {format_duration_friendly(delay)}) for: {label}."
            )
            result["success"] = True
            return result

    # If duration could not be extracted
    result["error"] = "Could not parse duration or target time from query."
    return result


class AlertService:
    """
    Central Alert and Alarm Subsystem for Neura AI.
    Runs a precise background daemon monitoring scheduled alerts, sounds audible alarms,
    speaks voice notifications, updates GUI bridges, and saves state persistently.
    """

    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls, voice_speaker_fn: Optional[Callable[[str], None]] = None):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = AlertService(voice_speaker_fn=voice_speaker_fn)
            elif voice_speaker_fn is not None:
                cls._instance.voice_speaker = voice_speaker_fn
            return cls._instance

    def __init__(self, voice_speaker_fn: Optional[Callable[[str], None]] = None):
        self.voice_speaker = voice_speaker_fn
        self.alerts: List[Dict[str, Any]] = []
        self._lock = threading.RLock()
        self._worker_active = True
        self._is_ringing = False
        self._stop_ringing_event = threading.Event()
        self.load_alerts()

        # Start background worker daemon
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="NeuraAlertWorker")
        self._worker_thread.start()
        print("⏰ [AlertService] Background alert monitoring engine active.")

    def load_alerts(self):
        """Loads persistent alerts from storage."""
        with self._lock:
            if os.path.exists(ALERTS_STORAGE_FILE):
                try:
                    with open(ALERTS_STORAGE_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            self.alerts = data
                except Exception as e:
                    print(f"⚠️ [AlertService] Failed to load alerts from storage: {e}")
                    self.alerts = []
            else:
                self.alerts = []

    def save_alerts(self):
        """Persists alerts to disk."""
        with self._lock:
            try:
                os.makedirs(os.path.dirname(ALERTS_STORAGE_FILE), exist_ok=True)
                temp_file = f"{ALERTS_STORAGE_FILE}.tmp"
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(self.alerts, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_file, ALERTS_STORAGE_FILE)
            except Exception as e:
                print(f"⚠️ [AlertService] Failed to save alerts: {e}")

    def update_status_bridge(self, last_triggered_msg: str = ""):
        """Publishes active alerts status to status_bridge.json for GUI reflection."""
        try:
            active_list = []
            now_ts = time.time()
            with self._lock:
                for a in self.alerts:
                    if a.get("status") == "active":
                        rem = max(0, int(a.get("target_epoch", 0) - now_ts))
                        active_list.append({
                            "id": a.get("id"),
                            "label": a.get("label"),
                            "target_time_str": a.get("target_time_str"),
                            "remaining_seconds": rem,
                            "remaining_friendly": format_duration_friendly(rem)
                        })

            data = {}
            if os.path.exists(STATUS_BRIDGE_FILE):
                try:
                    with open(STATUS_BRIDGE_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {}

            data["active_alerts"] = active_list
            data["active_alerts_count"] = len(active_list)
            if last_triggered_msg:
                data["last_triggered_alert"] = last_triggered_msg

            temp_bridge = f"{STATUS_BRIDGE_FILE}.tmp"
            with open(temp_bridge, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_bridge, STATUS_BRIDGE_FILE)
        except Exception:
            pass

    def schedule_alert(
        self,
        label: str,
        delay_seconds: float,
        target_time: Optional[datetime.datetime] = None,
        explanation: str = "",
        source_query: str = "",
        trigger_speech: Optional[str] = None
    ) -> Dict[str, Any]:
        """Schedules a new alert."""
        now = datetime.datetime.now()
        if target_time is None:
            target_time = now + datetime.timedelta(seconds=delay_seconds)
        else:
            delay_seconds = max(1.0, (target_time - now).total_seconds())

        if not trigger_speech:
            trigger_speech = build_contextual_alert_speech(
                label=label,
                duration_sec=delay_seconds,
                source_query=source_query
            )

        alert_id = f"alert_{int(time.time())}_{uuid.uuid4().hex[:4]}"
        alert_record = {
            "id": alert_id,
            "created_at": now.isoformat(),
            "target_epoch": target_time.timestamp(),
            "target_time_str": target_time.strftime("%I:%M:%S %p"),
            "target_date_str": target_time.strftime("%Y-%m-%d"),
            "delay_seconds": delay_seconds,
            "label": label,
            "explanation": explanation or f"Alert for {label}",
            "trigger_speech": trigger_speech,
            "source_query": source_query,
            "status": "active"
        }

        with self._lock:
            self.alerts.append(alert_record)
            self.save_alerts()

        self.update_status_bridge()
        print(f"⏰ [AlertService] Scheduled '{label}' for {alert_record['target_time_str']} (in {format_duration_friendly(delay_seconds)})")
        return alert_record

    def list_active_alerts(self) -> List[Dict[str, Any]]:
        """Returns list of currently active pending alerts."""
        now_ts = time.time()
        active = []
        with self._lock:
            for a in self.alerts:
                if a.get("status") == "active":
                    rem = max(0, int(a.get("target_epoch", 0) - now_ts))
                    item = dict(a)
                    item["remaining_seconds"] = rem
                    item["remaining_friendly"] = format_duration_friendly(rem)
                    active.append(item)
        return active

    def format_active_alerts_summary(self) -> str:
        """Returns verbal or textual summary of active alerts."""
        active = self.list_active_alerts()
        if not active:
            return "Sir, you currently have no active alerts or alarms set."

        lines = [f"Sir, you have {len(active)} active alert{'s' if len(active) != 1 else ''}:"]
        for idx, a in enumerate(active, 1):
            lbl = a.get("label", "Alarm")
            t_str = a.get("target_time_str", "")
            rem_str = a.get("remaining_friendly", "")
            lines.append(f"{idx}. '{lbl}' scheduled for {t_str} (in {rem_str}).")
        return "\n".join(lines)

    def cancel_alerts(self, identifier: Optional[str] = None) -> Tuple[int, str]:
        """Cancels alerts matching label/id or all alerts if identifier is 'all' or None."""
        cancelled_count = 0
        with self._lock:
            for a in self.alerts:
                if a.get("status") == "active":
                    if identifier is None or identifier.strip().lower() in ["all", "everything", "*"]:
                        a["status"] = "cancelled"
                        cancelled_count += 1
                    elif identifier.strip().lower() in a.get("label", "").lower() or identifier == a.get("id"):
                        a["status"] = "cancelled"
                        cancelled_count += 1
            if cancelled_count > 0:
                self.save_alerts()

        self.update_status_bridge()
        self.stop_ringing()

        if cancelled_count == 0:
            return 0, "No matching active alerts were found to cancel."
        elif cancelled_count == 1:
            return 1, "The scheduled alert has been successfully cancelled."
        else:
            return cancelled_count, f"Successfully cancelled {cancelled_count} active alerts."

    def stop_ringing(self):
        """Silences any actively ringing alarm sound."""
        self._is_ringing = False
        self._stop_ringing_event.set()

    def _play_alarm_sound_sequence(self):
        """
        Plays an audible multi-tone digital alarm sound.
        Uses native Windows winsound for instant zero-dependency audio chime.
        """
        self._is_ringing = True
        self._stop_ringing_event.clear()

        def _sound_worker():
            try:
                import winsound
                # Play 3 pulses of high-clarity alarm tone
                for pulse in range(3):
                    if self._stop_ringing_event.is_set():
                        break
                    # Tone 1: 1200 Hz for 180 ms
                    winsound.Beep(1200, 180)
                    time.sleep(0.05)
                    if self._stop_ringing_event.is_set():
                        break
                    # Tone 2: 1550 Hz for 220 ms
                    winsound.Beep(1550, 220)
                    time.sleep(0.12)

                if not self._stop_ringing_event.is_set():
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception as e:
                print(f"[AlertService Sound Note]: {e}")
            finally:
                self._is_ringing = False

        snd_thread = threading.Thread(target=_sound_worker, daemon=True, name="NeuraAlarmSound")
        snd_thread.start()

    def _send_desktop_notification(self, title: str, message: str):
        """Sends a native Windows balloon/toast notification non-blockingly."""
        def _toast_worker():
            try:
                safe_title = title.replace("'", "").replace('"', "")
                safe_message = message.replace("'", "").replace('"', "")
                ps_script = (
                    "[reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null; "
                    "$notify = New-Object System.Windows.Forms.NotifyIcon; "
                    "$notify.Icon = [System.Drawing.SystemIcons]::Information; "
                    "$notify.Visible = $True; "
                    f"$notify.ShowBalloonTip(5000, '{safe_title}', '{safe_message}', [System.Windows.Forms.ToolTipIcon]::Info); "
                    "Start-Sleep -Seconds 6; "
                    "$notify.Dispose();"
                )
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                )
            except Exception:
                pass
        t = threading.Thread(target=_toast_worker, daemon=True)
        t.start()

    def _trigger_alert(self, alert: Dict[str, Any]):
        """Dispatches the alarm: plays sound, speaks aloud, updates chat & status bridges."""
        label = alert.get("label", "Scheduled Task")
        explanation = alert.get("explanation", "")
        t_str = alert.get("target_time_str", "")

        spoken_msg = alert.get("trigger_speech")
        if not spoken_msg:
            spoken_msg = build_contextual_alert_speech(
                label=label,
                duration_sec=alert.get("delay_seconds"),
                source_query=alert.get("source_query", "")
            )

        print(f"\n🚨 [AlertService ALERT TRIGGERED!] {label} (Scheduled: {t_str})")
        print(f"📢 [Voice Announcement]: {spoken_msg}")

        # 1. Play audible sound
        self._play_alarm_sound_sequence()

        # 2. Update Chat Bridge for GUI
        self._push_chat_bridge(f"⏰ [ALERT TRIGGERED] {spoken_msg}")

        # 3. Speak Voice Notification
        if self.voice_speaker:
            try:
                # Speak in separate thread to prevent worker lockup
                spk_thread = threading.Thread(target=self.voice_speaker, args=(spoken_msg,), daemon=True)
                spk_thread.start()
            except Exception as e:
                print(f"[AlertService Voice Error]: {e}")
        else:
            print(f"🔊 [AlertService Default Voice]: {spoken_msg}")

        # 4. Windows Desktop Notification
        self._send_desktop_notification("Neura AI Alert", spoken_msg)

        # 5. Update Status Bridge
        self.update_status_bridge(last_triggered_msg=f"{label} at {t_str}")

    def _push_chat_bridge(self, message: str):
        """Appends notification message to chat_bridge.json so frontend shows it."""
        try:
            payload = {
                "time": datetime.datetime.now().strftime("%H:%M:%S"),
                "role": "neura",
                "message": message
            }
            if os.path.exists(CHAT_BRIDGE_FILE):
                with open(CHAT_BRIDGE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = []
            data.append(payload)
            if len(data) > 60:
                data = data[-60:]
            temp_file = f"{CHAT_BRIDGE_FILE}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, CHAT_BRIDGE_FILE)
        except Exception:
            pass

    def _worker_loop(self):
        """Continuously checks for alerts whose target timestamp has arrived."""
        while self._worker_active:
            try:
                now_ts = time.time()
                to_trigger = []

                with self._lock:
                    for a in self.alerts:
                        if a.get("status") == "active":
                            target_epoch = a.get("target_epoch", 0)
                            if now_ts >= target_epoch:
                                a["status"] = "triggered"
                                a["triggered_at"] = datetime.datetime.now().isoformat()
                                to_trigger.append(a)

                    if to_trigger:
                        self.save_alerts()

                # Trigger alerts outside lock
                for a in to_trigger:
                    self._trigger_alert(a)

            except Exception as e:
                print(f"⚠️ [AlertService Worker Exception]: {e}")

            time.sleep(0.5)


def get_alert_service(voice_speaker_fn: Optional[Callable[[str], None]] = None) -> AlertService:
    """Returns singleton instance of AlertService."""
    return AlertService.get_instance(voice_speaker_fn=voice_speaker_fn)
