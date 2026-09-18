"""
Conversation and LLM Orchestrator for Neura AI.
Connects Fixed Personality + Dynamic User Memory + Temporary Conversation Context.
"""

import os
import json
from typing import Optional, Tuple
import google.generativeai as genai
from groq import Groq
from dotenv import load_dotenv

from brain.personality import get_personality_prompt
from memory.memory_manager import MemoryManager

load_dotenv()

# Initialize LLM Clients
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

gemini_model = None
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        for g_name in ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash']:
            try:
                gemini_model = genai.GenerativeModel(g_name)
                break
            except Exception:
                continue
    except Exception as e:
        print(f"[Conversation] Gemini config warning: {e}")

groq_client = None
if GROQ_API_KEY:
    try:
        groq_client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        print(f"[Conversation] Groq config warning: {e}")

GROQ_MODELS = ["qwen/qwen3.8-27b", "groq/compound", "openai/gpt-oss-120b"]

def summarize_text(text_to_summarize: str) -> str:
    """Summarizes evicted conversation messages for rolling context."""
    prompt = (
        "Summarize the key information and topics from the following conversation snippet in 1 to 3 concise sentences:\n\n"
        + text_to_summarize
    )
    if gemini_model:
        try:
            res = gemini_model.generate_content(prompt)
            if res and res.text:
                return res.text.strip()
        except Exception:
            pass

    if groq_client:
        for m in GROQ_MODELS:
            try:
                completion = groq_client.chat.completions.create(
                    model=m,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                )
                return completion.choices[0].message.content.strip()
            except Exception:
                continue

    return ""

def llm_detect_preferences(user_text: str) -> Optional[dict]:
    """Uses LLM to detect subtle preferences if rule-based regex didn't catch them."""
    prompt = f"""Analyze this user message to an AI assistant:
"{user_text}"

Does the user express an explicit personal preference, fact about themselves, or a communication instruction (such as response length or format)?
If YES, respond ONLY with a JSON object containing keys like "pref_response_style", "pref_topic", "projects", "likes", etc.
Example: {{"pref_response_style": "concise"}}
If NO, respond ONLY with {{}}.
Do not include backticks, markdown formatting, or any other words. Output JSON only.
"""
    raw_json = "{}"
    if gemini_model:
        try:
            res = gemini_model.generate_content(prompt)
            if res and res.text:
                raw_json = res.text.strip()
        except Exception:
            pass
    elif groq_client:
        for m in GROQ_MODELS:
            try:
                comp = groq_client.chat.completions.create(
                    model=m,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1
                )
                raw_json = comp.choices[0].message.content.strip()
                if raw_json:
                    break
            except Exception:
                continue

    try:
        # Strip potential markdown formatting if returned
        if raw_json.startswith("```"):
            raw_json = raw_json.strip("`").replace("json", "").strip()
        data = json.loads(raw_json)
        return data if isinstance(data, dict) and data else None
    except Exception:
        return None

def generate_ai_response(user_query: str, memory_manager: MemoryManager) -> str:
    """
    Synthesizes personality, user profile, and conversation context into a unified prompt,
    queries the AI model, updates conversation memory, and returns the response.
    """
    # 1. Automatic Learning Pass (detect preferences or facts)
    memory_manager.auto_learn(user_query, llm_detector=llm_detect_preferences)

    # 2. Build Unified Context
    personality_section = get_personality_prompt(memory_manager.user_memory.get("preferences"))
    user_profile_section = memory_manager.get_user_profile_prompt()
    conversation_context_section = memory_manager.get_conversation_context()

    system_instruction = f"""{personality_section}

{user_profile_section}
"""
    context_parts = []
    if conversation_context_section:
        context_parts.append(conversation_context_section)
    context_parts.append(f"User: {user_query}\nNeura:")

    full_query = "\n\n".join(context_parts)

    response_text = ""

    # 3. Try Gemini first
    if gemini_model:
        try:
            full_prompt = f"{system_instruction}\n\n{full_query}"
            gemini_resp = gemini_model.generate_content(full_prompt)
            if gemini_resp and gemini_resp.text and gemini_resp.text.strip() and not "error" in gemini_resp.text.lower():
                response_text = gemini_resp.text.strip()
        except Exception as gemini_err:
            print(f"[Gemini failed: {gemini_err}] ⚡ Switching to Groq...")

    # 4. Fallback to Groq if Gemini failed or is unavailable
    if not response_text and groq_client:
        try:
            messages = [
                {"role": "system", "content": system_instruction},
            ]
            
            # Incorporate recent dialogue messages if any
            for msg in memory_manager.conv_memory.get("recent_messages", []):
                messages.append({
                    "role": "user" if msg["role"] == "user" else "assistant",
                    "content": msg["content"]
                })
            
            messages.append({"role": "user", "content": user_query})

            for m in GROQ_MODELS:
                try:
                    comp = groq_client.chat.completions.create(
                        model=m,
                        messages=messages,
                        temperature=0.6,
                    )
                    response_text = comp.choices[0].message.content.strip()
                    if response_text:
                        break
                except Exception:
                    continue

        except Exception as groq_err:
            print(f"[Groq failed: {groq_err}]")
            response_text = f"I encountered an issue connecting to my brain systems: {groq_err}"

    if not response_text:
        response_text = "I am having trouble reaching my language models right now, Sir. Please check your network and API keys."

    # 5. Append turn to Temporary Conversation Memory (with sliding window + auto-summarize)
    memory_manager.append_turn(user_query, response_text, summarizer=summarize_text)

    return response_text
