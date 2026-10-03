# Antigravity Agent Guidelines: Context JSON & Dual-Tier Memory Protocol

The agent must strictly follow this protocol on every user request, command, and interaction within this workspace.

---

## 1. Mandatory Context JSON Extraction

On every user command or conversation turn, extract and formulate a structured JSON representation of the user context:

```json
{
  "user_command": "<exact or cleaned user prompt>",
  "task": "<precise task description>",
  "name": "<file name, folder name, app name, module, or entity>",
  "type": "<app | code | script | pdf | excel | word | text | config | conversation>",
  "extension": "<e.g., .py, .json, .pdf, .csv, .xlsx, .txt, .md, or null>",
  "memory_type": "<temporary | fixed>",
  "details": {
    "<key>": "<necessary details to perform the task successfully>"
  }
}
```

Save the active context snapshot into [`.agents/context_memory/active_context.json`](file:///d:/VS%20Code/Neura_test_ai/.agents/context_memory/active_context.json).

---

## 2. Memory Persistence Detection

Classify the command context as either:
- **`temporary`**: One-off queries, ad-hoc status checks, quick inspections, disposable scripts, or transient conversation.
- **`fixed`**: Enduring configurations, persistent rules, repeated workflows, architectural guidelines, or core project modifications.

---

## 3. Context Matching & Memory Resolution (80% Rule)

Before executing a task:
1. Inspect stored memories in:
   - [`.agents/context_memory/fixed_memory.json`](file:///d:/VS%20Code/Neura_test_ai/.agents/context_memory/fixed_memory.json)
   - [`.agents/context_memory/temporary_memory.json`](file:///d:/VS%20Code/Neura_test_ai/.agents/context_memory/temporary_memory.json)

2. Evaluate context similarity between the incoming JSON and previous memory entries (task intent, target name, type, parameters).

3. **If Similarity >= 80% (Match Found)**:
   - Consider both the historical context/method and the newly requested approach.
   - Perform or evaluate both paths to determine which best satisfies the user's requirements.
   - Retain the optimal/successful context in **Fixed Memory** (`fixed_memory.json`).
   - Move or demote the alternative/sub-optimal context to **Temporary Memory** (`temporary_memory.json`).

4. **If Similarity < 80% (New Context)**:
   - Execute the task directly based on the new context JSON.
   - Append the new context record to the appropriate memory store (`fixed_memory.json` if detected as permanent, `temporary_memory.json` if detected as temporary).
