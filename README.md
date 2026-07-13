<div align="center">

# 🚀 NIK AI COMPANION
**The Ultimate Next-Generation Autonomous AI Assistant**

[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![LiveKit](https://img.shields.io/badge/Powered%20By-LiveKit-FF4B4B.svg)](https://livekit.io/)
[![Firebase](https://img.shields.io/badge/Database-Firebase-FFCA28.svg)](https://firebase.google.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](#license)

**Created by: Nikhil Somvanshi**

[Features](#-key-features) • [Installation](#-installation) • [Architecture](#%EF%B8%8F-system-architecture) • [Security](#-hardware-locked-licensing) • [Contributing](#-contributing)

</div>

---

## 🌟 Overview

**NIK** is not just a voice assistant—it is an advanced, autonomous AI companion designed to have human-like, face-to-face conversations. Running continuously in the background, NIK monitors system states, understands screen context via blazing-fast native Windows WinRT OCR, and proactively initiates conversations based on your mood, schedule, and PC activity. 

With an intuitive 4-Mode Dynamic UI, hardware-linked cloud licensing, and deep OS integration, NIK acts as a highly personalized, intelligent digital partner.

---

## 🔥 Key Features

| Category | Feature | Description |
| :--- | :--- | :--- |
| **🤖 Autonomous AI** | Proactive Speech | NIK doesn't just wait for commands. She initiates conversations, cracks jokes, and checks on your mood proactively. |
| **👁️ Computer Vision** | WinRT Native OCR | Uses advanced C# COM reflection via PowerShell to instantly read screen text directly via the Windows Native OCR Engine. |
| **🎙️ Voice Engine** | Low-Latency LiveKit | Integrated with the LiveKit framework for ultra-fast WebRTC-based Voice-to-Voice streaming. |
| **🔒 Security** | Hardware-Locked Keys | Cloud-based licensing system powered by Firebase RTDB. Keys bind permanently to the motherboard UUID. |
| **💻 Deep OS Control** | Windows Automation | Controls volume via Native COM `IAudioEndpointVolume`, adjusts screen brightness, opens apps, and clicks UI elements. |
| **🎨 Dynamic UI** | 4-Mode Theme System | Features Base, Premium, and Elite visual interfaces built with a sleek PyQt5 WebEngine integration. |

---

## ⚙️ System Architecture

NIK is built on a robust, multi-threaded architecture ensuring zero lag between UI rendering and AI processing.

1. **Frontend (PyQt5 + WebEngine)**: Renders HTML/JS/CSS animations and themes seamlessly.
2. **AI Agent Thread (LiveKit)**: A continuous daemon thread that listens to microphone input, processes intent, and generates TTS via LLM pipelines.
3. **Cloud Backend (Firebase)**: Verifies hardware licensing on startup and maintains state synchronization.
4. **Tool Router (Plugin System)**: Over 214+ dynamically loaded tools (from screen grabbing to system diagnosis) injected safely via an auto-patching registry.

---

## 🛡️ Hardware-Locked Licensing (Anti-Piracy)

NIK features a proprietary licensing algorithm. Upon first execution:
1. NIK connects to **Firebase Realtime Database**.
2. Retrieves the hardware's exact **UUID / MAC Address**.
3. Consumes one of the 5 pre-generated Cloud Access Keys.
4. Binds the key to the hardware permanently. 
*If installed on an unauthorized machine, the UI instantly locks and terminates.*

---

## 🚀 Installation & Setup

> **Note:** Due to security restrictions, private files like `.env`, `voice.json`, and memory states are excluded from this repository.

### Prerequisites
- Windows 10/11 (Required for WinRT OCR and COM objects)
- Python 3.10+
- FFmpeg (added to PATH)

### 1. Clone the Repository
```bash
git clone https://github.com/nikhilsomvanshi60/NIK-AI-COMPANION.git
cd NIK-AI-COMPANION
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Setup Environment Variables
Create a `.env` file in the root directory and add your API keys:
```env
LIVEKIT_API_KEY=your_key_here
LIVEKIT_API_SECRET=your_secret_here
LIVEKIT_URL=your_wss_url_here
```

### 4. Setup Firebase Service Account
Add your Firebase Admin SDK credential file as `voice.json` in the root directory.

### 5. Run NIK
```bash
# To run with the full UI
python mj.py

# To run in console mode
python mj.py console
```

---

## 🧠 Memory & Context
NIK maintains persistent local memory logs (`memory.json`, `autonomous_history.json`, `user_profile.json`) which tracks:
- User's daily mood trends.
- Past conversations.
- PC usage metrics.

This allows NIK to provide incredibly personalized and context-aware responses over time.

---

## 🤝 Contributing
Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/nikhilsomvanshi60/NIK-AI-COMPANION/issues).

---

<div align="center">
Made with ❤️ by Nikhil Somvanshi
</div>
