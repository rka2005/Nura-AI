# ⚡ NEURA AI // Next-Gen Cognitive Desktop Assistant & Sci-Fi HUD

<div align="center">

![Neura AI Banner](https://img.shields.io/badge/NEURA_AI-COGNITIVE_CORE_v2.5-00e5ff?style=for-the-badge&logo=probot&logoColor=white)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Pygame](https://img.shields.io/badge/GUI-Pygame_2.6-green?style=flat-square&logo=python)](https://www.pygame.org/)
[![Gemini AI](https://img.shields.io/badge/AI_Engine-Gemini_2.0_Flash-8E75B2?style=flat-square&logo=google)](https://ai.google.dev/)
[![Groq](https://img.shields.io/badge/Fast_LLM-Groq_API-F55036?style=flat-square)](https://groq.com/)
[![OpenCV](https://img.shields.io/badge/Vision-OpenCV_4-5C3EE8?style=flat-square&logo=opencv&logoColor=white)](https://opencv.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows_10%2F11-0078D6?style=flat-square&logo=windows)](https://microsoft.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

<p align="center">
  <strong>An intelligent personal AI companion, cognitive assistant, and Iron Man / JARVIS-inspired cybernetic desktop HUD with 3D audio reactivity, computer vision, deep memory retention, and OS automation.</strong>
</p>

[Key Features](#-key-features) • [Architecture](#-architecture) • [UI & HUD Showcase](#-ui--hud-showcase) • [Tech Stack](#-tech-stack) • [Installation & Setup](#-installation--setup) • [Command Cheatsheet](#-command-cheatsheet) • [Contact](#-developer--contact)

---

</div>

## 🌌 Overview

**Neura AI** is a state-of-the-art multimodal desktop companion engineered by **Rohit Kumar Adak**. Built with a deep focus on sci-fi aesthetics, conversational intelligence, and native operating system automation, Neura bridges high-speed LLM reasoning (via **Google Gemini 2.0 Flash** & **Groq**) with direct desktop agency and a dynamic, audio-reactive cybernetic HUD.

Whether commanded by **natural voice speech** or **tactical keyboard inputs**, Neura manages files, adjusts hardware brightness and volume, tracks real-time hardware telemetry, recalls long-term user preferences, browses the web, and controls desktop workflows seamlessly.

---

## ⚡ Key Features

### 🎙️ 1. Multimodal Interaction & Bi-Directional Bridge
- **Voice-Driven Interaction**: Hands-free voice commands powered by `SpeechRecognition` and `pyttsx3` neural text-to-speech with natural pacing and customizable voice parameters.
- **Interactive In-HUD Text Input**: Blinking cursor input bar with clipboard support (`Ctrl+V`), command history, and instant dispatch for silent operation.
- **Asynchronous Inter-Process Bridge**: Low-latency IPC bridge (`chat_bridge.json`, `input_bridge.json`, `status_bridge.json`) built with Windows file-lock collision retry guards.

### 🌐 2. Quantum Cybernetic HUD (Pygame 2.6 Engine)
- **3D Audio-Reactive Golden Sphere**: 1,800+ mathematically projected surface particles reacting in real-time to microphone acoustic amplitude.
- **Jarvis Arc Reactor HUD**: Rotating processor hexagon, sweeping radar lasers, orbital energy satellites, and expanding voice pulse rings.
- **24-Band Animated Spectrum Visualizer**: Real-time acoustic frequency equalizer bars styled with dynamic theme gradients.
- **Dynamic Theme Engine**: 4 instant colorways (**Orange/Gold**, **Neon Purple**, **Battle Red**, and **Bio Matrix Green**) switchable via in-app chips or hotkeys `1-4`.
- **Adaptive Layout Engine**: Fluid, responsive grid calculations preventing panel collisions on any display resolution from 720p to 4K.

### 🧠 3. 3-Tier Cognitive Memory Engine
- **Tier 1: User Identity & Facts**: Persists name, occupation, hobbies, and personal quirks across reboots.
- **Tier 2: User Preferences**: Retains explicit instructions (e.g., concise response style, preferred weather city, music choices).
- **Tier 3: Rolling Conversation Memory**: Summarizes conversation history, manages token windows, and logs episodic activity traces.
- **Memory Retention Index**: Live HUD meter scoring profile depth and memory density.

### 💻 4. Desktop Agency & Automation
- **System Telemetry Matrix**: Real-time live multi-line graphs tracking CPU load, RAM utilization, and NVIDIA GPU/VRAM metrics.
- **Hardware Controls**: Direct control of screen brightness (`screen_brightness_control`), master volume and mute states (`pycaw`), and media playback.
- **Vision Optics Module**: Live OpenCV webcam stream with sci-fi viewfinder overlays, target crosshairs, and animated radar sweep fallback.
- **Application & File Operations**: Fuzzy folder and file opening, web navigation, Wikipedia search with automatic Google fallback, and task manager integration.

---

## 🏗️ Architecture

Neura decouples visual presentation from cognitive processing using a decoupled dual-process architecture:

```mermaid
flowchart TB
    subgraph UI_Layer ["🖥️ Frontend Interface (frontend.py)"]
        HUD["Quantum Sci-Fi HUD<br/>(Pygame + OpenCV + PyAudio)"]
        Sphere["3D Audio-Reactive Sphere & HUD Core"]
        ChatUI["Conversation Feed & Interactive Input"]
        Visions["Optics Viewfinder & Camera Stream"]
        Telemetry["Hardware Performance Monitor<br/>(CPU / RAM / GPU)"]
    end

    subgraph Bridge_Layer ["⚡ IPC Bridge Layer (JSON & File Locks)"]
        ChatBridge[("chat_bridge.json<br/>Assistant & User Feed")]
        InputBridge[("input_bridge.json<br/>Command Queue")]
        StatusBridge[("status_bridge.json<br/>Live Assistant State")]
    end

    subgraph Core_Engine ["🧠 Backend Engine (neura.py)"]
        VoiceIO["Speech Recognition & PyTTSx3 Speech"]
        Router["Intent Router & Dispatcher<br/>(brain/intent_router.py)"]
        Personality["Fixed Personality System<br/>(brain/personality.py)"]
        DesktopCtrl["Desktop Automation Controller<br/>(brain/desktop_controller.py)"]
        FileMgr["File Manager CRUD<br/>(brain/file_manager.py)"]
        MemoryMgr["3-Tier Memory Manager<br/>(memory/memory_manager.py)"]
    end

    subgraph External_APIs ["☁️ Cloud & System Services"]
        Gemini["Google Gemini 2.0 Flash API"]
        Groq["Groq High-Speed LLM"]
        WinOS["Windows API / PyAutoGUI / Pycaw"]
    end

    HUD <--> |Reads Chat / Updates Input| Bridge_Layer
    Bridge_Layer <--> |Pops Commands / Writes State| Core_Engine
    Router --> Gemini & Groq
    Router --> DesktopCtrl & FileMgr
    Router --> MemoryMgr
    DesktopCtrl --> WinOS
```

---

## 🎨 UI & HUD Showcase

| HUD Module | Description | Visual Highlights |
| :--- | :--- | :--- |
| **Top Cyber Header** | Central system status and operational dashboard | Live pulsing status badge (`READY`, `LISTENING`, `PROCESSING`, `SPEAKING`), live digital clock, instant theme selector chips, and `MIC`/`CAM`/`BOLD`/`CLR` toggles. |
| **Tactical Chat Feed** | Conversation stream & keyboard input | Formatted user bubbles (`YOU`) in cyan/blue glass and Neura responses (`NEURA`) in glowing theme accents with timestamps, smooth wheel scroll, and inline command input bar. |
| **Tactical Command Chips** | One-click action prompts | Instant action chips for `[JOKE]`, `[WEATHER]`, `[MEMORY]`, `[MUSIC]`, `[FILES]`, and `[TASKMGR]`. |
| **Quantum Reactor Core** | Audio-reactive visualizer | 3D mathematical dot sphere, rotating hexagon processor, cyan gap arcs, sweeping lasers, and radial reaction rays. |
| **Optics Viewfinder** | Camera & computer vision frame | Live camera feed with scanlines, corner brackets `[+]`, target lock crosshairs, and animated rotating radar sweep when in standby mode. |
| **Neural Memory Matrix** | Cognitive profile telemetry | User identity tag, activity logs, recent context snippet, and an animated gradient **Retention Index gauge**. |
| **Hardware Telemetry** | Task manager style live monitor | Cyber grid with neon green (CPU), purple (RAM), and amber (GPU/VRAM) real-time wave graphs. |

---

## 🛠️ Tech Stack

| Category | Technologies / Libraries |
| :--- | :--- |
| **Programming Language** | Python 3.10 / 3.11 / 3.12 |
| **Graphical Interface** | Pygame 2.6, PyAudio, OpenCV (`cv2`) |
| **LLM & AI Reasoning** | Google Gemini 2.0 Flash (`google-generativeai`), Groq API |
| **Speech & Audio** | `SpeechRecognition`, `pyttsx3` (SAPI5 voice engine), PyAudio |
| **Hardware Monitoring** | `psutil`, NVIDIA SMI (`nvidia-smi`) |
| **OS Automation & Controls** | `pyautogui`, `pygetwindow`, `pycaw`, `screen_brightness_control`, `keyboard`, `webbrowser` |
| **Data & Memory** | JSON Schema Storage, 3-Tier Hierarchical Memory Model |

---

## 📁 Project Directory Structure

```text
Neura_test_ai/
│
├── neura.py                 # Core AI assistant engine, speech recognition, intent router, execution loop
├── frontend.py              # Quantum Sci-Fi HUD, 3D sphere, audio spectrum, telemetry panels (Pygame)
├── requirements.txt         # Project package dependencies
├── .env                     # Private API keys (Gemini, Groq)
├── chat_bridge.json         # IPC communication bridge: chat history
├── input_bridge.json        # IPC communication bridge: queued UI commands
├── status_bridge.json       # IPC communication bridge: live assistant state
│
├── brain/                   # Cognitive intelligence modules
│   ├── conversation.py      # LLM prompt orchestrator combining identity, memory, and chat history
│   ├── intent_router.py     # Intent classification engine mapping queries to desktop actions
│   ├── personality.py       # Neura's fixed personality guidelines, tone, and behavioral directives
│   ├── desktop_controller.py# Windows automation (volume, brightness, media, apps, screenshots)
│   └── file_manager.py      # File & folder discovery, fuzzy paths, and CRUD operations
│
├── memory/                  # 3-Tier persistent memory subsystem
│   ├── memory_manager.py    # MemoryManager class handling facts, preferences, and session context
│   ├── user_memory.json     # Long-term user profile, preferences, and episodic activity log
│   └── conversation_memory.json # Recent chat turns and summarized conversation memory
│
└── test_voice.py            # Diagnostic script for audio voice testing
```

---

## 🚀 Installation & Setup

### 1. Prerequisites
- **Operating System**: Windows 10 or Windows 11 (64-bit recommended for `pycaw` and SAPI5 TTS).
- **Python**: Python 3.10 to 3.12 installed ([python.org](https://www.python.org/downloads/)).
- **Microphone & Webcam**: Standard audio input and optional webcam.

### 2. Clone the Repository
```bash
git clone https://github.com/rka2005/Nura-AI.git
cd Nura-AI
```

### 3. Create a Virtual Environment
```bash
python -m venv venv
venv\Scripts\activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
pip install groq screen-brightness-control pycaw keyboard pyautogui pyjokes psutil pyaudio
```

> **Note on PyAudio**: If you encounter issues installing `pyaudio` via pip on Windows, install it using `pip install pipwin && pipwin install pyaudio` or download the precompiled wheel from [Unofficial Windows Binaries](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio).

### 5. Configure API Keys
Create a `.env` file in the root directory:
```env
GEMINI_API_KEY=your_google_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here
```
- Obtain a Gemini key: [Google AI Studio](https://aistudio.google.com/)
- Obtain a Groq key: [Groq Console](https://console.groq.com/)

---

## 🎮 Running Neura AI

### Launching the Complete System (HUD + AI Assistant)
Simply start the frontend:
```bash
python frontend.py
```
> `frontend.py` automatically initializes and supervises the `neura.py` daemon in the background.

### Running Headless / Voice-Only Mode
If you prefer running without the HUD GUI:
```bash
python neura.py
```

---

## ⌨️ Command Cheatsheet

Neura accepts commands via **Voice Speech** or by **Typing into the HUD input box**:

| Action Category | Example Commands | Action Triggered |
| :--- | :--- | :--- |
| **Conversational AI** | *"Explain quantum computing in simple terms"* | Streams response via Gemini / Groq with context |
| **Media Control** | *"Play songs on YouTube"*, *"Pause media"*, *"Next track"* | Dispatches media keys or opens YouTube |
| **Volume Control** | *"Set volume to 60%"*, *"Mute volume"*, *"Unmute"* | Adjusts master Windows audio endpoints via `pycaw` |
| **Display Brightness** | *"Increase brightness"*, *"Set brightness to 80%"* | Modifies monitor brightness via WMI |
| **Search & Information** | *"Who is Elon Musk"*, *"Weather in Kolkata"*, *"Search Python docs"* | Wikipedia search (auto-falls back to Google) |
| **Cognitive Memory** | *"What do you know about me"*, *"My favorite city is Tokyo"* | Reads / writes to 3-tier memory engine |
| **Productivity & Notes** | *"Take a note"*, *"Read my notes"*, *"Set a reminder"* | Creates timestamped local notes & timers |
| **System Diagnostics** | *"Open task manager"*, *"Take a screenshot"* | Launches task manager or captures display |
| **Session Control** | *"Clear conversation"*, *"Clear memory"*, *"Goodbye"* | Resets memory buffers or cleanly shuts down |

---

## 🕹️ HUD Hotkeys & Shortcuts

- **`1`**: Switch to **Orange / Gold** Theme (Classic Core)
- **`2`**: Switch to **Neon Purple** Theme (Cyberpunk)
- **`3`**: Switch to **Battle Red** Theme (Combat Matrix)
- **`4`**: Switch to **Bio Matrix** Theme (Emerald Scanner)
- **`U`**: Toggle **Ultra-Bold** HUD Line Geometry
- **`Enter`**: Send typed command in the input box
- **`Esc`**: Clear current input box text
- **`Mouse Wheel`**: Scroll through chat history inside the conversation panel

---

## 👤 Developer & Contact

**Neura AI** is designed and actively developed by **Rohit Kumar Adak**.

- **Author**: Rohit Kumar Adak
- **Email**: [rohitadak0@gmail.com](mailto:rohitadak0@gmail.com)
- **Phone**: `+91 834875905`
- **GitHub**: [@rka2005](https://github.com/rka2005)
- **Repository**: [https://github.com/rka2005/Nura-AI](https://github.com/rka2005/Nura-AI)

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

<div align="center">
  <sub>Built with passion for next-generation Human-AI interaction.</sub>
</div>
